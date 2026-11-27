from __future__ import annotations

import argparse
import json
import math
import time
import traceback
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional

import hyperspy.api as hs
import numpy as np
import pandas as pd
from exspy.models.edsmodel import _get_sigma, eV2keV, sigma2fwhm


FIT_MIN_KEV = 0.2
FIT_MAX_KEV = 40.0
INITIAL_RESOLUTION_EV = 128.0
IGNORE_SAMPLE_HALF_WIDTH_KEV = 0.2
BACKGROUND_WINDOWS_SIGMA = (4.0, 3.0)
BASELINE_ORDER = 6
EXPECTED_RESOLUTION_MIN_EV = 127.0
EXPECTED_RESOLUTION_MAX_EV = 131.0
LONG_STEP_SECONDS = 3.0
MODEL_STORE_NAME = "fit_protocol_state"
RESOLUTION_SCORE_PENALTY = 0.05


@dataclass(frozen=True)
class CaseConfig:
    name: str
    spectrum_path: Path
    background_path: Path
    elements: list[str]
    expected_chi2_max: float
    remove_readd_element: str


@dataclass
class StepTrace:
    case_name: str
    protocol_name: str
    cycle_index: int
    step_index: int
    step_name: str
    duration_s: float
    chi2r: float
    offset_keV: float
    resolution_eV: float
    reference_bg_shift_keV: float
    reference_bg_scale: float
    baseline_mean: float
    baseline_integral: float
    baseline_delta_mean_pct: float | None
    baseline_delta_max_pct: float | None
    negative_amplitudes: int
    selected_lines: str
    fit_call_count: int
    fit_call_summary: str
    notes: str


@dataclass
class ProtocolRunSummary:
    case_name: str
    protocol_name: str
    final_cycle_index: int
    final_chi2r: float
    final_offset_keV: float
    final_resolution_eV: float
    final_reference_bg_shift_keV: float
    total_runtime_s: float
    width_out_of_range: bool
    max_baseline_delta_mean_pct: float
    long_step_count: int
    expectation_met: bool
    second_cycle_delta_chi2: float | None
    remove_readd_ok: bool | None
    remove_readd_rms: float | None
    notes: str


@dataclass
class RemoveReaddSummary:
    remove_element: str
    remove_chi2r: float
    readd_chi2r: float
    readd_model_rms: float
    readd_resolution_delta_eV: float
    readd_offset_delta_eV: float
    ok: bool


def scalar_signal_value(signal) -> float:
    data = signal.data
    return float(data.item() if hasattr(data, "item") else data)


def format_fit_call_summary(call_records: list[dict]) -> str:
    if not call_records:
        return ""
    parts = []
    for call in call_records:
        optimizer = call.get("optimizer", "lm")
        bounded = "bounded" if call.get("bounded") else "unbounded"
        free_count = call.get("free_parameter_count")
        duration_s = call.get("duration_s", 0.0)
        parts.append(f"{optimizer}/{bounded}/{free_count}p/{duration_s:.2f}s")
    return " | ".join(parts)


def merge_ranges(ranges: Iterable[tuple[float, float]]) -> list[tuple[float, float]]:
    items = sorted((low, high) for low, high in ranges if high > low)
    if not items:
        return []
    merged: list[tuple[float, float]] = [items[0]]
    for low, high in items[1:]:
        prev_low, prev_high = merged[-1]
        if low <= prev_high:
            merged[-1] = (prev_low, max(prev_high, high))
        else:
            merged.append((low, high))
    return merged


class FitCallTracer:
    def __init__(self, model):
        self.model = model
        self.records: list[dict] = []
        self._orig_fit = None

    def __enter__(self):
        self._orig_fit = self.model.fit

        def wrapped_fit(*args, **kwargs):
            start = time.perf_counter()
            optimizer = kwargs.get("optimizer")
            if optimizer is None and args:
                optimizer = args[0]
            if optimizer is None:
                optimizer = "lm"
            bounded = bool(kwargs.get("bounded", False))
            free_parameter_count = 0
            for component in self.model:
                for parameter in component.parameters:
                    if parameter.free:
                        free_parameter_count += 1
            result = self._orig_fit(*args, **kwargs)
            self.records.append(
                {
                    "optimizer": optimizer,
                    "bounded": bounded,
                    "free_parameter_count": free_parameter_count,
                    "duration_s": time.perf_counter() - start,
                }
            )
            return result

        self.model.fit = wrapped_fit
        return self

    def __exit__(self, exc_type, exc, tb):
        self.model.fit = self._orig_fit
        return False


