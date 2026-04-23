"""
Regression checks for the standalone fitting protocol module.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import hyperspy.api as hs
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_fit_protocol import FittingProtocolConfig, fit_spectrum, refine_fit


REPO_ROOT = Path(__file__).resolve().parent.parent
MULTI_BG = REPO_ROOT / "acac" / "near_7994.EDS"
MULTI_ELEMENTS = ["C", "O", "Fe", "Al", "Ga", "Ge", "N"]
MULTI_CASES = {
    "exp_7984": 1.2,
    "exp_7988": 0.5,
    "exp_7989": 2.5,
    "exp_7990": 0.3,
    "exp_7992": 0.4,
    "exp_7993": 1.1,
    "exp_7995": 0.2,
}
LOW_ENERGY_SCREENING_CASES = {
    "exp_7987_with_absent_F": {
        "path": REPO_ROOT / "acac" / "exp_7987.EDS",
        "elements": ["C", "O", "Fe", "Al", "Ga", "Ge", "N", "F", "S"],
        "expected_screened": {"F_Ka", "S_Ka"},
        "expected_kept": {"C_Ka", "N_Ka", "O_Ka"},
        "max_initial_nfev": 25,
        "max_low_energy_abs_residual": 2.0,
    },
    "exp_7985_with_real_F": {
        "path": REPO_ROOT / "acac" / "exp_7985.EDS",
        "elements": ["C", "O", "Fe", "Al", "Ga", "Ge", "N", "F"],
        "expected_screened": {"N_Ka"},
        "expected_kept": {"C_Ka", "F_Ka", "O_Ka"},
        "max_initial_nfev": 25,
        "max_low_energy_abs_residual": 2.5,
    },
}
SINGLE_SPEC = REPO_ROOT / "grain1_thick.eds"
SINGLE_BG = REPO_ROOT / "bg_near_grain1_thick.eds"
SINGLE_ELEMENTS = ["C", "Cl", "Cu", "K", "Na", "O", "S", "Ca"]


def _require_files():
    paths = [MULTI_BG, SINGLE_SPEC, SINGLE_BG]
    paths.extend(REPO_ROOT / "acac" / f"{name}.EDS" for name in MULTI_CASES)
    paths.extend(case["path"] for case in LOW_ENERGY_SCREENING_CASES.values())
    for path in paths:
        if not path.exists():
            raise FileNotFoundError(path)


def _live_time(signal) -> float:
    value = signal.metadata.get_item("Acquisition_instrument.TEM.Detector.EDS.live_time", default=None)
    if value is None or value == 0:
        raise ValueError(f"Missing live time for {signal.metadata.General.title}")
    return float(value)


def _make_cps(signal):
    out = signal.deepcopy()
    out.data = signal.data / _live_time(signal)
    out.metadata.set_item("Signal.quantity", "X-rays (CPS)")
    return out


def _load_case_signal(path: Path, elements: list[str]):
    signal_counts = hs.load(str(path))
    signal_counts.set_microscope_parameters(energy_resolution_MnKa=128.0)
    signal = _make_cps(signal_counts)
    signal.set_elements(elements)
    return signal


def _load_background(path: Path):
    background_counts = hs.load(str(path))
    background_counts.set_microscope_parameters(energy_resolution_MnKa=128.0)
    return _make_cps(background_counts)


def _low_energy_between_peak_metrics(signal, model, max_energy_keV: float = 4.0, line_half_width_keV: float = 0.15):
    energy = signal.axes_manager.signal_axes[0].axis
    mask = (energy >= 0.2) & (energy <= max_energy_keV)
    for component in model:
        if not (hasattr(component, "A") and hasattr(component, "centre")):
            continue
        centre = float(component.centre.value)
        if centre <= max_energy_keV:
            mask &= np.abs(energy - centre) > line_half_width_keV
    residual = np.asarray(signal.data) - np.asarray(model.as_signal().data)
    values = residual[mask]
    return {
        "bins": int(mask.sum()),
        "mean_abs": float(np.mean(np.abs(values))) if values.size else float("nan"),
        "mean": float(np.mean(values)) if values.size else float("nan"),
        "rms": float(np.sqrt(np.mean(values**2))) if values.size else float("nan"),
    }


def _format_nfev(nfev_by_step: dict[str, int | None]) -> str:
    return ", ".join(f"{step}={value}" for step, value in nfev_by_step.items())


def _run_case(name: str, spectrum_path: Path, background_path: Path, elements: list[str], expected_chi2_max: float):
    config = FittingProtocolConfig()
    signal = _load_case_signal(spectrum_path, elements)
    background = _load_background(background_path)

    t0 = time.perf_counter()
    fit_result = fit_spectrum(
        signal,
        config=config,
        background_signal=background,
        bg_fit_mode="bg_spec",
        store_prefix=f"{name}_fit",
    )
    fit_dt = time.perf_counter() - t0
    fit_low_energy = _low_energy_between_peak_metrics(signal, fit_result.model)
    assert any("Prefitting reference background scale" in note for note in fit_result.notes), (
        f"{name}: expected masked reference-BG scale prefit note in fit_spectrum()"
    )
    t1 = time.perf_counter()
    refine_result = refine_fit(
        signal,
        fit_result.model,
        config=config,
        background_signal=background,
        bg_fit_mode="bg_spec",
        reference_bg_shift_keV=fit_result.reference_bg_shift_keV or 0.0,
        store_prefix=f"{name}_refine",
    )
    refine_dt = time.perf_counter() - t1
    refine_low_energy = _low_energy_between_peak_metrics(signal, refine_result.model)
    t2 = time.perf_counter()
    repeat_result = refine_fit(
        signal,
        refine_result.model,
        config=config,
        background_signal=background,
        bg_fit_mode="bg_spec",
        reference_bg_shift_keV=refine_result.reference_bg_shift_keV or 0.0,
        store_prefix=f"{name}_refine_repeat",
    )
    repeat_dt = time.perf_counter() - t2
    repeat_low_energy = _low_energy_between_peak_metrics(signal, repeat_result.model)

    assert refine_result.reduced_chisq < fit_result.reduced_chisq, (
        f"{name}: refinement should improve chi2r, got {fit_result.reduced_chisq} -> {refine_result.reduced_chisq}"
    )
    assert refine_result.reduced_chisq <= expected_chi2_max, (
        f"{name}: refined chi2r {refine_result.reduced_chisq:.3f} exceeds expected maximum {expected_chi2_max:.3f}"
    )
    assert repeat_result.reduced_chisq <= refine_result.reduced_chisq + 0.03, (
        f"{name}: repeat refinement should stay near the first refined result, got "
        f"{refine_result.reduced_chisq:.3f} -> {repeat_result.reduced_chisq:.3f}"
    )
    print(
        f"{name}: fit {fit_result.reduced_chisq:.3f} -> "
        f"refine {refine_result.reduced_chisq:.3f} -> "
        f"repeat {repeat_result.reduced_chisq:.3f} | "
        f"times: fit {fit_dt:.2f}s, refine {refine_dt:.2f}s, repeat {repeat_dt:.2f}s | "
        f"nfev: fit[{_format_nfev(fit_result.nfev_by_step)}], "
        f"refine[{_format_nfev(refine_result.nfev_by_step)}], "
        f"repeat[{_format_nfev(repeat_result.nfev_by_step)}] | "
        f"low-energy between-peaks abs/mean: "
        f"fit {fit_low_energy['mean_abs']:.3f}/{fit_low_energy['mean']:+.3f}, "
        f"refine {refine_low_energy['mean_abs']:.3f}/{refine_low_energy['mean']:+.3f}, "
        f"repeat {repeat_low_energy['mean_abs']:.3f}/{repeat_low_energy['mean']:+.3f}"
    )


def _run_low_energy_screening_case(name: str, case: dict):
    config = FittingProtocolConfig()
    signal = _load_case_signal(case["path"], case["elements"])
    background = _load_background(MULTI_BG)

    t0 = time.perf_counter()
    fit_result = fit_spectrum(
        signal,
        config=config,
        background_signal=background,
        bg_fit_mode="bg_spec",
        store_prefix=f"{name}_fit",
    )
    fit_dt = time.perf_counter() - t0
    low_energy = _low_energy_between_peak_metrics(signal, fit_result.model)
    screened = set(fit_result.screened_low_energy_lines)
    initial_nfev = fit_result.nfev_by_step.get("initial_fit")

    assert case["expected_screened"] <= screened, (
        f"{name}: expected {case['expected_screened']} to be screened, got {screened}"
    )
    assert not (case["expected_kept"] & screened), (
        f"{name}: expected {case['expected_kept']} to remain fit candidates, got screened {screened}"
    )
    assert initial_nfev is not None and initial_nfev <= case["max_initial_nfev"], (
        f"{name}: expected initial bounded fit <= {case['max_initial_nfev']} nfev, got {initial_nfev}"
    )
    assert low_energy["mean_abs"] <= case["max_low_energy_abs_residual"], (
        f"{name}: low-energy between-peaks mean abs residual {low_energy['mean_abs']:.3f} "
        f"exceeds {case['max_low_energy_abs_residual']:.3f}"
    )
    print(
        f"{name}: screened {sorted(screened)} | chi2r {fit_result.reduced_chisq:.3f} | "
        f"fit {fit_dt:.2f}s | nfev [{_format_nfev(fit_result.nfev_by_step)}] | "
        f"low-energy between-peaks abs/mean/rms "
        f"{low_energy['mean_abs']:.3f}/{low_energy['mean']:+.3f}/{low_energy['rms']:.3f}"
    )


def main():
    print("=" * 60)
    print("Testing Standalone Fitting Protocol Module")
    print("=" * 60)
    _require_files()

    for name, max_chi2 in MULTI_CASES.items():
        _run_case(
            name=name,
            spectrum_path=REPO_ROOT / "acac" / f"{name}.EDS",
            background_path=MULTI_BG,
            elements=MULTI_ELEMENTS,
            expected_chi2_max=max_chi2,
        )

    for name, case in LOW_ENERGY_SCREENING_CASES.items():
        _run_low_energy_screening_case(name, case)

    _run_case(
        name="grain1_thick",
        spectrum_path=SINGLE_SPEC,
        background_path=SINGLE_BG,
        elements=SINGLE_ELEMENTS,
        expected_chi2_max=0.2,
    )

    print("\nAll standalone fitting protocol checks passed")


if __name__ == "__main__":
    main()
