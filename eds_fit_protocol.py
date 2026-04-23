from __future__ import annotations

import re
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Callable, Optional

import hyperspy.api as hs
import numpy as np
from exspy.models.edsmodel import _get_sigma, eV2keV, sigma2fwhm

try:
    import numexpr
except ImportError:  # pragma: no cover - HyperSpy falls back to numpy.
    numexpr = None


_NUMEXPR_THREAD_LOCK = threading.Lock()
_NUMEXPR_THREAD_USERS = 0
_NUMEXPR_PREVIOUS_THREADS = None


@contextmanager
def small_signal_numexpr():
    """Force numexpr to one thread for small 1D EDS fits."""
    if numexpr is None:
        yield
        return

    try:
        global _NUMEXPR_THREAD_USERS, _NUMEXPR_PREVIOUS_THREADS
        with _NUMEXPR_THREAD_LOCK:
            if _NUMEXPR_THREAD_USERS == 0:
                _NUMEXPR_PREVIOUS_THREADS = numexpr.set_num_threads(1)
            _NUMEXPR_THREAD_USERS += 1
        yield
    finally:
        with _NUMEXPR_THREAD_LOCK:
            _NUMEXPR_THREAD_USERS -= 1
            if _NUMEXPR_THREAD_USERS == 0:
                numexpr.set_num_threads(_NUMEXPR_PREVIOUS_THREADS)
                _NUMEXPR_PREVIOUS_THREADS = None


@dataclass(frozen=True)
class FittingProtocolConfig:
    fit_energy_min_keV: float = 0.2
    fit_energy_max_keV: float = 40.0
    initial_resolution_eV: float = 128.0
    background_polynomial_order: int = 6
    ignore_sample_half_width_keV: float = 0.2
    reference_bg_scale_prefit_enabled: bool = True
    expected_resolution_min_eV: float = 127.0
    expected_resolution_max_eV: float = 131.0
    resolution_score_penalty: float = 0.05
    amplitude_bmin: float = 0.0
    resolution_candidate_min_energy_keV: float = 0.8
    resolution_candidate_max_energy_keV: tuple[float, ...] = (2.0, 1.8)
    resolution_candidate_max_lines: int = 3
    low_energy_peak_screening_enabled: bool = True
    low_energy_peak_screening_max_energy_keV: float = 4.0
    low_energy_peak_screening_min_intensity: float = 0.0
    low_energy_peak_screening_integration_windows: float = 2.0
    low_energy_peak_screening_background_line_width: tuple[float, float] = (2.0, 2.0)
    low_energy_peak_screening_background_windows_width: float = 1.0


@dataclass
class FitSpectrumResult:
    model: object
    reduced_chisq: float
    fitted_intensities: list
    reference_bg_shift_keV: float | None
    notes: list[str] = field(default_factory=list)
    nfev_by_step: dict[str, int | None] = field(default_factory=dict)
    screened_low_energy_lines: dict[str, float] = field(default_factory=dict)


@dataclass
class RefineFitResult:
    model: object
    reduced_chisq: float
    fitted_intensities: list
    reference_bg_shift_keV: float | None
    selected_resolution_candidate: str
    notes: list[str] = field(default_factory=list)
    nfev_by_step: dict[str, int | None] = field(default_factory=dict)
    screened_low_energy_lines: dict[str, float] = field(default_factory=dict)