class SpectrumProtocolStudy:
    def __init__(self, case: CaseConfig, output_dir: Path):
        self.case = case
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.signal_counts = hs.load(str(case.spectrum_path))
        self.signal_counts.metadata.set_item("General.title", case.name)
        self.signal_counts.set_microscope_parameters(energy_resolution_MnKa=INITIAL_RESOLUTION_EV)

        self.background_counts = hs.load(str(case.background_path))
        self.background_counts.metadata.set_item("General.title", f"{case.name}_reference_bg")
        self.background_counts.set_microscope_parameters(energy_resolution_MnKa=INITIAL_RESOLUTION_EV)

        self.signal = self._make_cps_signal(self.signal_counts)
        self.background = self._make_cps_signal(self.background_counts)
        self.signal.set_elements(case.elements)
        axis = self.signal.axes_manager.signal_axes[0]
        self._default_offset = float(axis.offset)
        self._default_scale = float(axis.scale)
        self._default_resolution = float(
            self.signal.metadata.get_item(
                "Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa",
                default=INITIAL_RESOLUTION_EV,
            )
        )

        self.model = self._build_model()
        self.model.store(MODEL_STORE_NAME)

        self.trace_rows: list[StepTrace] = []
        self.fit_call_rows: list[dict] = []
        self.step_index = 0
        self._baseline_reference: Optional[np.ndarray] = None
        self._keep_reference_bg_scale_fixed = False

    def _make_cps_signal(self, signal):
        live_time = self.get_live_time(signal)
        if live_time is None or live_time == 0:
            raise ValueError(f"Live time missing or zero for {signal.metadata.General.title}")
        out = signal.deepcopy()
        out.data = signal.data / live_time
        out.metadata.set_item("Signal.quantity", "X-rays (CPS)")
        return out

    @staticmethod
    def get_live_time(signal) -> float | None:
        return signal.metadata.get_item(
            "Acquisition_instrument.TEM.Detector.EDS.live_time",
            default=None,
        )

    def _build_model(self):
        model = self.signal.create_model(auto_add_lines=True, auto_background=False)
        model.add_polynomial_background(order=BASELINE_ORDER)
        reference_bg = hs.model.components1D.ScalableFixedPattern(self.background)
        reference_bg.name = "instrument"
        reference_bg.isbackground = True
        reference_bg.xscale.free = False
        reference_bg.shift.free = False
        reference_bg.shift.value = 0.0
        reference_bg.yscale.bmin = 0.0
        model.append(reference_bg)
        model.background_components.append(reference_bg)
        self._set_amplitude_bounds(model)
        self._fix_xray_line_energies(model)
        self._fix_xray_line_widths(model)
        return model

    @staticmethod
    def _set_amplitude_bounds(model):
        for component in model:
            if hasattr(component, "A"):
                component.A.bmin = 0.0
                if component.A.value < 0:
                    component.A.value = 0.0

    @staticmethod
    def _fix_xray_line_energies(model):
        for component in model:
            if hasattr(component, "centre") and hasattr(component, "sigma"):
                component.centre.free = False

    @staticmethod
    def _fix_xray_line_widths(model):
        for component in model:
            if hasattr(component, "centre") and hasattr(component, "sigma"):
                component.sigma.free = False

    def restore_initial_model(self):
        self.restore_state(
            {
                "snapshot_name": MODEL_STORE_NAME,
                "offset_keV": self._default_offset,
                "scale_keV": self._default_scale,
                "resolution_eV": self._default_resolution,
            }
        )
        axis = self.signal.axes_manager.signal_axes[0]
        self._set_amplitude_bounds(self.model)
        instrument = self.instrument
        if instrument is not None:
            instrument.yscale.bmin = 0.0
            instrument.xscale.free = False
        self._baseline_reference = None
        self._keep_reference_bg_scale_fixed = False

    def capture_state(self, snapshot_name: str) -> dict:
        self.model.store(snapshot_name)
        axis = self.signal.axes_manager.signal_axes[0]
        return {
            "snapshot_name": snapshot_name,
            "offset_keV": float(axis.offset),
            "scale_keV": float(axis.scale),
            "resolution_eV": self.resolution_eV(),
        }

    def restore_state(self, state: dict):
        self.model = self.signal.models.restore(state["snapshot_name"])
        axis = self.signal.axes_manager.signal_axes[0]
        axis.offset = float(state["offset_keV"])
        axis.scale = float(state["scale_keV"])
        self.signal.set_microscope_parameters(energy_resolution_MnKa=float(state["resolution_eV"]))
        self._set_amplitude_bounds(self.model)
        instrument = self.instrument
        if instrument is not None:
            instrument.yscale.bmin = 0.0
            instrument.xscale.free = False

    @property
    def instrument(self):
        for component in self.model:
            if component.name == "instrument":
                return component
        return None

    @property
    def energy_axis(self) -> np.ndarray:
        return self.signal.axes_manager.signal_axes[0].axis

    def offset_keV(self) -> float:
        return float(self.signal.axes_manager.signal_axes[0].offset)

    def resolution_eV(self) -> float:
        return float(
            self.signal.metadata.get_item(
                "Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa",
                default=INITIAL_RESOLUTION_EV,
            )
        )

    def bg_shift_keV(self) -> float:
        instrument = self.instrument
        return float(instrument.shift.value if instrument is not None else 0.0)

    def bg_scale(self) -> float:
        instrument = self.instrument
        return float(instrument.yscale.value if instrument is not None else 0.0)

    def chi2r(self) -> float:
        return scalar_signal_value(self.model.red_chisq)

    def xray_components(self) -> list:
        return [component for component in self.model if hasattr(component, "A") and hasattr(component, "centre") and hasattr(component, "sigma")]

    def polynomial_components(self) -> list:
        return [component for component in self.model.background_components if component.name != "instrument"]

    def baseline_curve(self) -> np.ndarray:
        axis = self.energy_axis
        baseline = np.zeros_like(axis, dtype=float)
        for component in self.polynomial_components():
            baseline += np.asarray(component.function(axis), dtype=float)
        return baseline

    def negative_amplitude_count(self) -> int:
        count = 0
        for component in self.xray_components():
            if component.A.value < -1e-12:
                count += 1
        return count

    def strong_alpha_lines(
        self,
        min_energy_keV: float = 0.8,
        max_energy_keV: float | None = None,
        max_lines: int = 3,
    ) -> list[str]:
        axis_max = float(self.energy_axis.max())
        if max_energy_keV is None:
            max_energy_keV = axis_max
        candidates: list[tuple[float, float, str]] = []
        for component in self.xray_components():
            name = component.name
            if not (name.endswith("Ka") or name.endswith("La") or name.endswith("Ma")):
                continue
            if not getattr(component, "active", True):
                continue
            energy = float(component.centre.value)
            if energy < min_energy_keV or energy > min(axis_max, max_energy_keV):
                continue
            amplitude = max(float(component.A.value), 0.0)
            candidates.append((amplitude, energy, name))
        candidates.sort(reverse=True)
        selected: list[tuple[float, str]] = []
        for amplitude, energy, name in candidates:
            if any(abs(energy - other_energy) < 0.12 for other_energy, _ in selected):
                continue
            selected.append((energy, name))
            if len(selected) >= max_lines:
                break
        if selected:
            return [name for _, name in selected]

        fallback = [
            component.name
            for component in self.xray_components()
            if component.name.endswith(("Ka", "La", "Ma"))
            and float(component.centre.value) <= min(axis_max, max_energy_keV)
        ]
        return fallback[:max_lines]

    def set_energy_resolution_from_reference_line(self, reference_line: str) -> float:
        energy_mn_ka, _ = self.signal._get_line_energy("Mn_Ka", "auto")
        ref_component = self.model[reference_line]
        get_sigma_mn_ka = _get_sigma(
            energy_mn_ka,
            ref_component.centre.value,
            self.model.units_factor,
            return_f=True,
        )
        fwhm_mn_ka = (
            get_sigma_mn_ka(ref_component.sigma.value)
            * eV2keV
            / self.model.units_factor
            * sigma2fwhm
        )
        self.signal.set_microscope_parameters(energy_resolution_MnKa=fwhm_mn_ka)
        for component in self.xray_components():
            line_fwhm = self.signal._get_line_energy(component.name, FWHM_MnKa="auto")[1]
            component.fwhm = line_fwhm
        return float(fwhm_mn_ka)

    def sample_exclusion_ranges(self, half_width_keV: float) -> list[tuple[float, float]]:
        ranges = []
        for component in self.xray_components():
            energy = float(component.centre.value)
            low = max(FIT_MIN_KEV, energy - half_width_keV)
            high = min(FIT_MAX_KEV, energy + half_width_keV)
            if high > low:
                ranges.append((low, high))
        return merge_ranges(ranges)

    @contextmanager
    def temporary_signal_range(self, exclude_sample_half_width_keV: float | None = None):
        self.model.set_signal_range(FIT_MIN_KEV, FIT_MAX_KEV)
        try:
            if exclude_sample_half_width_keV:
                for low, high in self.sample_exclusion_ranges(exclude_sample_half_width_keV):
                    self.model.remove_signal_range(low, high)
            yield
        finally:
            self.model.reset_signal_range()

    def snapshot_parameters(self) -> dict:
        snapshot = {
            "offset_keV": self.offset_keV(),
            "resolution_eV": self.resolution_eV(),
            "reference_bg_shift_keV": self.bg_shift_keV(),
            "reference_bg_scale": self.bg_scale(),
            "negative_amplitudes": self.negative_amplitude_count(),
            "selected_alpha_lines": self.strong_alpha_lines(),
            "instrument": {},
            "background_components": {},
            "xray_line_amplitudes": {},
        }
        instrument = self.instrument
        if instrument is not None:
            snapshot["instrument"] = {
                "shift": float(instrument.shift.value),
                "shift_free": bool(instrument.shift.free),
                "yscale": float(instrument.yscale.value),
                "yscale_free": bool(instrument.yscale.free),
            }
        for component in self.polynomial_components():
            snapshot["background_components"][component.name] = {
                parameter.name: float(parameter.value) for parameter in component.parameters
            }
        for component in self.xray_components():
            snapshot["xray_line_amplitudes"][component.name] = float(component.A.value)
        return snapshot

    def _write_baseline_curve(self, protocol_name: str, cycle_index: int, step_name: str, baseline: np.ndarray):
        safe_step = step_name.replace(" ", "_").replace("/", "_")
        path = self.output_dir / f"{protocol_name}_cycle{cycle_index:02d}_{self.step_index:03d}_{safe_step}_baseline.csv"
        pd.DataFrame({"energy_keV": self.energy_axis, "baseline_cps": baseline}).to_csv(path, index=False)

    def _write_parameter_snapshot(self, protocol_name: str, cycle_index: int, step_name: str, data: dict):
        safe_step = step_name.replace(" ", "_").replace("/", "_")
        path = self.output_dir / f"{protocol_name}_cycle{cycle_index:02d}_{self.step_index:03d}_{safe_step}_snapshot.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record_step(
        self,
        protocol_name: str,
        cycle_index: int,
        step_name: str,
        duration_s: float,
        fit_calls: list[dict],
        notes: str = "",
        selected_lines: Optional[list[str]] = None,
    ):
        baseline = self.baseline_curve()
        baseline_mean = float(np.mean(np.abs(baseline)))
        baseline_integral = float(np.trapezoid(baseline, self.energy_axis))
        baseline_delta_mean_pct = None
        baseline_delta_max_pct = None
        if self._baseline_reference is not None:
            delta = np.abs(baseline - self._baseline_reference)
            baseline_delta_mean_pct = float(
                100.0 * np.mean(delta) / max(np.mean(np.abs(self._baseline_reference)), 1e-12)
            )
            baseline_delta_max_pct = float(
                100.0 * np.max(delta) / max(np.max(np.abs(self._baseline_reference)), 1e-12)
            )
        self._baseline_reference = baseline.copy()

        selected_text = ",".join(selected_lines or [])
        fit_summary = format_fit_call_summary(fit_calls)
        row = StepTrace(
            case_name=self.case.name,
            protocol_name=protocol_name,
            cycle_index=cycle_index,
            step_index=self.step_index,
            step_name=step_name,
            duration_s=duration_s,
            chi2r=self.chi2r(),
            offset_keV=self.offset_keV(),
            resolution_eV=self.resolution_eV(),
            reference_bg_shift_keV=self.bg_shift_keV(),
            reference_bg_scale=self.bg_scale(),
            baseline_mean=baseline_mean,
            baseline_integral=baseline_integral,
            baseline_delta_mean_pct=baseline_delta_mean_pct,
            baseline_delta_max_pct=baseline_delta_max_pct,
            negative_amplitudes=self.negative_amplitude_count(),
            selected_lines=selected_text,
            fit_call_count=len(fit_calls),
            fit_call_summary=fit_summary,
            notes=notes,
        )
        self.trace_rows.append(row)
        for fit_index, fit_call in enumerate(fit_calls, start=1):
            fit_row = dict(fit_call)
            fit_row.update(
                {
                    "case_name": self.case.name,
                    "protocol_name": protocol_name,
                    "cycle_index": cycle_index,
                    "step_index": self.step_index,
                    "fit_index": fit_index,
                    "step_name": step_name,
                }
            )
            self.fit_call_rows.append(fit_row)

        anomaly = False
        anomaly_notes: list[str] = []
        if row.resolution_eV < EXPECTED_RESOLUTION_MIN_EV or row.resolution_eV > EXPECTED_RESOLUTION_MAX_EV:
            anomaly = True
            anomaly_notes.append("resolution outside expected 127-131 eV")
        if baseline_delta_mean_pct is not None and baseline_delta_mean_pct > 20.0:
            anomaly = True
            anomaly_notes.append("baseline mean delta > 20%")
        if duration_s > LONG_STEP_SECONDS:
            anomaly = True
            anomaly_notes.append("step longer than 3 s")
        if row.negative_amplitudes:
            anomaly = True
            anomaly_notes.append("negative amplitudes detected")

        if anomaly:
            snapshot = self.snapshot_parameters()
            snapshot["fit_calls"] = fit_calls
            snapshot["notes"] = notes
            snapshot["anomaly_notes"] = anomaly_notes
            self._write_parameter_snapshot(protocol_name, cycle_index, step_name, snapshot)

        self._write_baseline_curve(protocol_name, cycle_index, step_name, baseline)
        self.step_index += 1

    def run_step(
        self,
        protocol_name: str,
        cycle_index: int,
        step_name: str,
        action: Callable[[], Optional[str]],
        selected_lines: Optional[list[str]] = None,
    ):
        selected_lines = list(selected_lines or [])
        start = time.perf_counter()
        with FitCallTracer(self.model) as tracer:
            notes = action() or ""
        duration_s = time.perf_counter() - start
        self.record_step(
            protocol_name=protocol_name,
            cycle_index=cycle_index,
            step_name=step_name,
            duration_s=duration_s,
            fit_calls=tracer.records,
            notes=notes,
            selected_lines=selected_lines,
        )

    def prefit_reference_bg_masked(self):
        self.model.disable_xray_lines()
        self.model.free_background()
        instrument = self.instrument
        instrument.shift.free = True
        instrument.yscale.free = True
        try:
            with self.temporary_signal_range(exclude_sample_half_width_keV=IGNORE_SAMPLE_HALF_WIDTH_KEV):
                self.model.fit(optimizer="trf", bounded=True)
        finally:
            instrument.shift.free = False
            self.model.enable_xray_lines()
        return (
            f"Masked background prefit with sample windows excluded. "
            f"Scale={self.bg_scale():.4f}, Shift={self.bg_shift_keV():.6f} keV"
        )

    def prefit_reference_bg_scale_masked(self):
        self.model.disable_xray_lines()
        instrument = self.instrument
        previous_states = []
        for component in self.model:
            for parameter in component.parameters:
                previous_states.append((parameter, parameter.free, parameter.twin))
                parameter.free = False
        instrument.shift.free = False
        instrument.yscale.free = True
        try:
            with self.temporary_signal_range(exclude_sample_half_width_keV=IGNORE_SAMPLE_HALF_WIDTH_KEV):
                self.model.fit(optimizer="trf", bounded=True)
        finally:
            self.model.enable_xray_lines()
            for parameter, free, twin in previous_states:
                parameter.free = free
                parameter.twin = twin
        return (
            f"Masked reference-BG scale prefit only. "
            f"Scale={self.bg_scale():.4f}, Shift={self.bg_shift_keV():.6f} keV"
        )

    def prefit_reference_bg_scale_masked_and_lock(self):
        note = self.prefit_reference_bg_scale_masked()
        self._keep_reference_bg_scale_fixed = True
        return note + ". Keeping reference-BG scale fixed in subsequent full fits"

    def refine_reference_bg_shift_masked(self):
        instrument = self.instrument
        previous_states = []
        for component in self.model:
            for parameter in component.parameters:
                previous_states.append((parameter, parameter.free, parameter.twin))
                parameter.free = False
        instrument.shift.free = True
        instrument.yscale.free = True
        with self.temporary_signal_range(exclude_sample_half_width_keV=IGNORE_SAMPLE_HALF_WIDTH_KEV):
            self.model.fit(optimizer="lm", bounded=False)
        instrument.shift.free = False
        masked_chi2 = self.chi2r()
        for parameter, free, twin in previous_states:
            parameter.free = free
            parameter.twin = twin
        return (
            f"Masked BG-window fit for reference BG shift only. "
            f"Shift={self.bg_shift_keV():.6f} keV, Scale={self.bg_scale():.4f}, "
            f"masked chi2r={masked_chi2:.3f}"
        )

    def refine_reference_bg_shift_only_masked(self):
        instrument = self.instrument
        previous_states = []
        for component in self.model:
            for parameter in component.parameters:
                previous_states.append((parameter, parameter.free, parameter.twin))
                parameter.free = False
        instrument.shift.free = True
        instrument.yscale.free = False
        with self.temporary_signal_range(exclude_sample_half_width_keV=IGNORE_SAMPLE_HALF_WIDTH_KEV):
            self.model.fit(optimizer="lm", bounded=False)
        masked_chi2 = self.chi2r()
        for parameter, free, twin in previous_states:
            parameter.free = free
            parameter.twin = twin
        return (
            f"Masked BG-window fit for reference BG shift only (scale fixed). "
            f"Shift={self.bg_shift_keV():.6f} keV, Scale={self.bg_scale():.4f}, "
            f"masked chi2r={masked_chi2:.3f}"
        )

    def prefit_reference_bg_docs(self):
        note = self.prefit_reference_bg_masked()
        return (
            "Docs-like background-first route. "
            "exSpy fit_background() is not compatible here with a polynomial plus "
            f"ScalableFixedPattern reference background, so this uses the masked "
            f"background-only prefit instead. {note}"
        )

    def initial_bounded_fit(self):
        self.model.enable_xray_lines()
        self.model.free_background()
        self._fix_xray_line_energies(self.model)
        self._fix_xray_line_widths(self.model)
        instrument = self.instrument
        instrument.shift.free = False
        instrument.yscale.free = not self._keep_reference_bg_scale_fixed
        with self.temporary_signal_range():
            self.model.fit(optimizer="trf", bounded=True)
        return (
            f"Initial bounded fit. chi2r={self.chi2r():.3f}, "
            f"resolution={self.resolution_eV():.2f} eV, "
            f"reference-BG scale={'fixed' if self._keep_reference_bg_scale_fixed else 'free'}"
        )

    def calibrate_offset(self):
        instrument = self.instrument
        instrument.shift.free = False
        with self.temporary_signal_range():
            self.model.calibrate_energy_axis(calibrate="offset")
        return f"Overall offset calibration to {self.offset_keV():.6f} keV"

    def calibrate_selected_line_energies(self, selected_lines: list[str]):
        with self.temporary_signal_range():
            self.model.calibrate_xray_lines("energy", selected_lines, bound=10)
        return f"Selected-line energy calibration on {', '.join(selected_lines)}"

    def calibrate_resolution_exspy(self, selected_lines: list[str]):
        if not selected_lines:
            selected_lines = self.strong_alpha_lines()
        self.model._twin_xray_lines_width(xray_lines=selected_lines)
        with self.temporary_signal_range():
            self.model.fit(optimizer="lm", bounded=False)
        self._fix_xray_line_widths(self.model)
        resolution = self.set_energy_resolution_from_reference_line(selected_lines[0])
        return f"exSpy-like resolution calibration on {', '.join(selected_lines)} -> {resolution:.2f} eV"

    def calibrate_resolution_global(self, selected_lines: list[str]):
        if not selected_lines:
            selected_lines = self.strong_alpha_lines()
        self._fix_xray_line_energies(self.model)
        self.model.fix_background()
        instrument = self.instrument
        instrument.yscale.free = False
        instrument.shift.free = False
        self.model._twin_xray_lines_width(xray_lines=selected_lines)
        for component in self.xray_components():
            component.sigma.free = component.name in selected_lines
        try:
            with self.temporary_signal_range():
                self.model.fit(optimizer="trf", bounded=True)
        finally:
            self._fix_xray_line_widths(self.model)
            resolution = self.set_energy_resolution_from_reference_line(selected_lines[0])
            self.model.free_background()
            instrument.yscale.free = True
        return f"Global twinned-width resolution fit on {', '.join(selected_lines)} -> {resolution:.2f} eV"

    def calibrate_resolution_locked(self, selected_lines: list[str]):
        if not selected_lines:
            selected_lines = self.strong_alpha_lines()
        previous_states = []
        for component in self.model:
            for parameter in component.parameters:
                previous_states.append((parameter, parameter.free, parameter.twin))
                parameter.free = False
        self.model._twin_xray_lines_width(selected_lines)
        for line_name in selected_lines[1:]:
            self.model[line_name].sigma.free = False
        with self.temporary_signal_range():
            self.model.fit(optimizer="lm", bounded=False)
        self._fix_xray_line_widths(self.model)
        resolution = self.set_energy_resolution_from_reference_line(selected_lines[0])
        for parameter, free, twin in previous_states:
            parameter.free = free
            parameter.twin = twin
        return (
            f"Locked one-parameter resolution calibration on {', '.join(selected_lines)} "
            f"-> {resolution:.2f} eV"
        )

    def resolution_line_candidates(self) -> list[tuple[str, list[str]]]:
        candidates: list[tuple[str, list[str]]] = []
        strong_mixed = self.strong_alpha_lines()
        if strong_mixed:
            candidates.append(("mixed_strong", strong_mixed))
        low_energy = self.strong_alpha_lines(max_energy_keV=2.0)
        if low_energy and low_energy != strong_mixed:
            candidates.append(("low_energy", low_energy))
        very_low_energy = self.strong_alpha_lines(max_energy_keV=1.8)
        if very_low_energy and very_low_energy not in [lines for _, lines in candidates]:
            candidates.append(("very_low_energy", very_low_energy))
        return candidates

    @staticmethod
    def resolution_penalty(resolution_eV: float) -> float:
        excess = 0.0
        if resolution_eV < EXPECTED_RESOLUTION_MIN_EV:
            excess = EXPECTED_RESOLUTION_MIN_EV - resolution_eV
        elif resolution_eV > EXPECTED_RESOLUTION_MAX_EV:
            excess = resolution_eV - EXPECTED_RESOLUTION_MAX_EV
        return RESOLUTION_SCORE_PENALTY * (excess ** 2)

    def calibrate_resolution_candidate_search(self):
        baseline_state = self.capture_state(f"{MODEL_STORE_NAME}_resolution_base_{self.step_index}")
        best_state = baseline_state
        best_name = "skip"
        best_score = self.chi2r() + self.resolution_penalty(self.resolution_eV())
        best_notes = [f"skip: chi2r={self.chi2r():.3f}, res={self.resolution_eV():.2f} eV, score={best_score:.3f}"]

        for label, lines in self.resolution_line_candidates():
            self.restore_state(baseline_state)
            self.calibrate_resolution_locked(lines)
            self.refit_linear_terms()
            candidate_chi2 = self.chi2r()
            candidate_res = self.resolution_eV()
            candidate_score = candidate_chi2 + self.resolution_penalty(candidate_res)
            best_notes.append(
                f"{label}({','.join(lines)}): chi2r={candidate_chi2:.3f}, "
                f"res={candidate_res:.2f} eV, score={candidate_score:.3f}"
            )
            if candidate_score < best_score:
                best_name = label
                best_score = candidate_score
                best_state = self.capture_state(f"{MODEL_STORE_NAME}_resolution_best_{label}_{self.step_index}")

        self.restore_state(best_state)
        return "Resolution candidate search selected " + best_name + ". " + " | ".join(best_notes)

    def _chi2_of_state(self, state: dict) -> float:
        current_state = self.capture_state(f"{MODEL_STORE_NAME}_tmp_current_{self.step_index}")
        try:
            self.restore_state(state)
            return self.chi2r()
        finally:
            self.restore_state(current_state)

    def refit_linear_terms(self):
        instrument = self.instrument
        for component in self.model:
            for parameter in component.parameters:
                parameter.free = False
        for component in self.xray_components():
            if component.A.twin is None:
                component.A.free = True
        for component in self.polynomial_components():
            component.set_parameters_free()
        instrument.yscale.free = not self._keep_reference_bg_scale_fixed
        instrument.shift.free = False
        instrument.xscale.free = False
        self._fix_xray_line_energies(self.model)
        self._fix_xray_line_widths(self.model)
        with self.temporary_signal_range():
            self.model.fit(optimizer="trf", bounded=True)
        if self._keep_reference_bg_scale_fixed:
            return "Re-fit amplitudes and baseline with reference-background scale fixed"
        return "Re-fit amplitudes, baseline, and reference-background scale"

    def remove_readd_element(self, element: str) -> RemoveReaddSummary:
        refined_model_signal = np.asarray(self.model.as_signal(show_progressbar=False).data, dtype=float)
        refined_resolution = self.resolution_eV()
        refined_offset = self.offset_keV()

        affected = [component for component in self.xray_components() if component.name.startswith(f"{element}_")]
        if not affected:
            raise ValueError(f"Element {element} not found in model for {self.case.name}")

        for component in affected:
            component.active = False
        self.refit_linear_terms()
        remove_chi2 = self.chi2r()

        for component in affected:
            component.active = True
        self.refit_linear_terms()
        readd_chi2 = self.chi2r()

        readd_model_signal = np.asarray(self.model.as_signal(show_progressbar=False).data, dtype=float)
        rms = float(np.sqrt(np.mean((readd_model_signal - refined_model_signal) ** 2)))
        resolution_delta = self.resolution_eV() - refined_resolution
        offset_delta = (self.offset_keV() - refined_offset) * 1000.0
        ok = rms < 1e-3 and abs(resolution_delta) < 1e-6 and abs(offset_delta) < 1e-6
        return RemoveReaddSummary(
            remove_element=element,
            remove_chi2r=remove_chi2,
            readd_chi2r=readd_chi2,
            readd_model_rms=rms,
            readd_resolution_delta_eV=resolution_delta,
            readd_offset_delta_eV=offset_delta,
            ok=ok,
        )

    def write_outputs(self, protocol_summaries: list[ProtocolRunSummary]):
        trace_path = self.output_dir / "step_trace.csv"
        fit_call_path = self.output_dir / "fit_calls.csv"
        summary_path = self.output_dir / "protocol_summary.csv"
        pd.DataFrame([asdict(row) for row in self.trace_rows]).to_csv(trace_path, index=False)
        pd.DataFrame(self.fit_call_rows).to_csv(fit_call_path, index=False)
        pd.DataFrame([asdict(row) for row in protocol_summaries]).to_csv(summary_path, index=False)