def fit_spectrum(
    signal,
    *,
    config: FittingProtocolConfig,
    background_signal=None,
    bg_fit_mode: str = "bg_spec",
    bg_elements: Optional[list[str]] = None,
    reference_bg_shift_keV: float = 0.0,
    existing_model=None,
    reuse_existing_model: bool = False,
    store_prefix: str = "eds_fit",
    logger: Callable[[str], None] = print,
) -> FitSpectrumResult:
    protocol = _SpectrumFitProtocol(
        signal=signal,
        config=config,
        background_signal=background_signal,
        bg_fit_mode=bg_fit_mode,
        bg_elements=bg_elements or [],
        reference_bg_shift_keV=reference_bg_shift_keV,
        model=existing_model,
        store_prefix=store_prefix,
        logger=logger,
    )
    protocol.prepare_model(reuse_existing_model=reuse_existing_model)
    notes = []
    if config.reference_bg_scale_prefit_enabled and protocol.instrument is not None:
        notes.append(protocol.prefit_reference_bg_scale_masked())
    if config.low_energy_peak_screening_enabled:
        notes.append(protocol.apply_low_energy_peak_screening())
    notes.append(protocol.run_initial_bounded_fit())
    return FitSpectrumResult(
        model=protocol.model,
        reduced_chisq=protocol.chi2r(),
        fitted_intensities=protocol.model.get_lines_intensity(),
        reference_bg_shift_keV=protocol.reference_bg_shift_keV(),
        notes=notes,
        nfev_by_step=dict(protocol.nfev_by_step),
        screened_low_energy_lines=dict(protocol.screened_low_energy_lines),
    )


def refine_fit(
    signal,
    model,
    *,
    config: FittingProtocolConfig,
    background_signal=None,
    bg_fit_mode: str = "bg_spec",
    bg_elements: Optional[list[str]] = None,
    reference_bg_shift_keV: float = 0.0,
    store_prefix: str = "eds_refine",
    logger: Callable[[str], None] = print,
) -> RefineFitResult:
    protocol = _SpectrumFitProtocol(
        signal=signal,
        config=config,
        background_signal=background_signal,
        bg_fit_mode=bg_fit_mode,
        bg_elements=bg_elements or [],
        reference_bg_shift_keV=reference_bg_shift_keV,
        model=model,
        store_prefix=store_prefix,
        logger=logger,
    )
    if protocol.model is None:
        raise ValueError("refine_fit() requires an existing fitted model")

    notes = []
    if config.low_energy_peak_screening_enabled:
        notes.append(protocol.apply_low_energy_peak_screening())
    notes.append(protocol.calibrate_offset())
    notes.append(protocol.refit_linear_terms())
    if protocol.instrument is not None:
        notes.append(protocol.refine_reference_bg_shift_masked())
        notes.append(protocol.refit_linear_terms())
    selected_candidate, note = protocol.calibrate_resolution_candidate_search()
    notes.append(note)
    return RefineFitResult(
        model=protocol.model,
        reduced_chisq=protocol.chi2r(),
        fitted_intensities=protocol.model.get_lines_intensity(),
        reference_bg_shift_keV=protocol.reference_bg_shift_keV(),
        selected_resolution_candidate=selected_candidate,
        notes=notes,
        nfev_by_step=dict(protocol.nfev_by_step),
        screened_low_energy_lines=dict(protocol.screened_low_energy_lines),
    )


class _SpectrumFitProtocol:
    def __init__(
        self,
        *,
        signal,
        config: FittingProtocolConfig,
        background_signal,
        bg_fit_mode: str,
        bg_elements: list[str],
        reference_bg_shift_keV: float,
        model,
        store_prefix: str,
        logger: Callable[[str], None],
    ):
        self.signal = signal
        self.config = config
        self.background_signal = background_signal
        self.bg_fit_mode = bg_fit_mode
        self.bg_elements = list(bg_elements)
        self.model = model
        self.store_prefix = store_prefix
        self.logger = logger
        self._snapshot_counter = 0
        self._sample_elements = list(signal.metadata.get_item("Sample.elements", default=[]))
        self._reference_bg_shift_keV = float(reference_bg_shift_keV)
        self.nfev_by_step: dict[str, int | None] = {}
        self.screened_low_energy_lines: dict[str, float] = {}
        self._last_fit_step_name: str | None = None

    @property
    def instrument(self):
        if self.model is None:
            return None
        for component in self.model:
            if component.name == "instrument":
                return component
        return None

    def reference_bg_shift_keV(self) -> float | None:
        instrument = self.instrument
        if instrument is None:
            return None
        return float(instrument.shift.value)

    def energy_axis(self) -> np.ndarray:
        return self.signal.axes_manager.signal_axes[0].axis

    def chi2r(self) -> float:
        data = self.model.red_chisq.data
        return float(data.item() if hasattr(data, "item") else data)

    def prepare_model(self, *, reuse_existing_model: bool):
        self.signal.set_elements(self._desired_model_elements())
        self.signal.set_microscope_parameters(energy_resolution_MnKa=self.config.initial_resolution_eV)
        if self.background_signal is not None:
            self.background_signal.set_microscope_parameters(energy_resolution_MnKa=self.config.initial_resolution_eV)

        if self.model is None or not reuse_existing_model:
            previous_model = self.model
            self.model = self._build_model()
            self._seed_model_from_previous(previous_model)
        else:
            self._update_existing_model_elements_inplace()

        self._restore_model_state_hygiene()

    def run_initial_bounded_fit(self) -> str:
        if self.model is None:
            raise ValueError("No model prepared for fitting")
        self.model.enable_xray_lines()
        self.model.free_background()
        self._fix_xray_line_energies()
        self._fix_xray_line_widths()
        self._apply_screening_constraints_to_model()
        instrument = self.instrument
        if instrument is not None:
            instrument.shift.free = False
            instrument.yscale.free = True
            instrument.xscale.free = False
        with small_signal_numexpr():
            with self.temporary_signal_range():
                self._fit_current_model("initial_fit", optimizer="trf", bounded=True)
        chisq = self.chi2r()
        nfev = self.nfev_by_step.get(self._last_fit_step_name)
        nfev_text = f", nfev: {nfev}" if nfev is not None else ""
        self.logger(f"Fitting element lines and polynomial baseline... chi2r: {chisq:.2f}{nfev_text}")
        return f"Initial bounded fit. chi2r={chisq:.3f}{nfev_text}"

    def prefit_reference_bg_scale_masked(self) -> str:
        instrument = self.instrument
        if instrument is None:
            return "No reference background component"

        previous_states = self._capture_parameter_states()
        try:
            self._set_all_parameters_free(False)
            instrument.shift.free = False
            instrument.yscale.free = True
            instrument.xscale.free = False
            with small_signal_numexpr():
                with self.temporary_signal_range(
                    exclude_sample_half_width_keV=self.config.ignore_sample_half_width_keV
                ):
                    self._fit_current_model("reference_bg_scale_prefit", optimizer="trf", bounded=True)
        finally:
            self._restore_parameter_states(previous_states)
            self._restore_model_state_hygiene()

        scale = float(instrument.yscale.value)
        shift = float(instrument.shift.value)
        message = (
            f"Prefitting reference background scale (sample elements excluded)... "
            f"Scale: {scale:.4f}, Shift: {shift:.6f} keV"
        )
        nfev = self.nfev_by_step.get(self._last_fit_step_name)
        if nfev is not None:
            message += f", nfev: {nfev}"
        self.logger(message)
        return message

    def apply_low_energy_peak_screening(self) -> str:
        if self.model is None:
            return "Low-energy peak screening skipped: no model"

        primary_lines = self._low_energy_primary_line_names()
        if not primary_lines:
            return "Low-energy peak screening skipped: no low-energy lines"

        try:
            background_windows = self.signal.estimate_background_windows(
                line_width=list(self.config.low_energy_peak_screening_background_line_width),
                windows_width=self.config.low_energy_peak_screening_background_windows_width,
                xray_lines=primary_lines,
            )
            intensities = self.signal.get_lines_intensity(
                xray_lines=primary_lines,
                integration_windows=self.config.low_energy_peak_screening_integration_windows,
                background_windows=background_windows,
                plot_result=False,
            )
        except Exception as exc:
            message = f"Low-energy peak screening skipped: peak sums failed ({exc})"
            self.logger(message)
            return message

        evidence = self._line_intensity_map(intensities)
        existing_screened = self._fixed_zero_low_energy_primary_line_names()
        self.screened_low_energy_lines = {
            line: float(evidence.get(line, self.config.low_energy_peak_screening_min_intensity))
            for line in existing_screened
        }
        self.screened_low_energy_lines.update({
            line: float(evidence[line])
            for line in primary_lines
            if evidence.get(line, 0.0) <= self.config.low_energy_peak_screening_min_intensity
        })
        self._apply_screening_constraints_to_model()

        kept = [line for line in primary_lines if line not in self.screened_low_energy_lines]
        screened = ", ".join(f"{line}={value:.3g}" for line, value in self.screened_low_energy_lines.items())
        kept_text = ", ".join(kept) if kept else "none"
        if screened:
            message = (
                "Low-energy peak screening... "
                f"fixed screened lines at zero: {screened}; kept: {kept_text}"
            )
        else:
            message = f"Low-energy peak screening... all {len(primary_lines)} low-energy primary lines kept"
        self.logger(message)
        return message

    def calibrate_offset(self) -> str:
        instrument = self.instrument
        initial_offset = self.offset_keV()
        initial_chi2 = self.chi2r()
        if instrument is not None:
            instrument.shift.free = False
        with small_signal_numexpr():
            with self.temporary_signal_range():
                self.model.calibrate_energy_axis(calibrate="offset")
        chisq = self.chi2r()
        offset = self.offset_keV()
        message = (
            f"Fitting overall offset... {offset:.6f} keV "
            f"(delta = {(offset - initial_offset) * 1000:+.2f} eV). "
            f"chi2r: {chisq:.2f} (delta = {chisq - initial_chi2:+.2f}, {self._format_delta_percent(chisq, initial_chi2)})"
        )
        self.logger(message)
        return message

    def refine_reference_bg_shift_masked(self) -> str:
        instrument = self.instrument
        if instrument is None:
            return "No reference background component"

        initial_shift = float(instrument.shift.value)
        previous_states = self._capture_parameter_states()
        try:
            self._set_all_parameters_free(False)
            instrument.shift.free = True
            instrument.yscale.free = True
            instrument.xscale.free = False
            with small_signal_numexpr():
                with self.temporary_signal_range(exclude_sample_half_width_keV=self.config.ignore_sample_half_width_keV):
                    self._fit_current_model("reference_bg_shift", optimizer="lm", bounded=False)
        finally:
            self._restore_parameter_states(previous_states)
            self._apply_screening_constraints_to_model()

        self._reference_bg_shift_keV = float(instrument.shift.value)
        message = (
            f"Fitting reference background shift... {instrument.shift.value:.6f} keV "
            f"(delta = {(instrument.shift.value - initial_shift) * 1000:+.2f} eV). "
            f"masked BG-window chi2r: {self.chi2r():.2f}"
        )
        self.logger(message)
        return message

    def refit_linear_terms(self) -> str:
        instrument = self.instrument
        previous_states = self._capture_parameter_states()
        try:
            self._set_all_parameters_free(False)
            for component in self.xray_components():
                if component.A.twin is None and not self._is_screened_low_energy_component(component):
                    component.A.free = True
            for component in self.polynomial_components():
                component.set_parameters_free()
            if instrument is not None:
                instrument.yscale.free = True
                instrument.shift.free = False
                instrument.xscale.free = False
            self._fix_xray_line_energies()
            self._fix_xray_line_widths()
            self._apply_screening_constraints_to_model()
            with small_signal_numexpr():
                with self.temporary_signal_range():
                    self._fit_current_model("linear_refit", optimizer="trf", bounded=True)
        finally:
            self._restore_parameter_states(previous_states)
            self._restore_model_state_hygiene()

        chisq = self.chi2r()
        nfev = self.nfev_by_step.get(self._last_fit_step_name)
        nfev_text = f", nfev: {nfev}" if nfev is not None else ""
        self.logger(f"Re-fitting amplitudes, baseline, and reference BG scale... chi2r: {chisq:.2f}{nfev_text}")
        return f"Linear re-fit. chi2r={chisq:.3f}{nfev_text}"

    def calibrate_resolution_candidate_search(self) -> tuple[str, str]:
        baseline_state = self.capture_state("resolution_base")
        best_state = baseline_state
        best_name = "skip"
        best_score = self._score_current_state()
        notes = [f"skip: chi2r={self.chi2r():.3f}, res={self.resolution_eV():.2f} eV, score={best_score:.3f}"]

        for label, lines in self.resolution_line_candidates():
            self.restore_state(baseline_state)
            self.calibrate_resolution_locked(lines)
            self.refit_linear_terms()
            score = self._score_current_state()
            notes.append(
                f"{label}({','.join(lines)}): chi2r={self.chi2r():.3f}, "
                f"res={self.resolution_eV():.2f} eV, score={score:.3f}"
            )
            if score < best_score:
                best_score = score
                best_name = label
                best_state = self.capture_state(f"resolution_best_{label}")

        self.restore_state(best_state)
        message = "Resolution candidate search selected " + best_name + ". " + " | ".join(notes)
        self.logger(message)
        return best_name, message

    def calibrate_resolution_locked(self, selected_lines: list[str]) -> str:
        if not selected_lines:
            return "No resolution lines selected"
        previous_states = self._capture_parameter_states()
        try:
            self._set_all_parameters_free(False)
            self.model._twin_xray_lines_width(selected_lines)
            for name in selected_lines[1:]:
                self.model[name].sigma.free = False
            with small_signal_numexpr():
                with self.temporary_signal_range():
                    self._fit_current_model(f"resolution_{selected_lines[0]}", optimizer="lm", bounded=False)
            self._fix_xray_line_widths()
            resolution = self.set_energy_resolution_from_reference_line(selected_lines[0])
        finally:
            self._restore_parameter_states(previous_states)
            self._restore_model_state_hygiene()
        return f"Locked one-parameter resolution calibration on {', '.join(selected_lines)} -> {resolution:.2f} eV"

    def capture_state(self, suffix: str) -> dict:
        snapshot_name = self._snapshot_name(suffix)
        self.model.store(snapshot_name)
        axis = self.signal.axes_manager.signal_axes[0]
        return {
            "snapshot_name": snapshot_name,
            "offset_keV": float(axis.offset),
            "scale_keV": float(axis.scale),
            "resolution_eV": self.resolution_eV(),
            "reference_bg_shift_keV": self.reference_bg_shift_keV(),
        }

    def restore_state(self, state: dict):
        self.model = self.signal.models.restore(state["snapshot_name"])
        axis = self.signal.axes_manager.signal_axes[0]
        axis.offset = float(state["offset_keV"])
        axis.scale = float(state["scale_keV"])
        self.signal.set_microscope_parameters(energy_resolution_MnKa=float(state["resolution_eV"]))
        instrument = self.instrument
        if instrument is not None and state.get("reference_bg_shift_keV") is not None:
            instrument.shift.value = float(state["reference_bg_shift_keV"])
            self._reference_bg_shift_keV = float(state["reference_bg_shift_keV"])
        self._restore_model_state_hygiene()

    def resolution_line_candidates(self) -> list[tuple[str, list[str]]]:
        candidates: list[tuple[str, list[str]]] = []
        strong_mixed = self.strong_alpha_lines()
        if strong_mixed:
            candidates.append(("mixed_strong", strong_mixed))
        seen = {tuple(strong_mixed)}
        for max_energy_keV in self.config.resolution_candidate_max_energy_keV:
            lines = self.strong_alpha_lines(max_energy_keV=max_energy_keV)
            key = tuple(lines)
            if lines and key not in seen:
                label = "low_energy" if max_energy_keV == self.config.resolution_candidate_max_energy_keV[0] else "very_low_energy"
                candidates.append((label, lines))
                seen.add(key)
        return candidates

    def strong_alpha_lines(self, max_energy_keV: float | None = None) -> list[str]:
        axis_max = float(self.energy_axis().max())
        if max_energy_keV is None:
            max_energy_keV = axis_max
        candidates: list[tuple[float, float, str]] = []
        for component in self.xray_components():
            name = component.name
            if not name.endswith(("Ka", "La", "Ma")):
                continue
            if not getattr(component, "active", True):
                continue
            if self._is_screened_low_energy_component(component):
                continue
            energy = float(component.centre.value)
            if energy < self.config.resolution_candidate_min_energy_keV or energy > min(axis_max, max_energy_keV):
                continue
            amplitude = max(float(component.A.value), 0.0)
            candidates.append((amplitude, energy, name))
        candidates.sort(reverse=True)
        selected: list[tuple[float, str]] = []
        for amplitude, energy, name in candidates:
            if any(abs(energy - other_energy) < 0.12 for other_energy, _ in selected):
                continue
            selected.append((energy, name))
            if len(selected) >= self.config.resolution_candidate_max_lines:
                break
        if selected:
            return [name for _, name in selected]
        fallback = [
            component.name
            for component in self.xray_components()
            if component.name.endswith(("Ka", "La", "Ma"))
            and float(component.centre.value) <= min(axis_max, max_energy_keV)
            and not self._is_screened_low_energy_component(component)
        ]
        return fallback[: self.config.resolution_candidate_max_lines]

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

    def resolution_eV(self) -> float:
        return float(
            self.signal.metadata.get_item(
                "Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa",
                default=self.config.initial_resolution_eV,
            )
        )

    def offset_keV(self) -> float:
        return float(self.signal.axes_manager.signal_axes[0].offset)

    def xray_components(self) -> list:
        return [component for component in self.model if hasattr(component, "A") and hasattr(component, "centre") and hasattr(component, "sigma")]

    def polynomial_components(self) -> list:
        return [component for component in self.model.background_components if component.name != "instrument"]

    def _score_current_state(self) -> float:
        resolution = self.resolution_eV()
        excess = 0.0
        if resolution < self.config.expected_resolution_min_eV:
            excess = self.config.expected_resolution_min_eV - resolution
        elif resolution > self.config.expected_resolution_max_eV:
            excess = resolution - self.config.expected_resolution_max_eV
        return self.chi2r() + self.config.resolution_score_penalty * (excess ** 2)

    def _build_model(self):
        elements = self._desired_model_elements()
        self.signal.set_elements(elements)
        model = self.signal.create_model(auto_add_lines=True, auto_background=False)
        model.add_family_lines()
        model.add_polynomial_background(order=self.config.background_polynomial_order)
        if self.bg_fit_mode == "bg_spec":
            if self.background_signal is None:
                raise ValueError("bg_spec mode requires a reference background signal")
            comp_bg = hs.model.components1D.ScalableFixedPattern(self.background_signal)
            comp_bg.name = "instrument"
            comp_bg.isbackground = True
            comp_bg.xscale.free = False
            comp_bg.shift.free = False
            comp_bg.shift.value = self._reference_bg_shift_keV
            comp_bg.yscale.bmin = self.config.amplitude_bmin
            model.append(comp_bg)
            model.background_components.append(comp_bg)
        self._set_amplitude_bounds(model)
        self._fix_xray_line_energies(model)
        self._fix_xray_line_widths(model)
        return model

    def _desired_model_elements(self) -> list[str]:
        desired = list(self._sample_elements)
        if self.bg_fit_mode == "bg_elements":
            for element in self.bg_elements:
                if element not in desired:
                    desired.append(element)
        return desired

    def _update_existing_model_elements_inplace(self):
        desired_model_elements = self._desired_model_elements()
        self.signal.set_elements(desired_model_elements)
        self.model.signal.set_elements(desired_model_elements)

        removable = []
        for component in list(self.model):
            if getattr(component, "isbackground", False):
                continue
            if self._component_element(component) not in desired_model_elements:
                removable.append(component)
        if removable:
            self.model.remove(removable)

        self.model.add_family_lines()
        self._set_amplitude_bounds(self.model)
        self._restore_model_state_hygiene()

    def _seed_model_from_previous(self, previous_model):
        if self.model is None or previous_model is None:
            return
        previous_components = self._component_map(previous_model)
        for component in self.model:
            previous_component = previous_components.get(component.name)
            if previous_component is None:
                continue
            previous_params = {param.name: param for param in previous_component.parameters}
            for param in component.parameters:
                previous_param = previous_params.get(param.name)
                if previous_param is None:
                    continue
                if param.twin is None:
                    param.value = previous_param.value
                if param.bmin is not None or previous_param.bmin is not None:
                    param.bmin = previous_param.bmin
                if param.bmax is not None or previous_param.bmax is not None:
                    param.bmax = previous_param.bmax
                param.assign_current_value_to_all()

    @staticmethod
    def _component_map(model) -> dict[str, object]:
        return {component.name: component for component in model}

    @staticmethod
    def _component_element(component) -> Optional[str]:
        if hasattr(component, "element"):
            return component.element
        if hasattr(component, "name"):
            name_parts = component.name.split("_")
            if len(name_parts) >= 2:
                return name_parts[0]
        return None

    def _restore_model_state_hygiene(self):
        if self.model is None:
            return
        for component in self.model:
            if self._is_xray_line_component(component):
                component.sigma.bmin = self.config.amplitude_bmin
                if hasattr(component, "A"):
                    component.A.bmin = self.config.amplitude_bmin
        self._apply_screening_constraints_to_model()

    @staticmethod
    def _is_xray_line_component(component) -> bool:
        return hasattr(component, "A") and hasattr(component, "centre") and hasattr(component, "sigma")

    def _set_amplitude_bounds(self, model):
        for component in model:
            if hasattr(component, "A"):
                component.A.bmin = self.config.amplitude_bmin
                if component.A.value < self.config.amplitude_bmin:
                    component.A.value = self.config.amplitude_bmin

    def _fix_xray_line_energies(self, model=None):
        target = model or self.model
        for component in target:
            if self._is_xray_line_component(component):
                component.centre.free = False

    def _fix_xray_line_widths(self, model=None):
        target = model or self.model
        for component in target:
            if self._is_xray_line_component(component):
                component.sigma.free = False

    def _set_all_parameters_free(self, free: bool):
        for component in self.model:
            for parameter in component.parameters:
                parameter.free = free
        self._apply_screening_constraints_to_model()

    def _capture_parameter_states(self):
        return [
            (parameter, parameter.free, parameter.twin, parameter.bmin, parameter.bmax)
            for component in self.model
            for parameter in component.parameters
        ]

    @staticmethod
    def _restore_parameter_states(states):
        for parameter, free, twin, bmin, bmax in states:
            parameter.free = free
            parameter.twin = twin
            parameter.bmin = bmin
            parameter.bmax = bmax

    def _fit_current_model(self, step_name: str, **kwargs):
        info = self.model.fit(return_info=True, **kwargs)
        key = self._unique_step_name(step_name)
        self.nfev_by_step[key] = self._fit_info_nfev(info)
        self._last_fit_step_name = key
        return info

    def _unique_step_name(self, step_name: str) -> str:
        if step_name not in self.nfev_by_step:
            return step_name
        index = 2
        while f"{step_name}_{index}" in self.nfev_by_step:
            index += 1
        return f"{step_name}_{index}"

    @staticmethod
    def _fit_info_nfev(info) -> int | None:
        if info is None:
            return None
        if isinstance(info, dict):
            value = info.get("nfev")
        else:
            value = getattr(info, "nfev", None)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _low_energy_primary_line_names(self) -> list[str]:
        lines = []
        max_energy = float(self.config.low_energy_peak_screening_max_energy_keV)
        for component in self.xray_components():
            if not self._is_primary_peak_screening_component(component):
                continue
            if float(component.centre.value) <= max_energy:
                lines.append(component.name)
        return lines

    def _fixed_zero_low_energy_primary_line_names(self) -> list[str]:
        lines = []
        for component in self.xray_components():
            if not self._is_primary_peak_screening_component(component):
                continue
            if component.name not in self._low_energy_primary_line_names():
                continue
            if component.A.free:
                continue
            if abs(float(component.A.value) - self.config.amplitude_bmin) <= 1e-12:
                lines.append(component.name)
        return lines

    def _is_primary_peak_screening_component(self, component) -> bool:
        if not self._is_xray_line_component(component):
            return False
        if component.A.twin is not None:
            return False
        return component.name.endswith(("Ka", "La", "Ma"))

    def _is_screened_low_energy_component(self, component) -> bool:
        if not self._is_xray_line_component(component):
            return False
        if component.name in self.screened_low_energy_lines:
            return True
        twin = getattr(component.A, "twin", None)
        for line_name in self.screened_low_energy_lines:
            try:
                parent = self.model[line_name]
            except Exception:
                continue
            if parent.A is twin:
                return True
        return False

    def _apply_screening_constraints_to_model(self):
        if self.model is None or not self.screened_low_energy_lines:
            return
        for component in self.xray_components():
            if not self._is_screened_low_energy_component(component):
                continue
            component.A.free = False
            component.A.bmin = self.config.amplitude_bmin
            if component.A.twin is None:
                component.A.value = self.config.amplitude_bmin
                component.A.assign_current_value_to_all()

    @staticmethod
    def _line_intensity_map(intensity_signals: list) -> dict[str, float]:
        values: dict[str, float] = {}
        for intensity in intensity_signals:
            lines = intensity.metadata.get_item("Sample.xray_lines", default=[])
            if lines:
                line = lines[0]
            else:
                title = intensity.metadata.get_item("General.title", default="")
                match = re.search(r":\s*([A-Za-z0-9_]+)\s+at", title)
                if match is None:
                    continue
                line = match.group(1)
            values[line] = float(np.asarray(intensity.data).squeeze())
        return values

    def _snapshot_name(self, suffix: str) -> str:
        self._snapshot_counter += 1
        return f"{self.store_prefix}_{suffix}_{self._snapshot_counter}"

    @contextmanager
    def temporary_signal_range(self, exclude_sample_half_width_keV: float = 0.0):
        previous_mask = np.copy(getattr(self.model, "_channel_switches", []))
        lower, upper = self._get_fit_range_bounds()
        self.model.set_signal_range(lower, upper)
        if exclude_sample_half_width_keV > 0:
            for component in self.model:
                if self._is_sample_line_component(component):
                    centre = getattr(component, "centre", None)
                    if centre is not None:
                        self.model.remove_signal_range(
                            centre.value - exclude_sample_half_width_keV,
                            centre.value + exclude_sample_half_width_keV,
                        )
        try:
            yield
        finally:
            if len(previous_mask):
                self.model.set_signal_range_from_mask(previous_mask)

    def _get_fit_range_bounds(self) -> tuple[float, float]:
        axis = self.signal.axes_manager.signal_axes[0]
        low = max(axis.low_value, float(self.config.fit_energy_min_keV))
        high = min(axis.high_value, float(self.config.fit_energy_max_keV))
        if high <= low:
            raise ValueError(
                f"Invalid fit energy range: lower={low:.3f} keV, upper={high:.3f} keV"
            )
        return low, high

    def _is_sample_line_component(self, component) -> bool:
        return self._component_element(component) in self._sample_elements and self._is_xray_line_component(component)

    @staticmethod
    def _format_delta_percent(current: float, previous: float) -> str:
        if previous == 0:
            return "n/a"
        return f"{((current / previous) - 1) * 100:+.1f}%"