def run_protocol(
    study: SpectrumProtocolStudy,
    protocol_name: str,
    steps: list[tuple[str, Callable[[SpectrumProtocolStudy, list[str]], Optional[str]], bool]],
    repeat_cycle: bool,
    remove_readd: bool,
) -> ProtocolRunSummary:
    study.restore_initial_model()
    selected_lines = study.strong_alpha_lines()
    cycle_count = 2 if repeat_cycle else 1
    cycle_end_chi2: list[float] = []
    protocol_start = time.perf_counter()
    summary_notes: list[str] = [f"Initial selected lines: {', '.join(selected_lines)}"]

    for cycle_index in range(1, cycle_count + 1):
        if cycle_index > 1:
            selected_lines = study.strong_alpha_lines()
            summary_notes.append(f"Cycle {cycle_index} selected lines: {', '.join(selected_lines)}")
        for step_name, step_func, uses_selected_lines in steps:
            current_lines = study.strong_alpha_lines() if uses_selected_lines else []
            study.run_step(
                protocol_name=protocol_name,
                cycle_index=cycle_index,
                step_name=step_name,
                action=lambda f=step_func, lines=current_lines: f(study, lines),
                selected_lines=current_lines,
            )
        cycle_end_chi2.append(study.chi2r())

    remove_readd_summary = None
    if remove_readd:
        remove_readd_summary = study.remove_readd_element(study.case.remove_readd_element)
        summary_notes.append(
            f"Remove/re-add {remove_readd_summary.remove_element}: "
            f"rms={remove_readd_summary.readd_model_rms:.6f}, ok={remove_readd_summary.ok}"
        )

    protocol_rows = [row for row in study.trace_rows if row.protocol_name == protocol_name]
    total_runtime_s = time.perf_counter() - protocol_start
    final_row = protocol_rows[-1]
    width_out_of_range = any(
        row.resolution_eV < EXPECTED_RESOLUTION_MIN_EV or row.resolution_eV > EXPECTED_RESOLUTION_MAX_EV
        for row in protocol_rows
    )
    baseline_deltas = [
        row.baseline_delta_mean_pct
        for row in protocol_rows
        if row.baseline_delta_mean_pct is not None
    ]
    long_step_count = sum(1 for row in protocol_rows if row.duration_s > LONG_STEP_SECONDS)
    expectation_met = final_row.chi2r <= study.case.expected_chi2_max
    second_cycle_delta = None
    if len(cycle_end_chi2) >= 2:
        second_cycle_delta = cycle_end_chi2[1] - cycle_end_chi2[0]

    return ProtocolRunSummary(
        case_name=study.case.name,
        protocol_name=protocol_name,
        final_cycle_index=cycle_count,
        final_chi2r=final_row.chi2r,
        final_offset_keV=final_row.offset_keV,
        final_resolution_eV=final_row.resolution_eV,
        final_reference_bg_shift_keV=final_row.reference_bg_shift_keV,
        total_runtime_s=total_runtime_s,
        width_out_of_range=width_out_of_range,
        max_baseline_delta_mean_pct=max(baseline_deltas) if baseline_deltas else 0.0,
        long_step_count=long_step_count,
        expectation_met=expectation_met,
        second_cycle_delta_chi2=second_cycle_delta,
        remove_readd_ok=None if remove_readd_summary is None else remove_readd_summary.ok,
        remove_readd_rms=None if remove_readd_summary is None else remove_readd_summary.readd_model_rms,
        notes=" | ".join(summary_notes),
    )


def protocol_definitions():
    return {
        "docs_manual": [
            ("Prefit reference BG (docs windows)", lambda study, _: study.prefit_reference_bg_docs(), False),
            ("Initial bounded fit", lambda study, _: study.initial_bounded_fit(), False),
            ("Calibrate selected line energies", lambda study, lines: study.calibrate_selected_line_energies(lines), True),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Calibrate resolution (exSpy)", lambda study, lines: study.calibrate_resolution_exspy(lines), True),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
        ],
        "masked_bg_offset_resolution": [
            ("Prefit reference BG (masked)", lambda study, _: study.prefit_reference_bg_masked(), False),
            ("Initial bounded fit", lambda study, _: study.initial_bounded_fit(), False),
            ("Calibrate overall offset", lambda study, _: study.calibrate_offset(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Calibrate resolution (exSpy)", lambda study, lines: study.calibrate_resolution_exspy(lines), True),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
        ],
        "masked_bg_energy_resolution": [
            ("Prefit reference BG (masked)", lambda study, _: study.prefit_reference_bg_masked(), False),
            ("Initial bounded fit", lambda study, _: study.initial_bounded_fit(), False),
            ("Calibrate selected line energies", lambda study, lines: study.calibrate_selected_line_energies(lines), True),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Calibrate resolution (exSpy)", lambda study, lines: study.calibrate_resolution_exspy(lines), True),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
        ],
        "masked_bg_offset_global_resolution": [
            ("Prefit reference BG (masked)", lambda study, _: study.prefit_reference_bg_masked(), False),
            ("Initial bounded fit", lambda study, _: study.initial_bounded_fit(), False),
            ("Calibrate overall offset", lambda study, _: study.calibrate_offset(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Calibrate resolution (global twinned)", lambda study, lines: study.calibrate_resolution_global(lines), True),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
        ],
        "offset_bgshift_locked_resolution": [
            ("Initial bounded fit", lambda study, _: study.initial_bounded_fit(), False),
            ("Calibrate overall offset", lambda study, _: study.calibrate_offset(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Refine reference BG shift (masked)", lambda study, _: study.refine_reference_bg_shift_masked(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Calibrate resolution (locked global)", lambda study, lines: study.calibrate_resolution_locked(lines), True),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
        ],
        "offset_bgshift_resolution_search": [
            ("Initial bounded fit", lambda study, _: study.initial_bounded_fit(), False),
            ("Calibrate overall offset", lambda study, _: study.calibrate_offset(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Refine reference BG shift (masked)", lambda study, _: study.refine_reference_bg_shift_masked(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Calibrate resolution (candidate search)", lambda study, _: study.calibrate_resolution_candidate_search(), False),
        ],
        "yscale_prefit_offset_bgshift_resolution_search": [
            ("Prefit reference BG scale (masked)", lambda study, _: study.prefit_reference_bg_scale_masked(), False),
            ("Initial bounded fit", lambda study, _: study.initial_bounded_fit(), False),
            ("Calibrate overall offset", lambda study, _: study.calibrate_offset(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Refine reference BG shift (masked)", lambda study, _: study.refine_reference_bg_shift_masked(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Calibrate resolution (candidate search)", lambda study, _: study.calibrate_resolution_candidate_search(), False),
        ],
        "yscale_prefit_fixed_scale_offset_bgshiftonly_resolution_search": [
            ("Prefit reference BG scale (masked, lock)", lambda study, _: study.prefit_reference_bg_scale_masked_and_lock(), False),
            ("Initial bounded fit", lambda study, _: study.initial_bounded_fit(), False),
            ("Calibrate overall offset", lambda study, _: study.calibrate_offset(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Refine reference BG shift only (masked)", lambda study, _: study.refine_reference_bg_shift_only_masked(), False),
            ("Refit linear terms", lambda study, _: study.refit_linear_terms(), False),
            ("Calibrate resolution (candidate search)", lambda study, _: study.calibrate_resolution_candidate_search(), False),
        ],
    }


def default_cases(repo_root: Path) -> list[CaseConfig]:
    acac_dir = repo_root / "acac"
    acac_elements = ["C", "O", "Fe", "Al", "Ga", "Ge", "N"]
    cases = [
        CaseConfig(
            name=name,
            spectrum_path=acac_dir / f"{name}.EDS",
            background_path=acac_dir / "near_7994.EDS",
            elements=acac_elements,
            expected_chi2_max=1.0,
            remove_readd_element="Ge",
        )
        for name in ["exp_7984", "exp_7988", "exp_7989", "exp_7990", "exp_7992", "exp_7993", "exp_7995"]
    ]
    cases.append(
        CaseConfig(
            name="grain1_thick",
            spectrum_path=repo_root / "grain1_thick.eds",
            background_path=repo_root / "bg_near_grain1_thick.eds",
            elements=["C", "Cl", "Cu", "K", "Na", "O", "S", "Ca"],
            expected_chi2_max=0.2,
            remove_readd_element="Ca",
        )
    )
    return cases


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone EDS fitting protocol explorer")
    parser.add_argument(
        "--cases",
        nargs="*",
        help="Optional subset of case names to run",
    )
    parser.add_argument(
        "--protocols",
        nargs="*",
        help="Optional subset of protocol names to run",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to tests/fitting_protocol_outputs/<timestamp>",
    )
    parser.add_argument(
        "--repeat-cycle",
        action="store_true",
        help="Run each protocol twice in succession to test stability",
    )
    parser.add_argument(
        "--remove-readd",
        action="store_true",
        help="Run remove/re-add element validation after each protocol",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_root = args.output_dir or repo_root / "tests" / "fitting_protocol_outputs" / timestamp
    output_root.mkdir(parents=True, exist_ok=True)

    cases = default_cases(repo_root)
    if args.cases:
        wanted = set(args.cases)
        cases = [case for case in cases if case.name in wanted]
    protocols = protocol_definitions()
    if args.protocols:
        wanted = set(args.protocols)
        protocols = {name: steps for name, steps in protocols.items() if name in wanted}

    all_summaries: list[ProtocolRunSummary] = []
    failures: list[dict] = []
    for case in cases:
        case_output_dir = output_root / case.name
        case_output_dir.mkdir(parents=True, exist_ok=True)
        study = SpectrumProtocolStudy(case, case_output_dir)
        case_summaries: list[ProtocolRunSummary] = []
        for protocol_name, steps in protocols.items():
            try:
                print(f"\n=== {case.name} / {protocol_name} ===")
                summary = run_protocol(
                    study=study,
                    protocol_name=protocol_name,
                    steps=steps,
                    repeat_cycle=args.repeat_cycle,
                    remove_readd=args.remove_readd,
                )
                case_summaries.append(summary)
                all_summaries.append(summary)
                print(
                    f"Final chi2r={summary.final_chi2r:.3f}, "
                    f"resolution={summary.final_resolution_eV:.2f} eV, "
                    f"offset={summary.final_offset_keV:.6f} keV"
                )
            except Exception as exc:  # pragma: no cover - analysis script
                failures.append(
                    {
                        "case_name": case.name,
                        "protocol_name": protocol_name,
                        "error": repr(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
                print(f"FAILED: {case.name} / {protocol_name}: {exc}")
        study.write_outputs(case_summaries)

    pd.DataFrame([asdict(summary) for summary in all_summaries]).to_csv(
        output_root / "all_protocol_summary.csv",
        index=False,
    )
    if failures:
        (output_root / "failures.json").write_text(json.dumps(failures, indent=2), encoding="utf-8")
        print(f"\nCompleted with {len(failures)} failures. See {output_root / 'failures.json'}")
    else:
        print(f"\nCompleted without failures. Outputs: {output_root}")


if __name__ == "__main__":
    main()
