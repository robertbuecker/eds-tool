"""
Regression checks for stable post-refinement fit state and fit-range propagation.

Note:
- The default regression set intentionally excludes `exp_7985` / `exp_7987`.
  Those spectra require extra elements (`F` / `S`) and are better handled as
  explicit exploratory cases, not as default stability baselines.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession


MULTI_SPEC = os.path.join("acac", "exp_7993.EDS")
MULTI_BG = os.path.join("acac", "near_7994.EDS")
MULTI_ELEMENTS = ["C", "O", "Fe", "Al", "Ga", "Ge", "N"]
MULTI_REPEAT_CASES = ["exp_7993.EDS", "exp_7995.EDS"]
SPEC_FILE_1 = "grain1_thin.eds"
SPEC_FILE_2 = "grain1_thick.eds"
BG_FILE = "bg_near_grain1_thin.eds"
BG_ELEMENTS = ["Cu", "Au", "Cr", "Sn", "Fe", "Si", "C", "Nb", "Mo"]


def _require_files():
    for path in (MULTI_SPEC, MULTI_BG, SPEC_FILE_1, SPEC_FILE_2, BG_FILE):
        if not os.path.exists(path):
            raise FileNotFoundError(path)


def _structure_signature(rec):
    assert rec.model is not None
    return tuple(
        (
            component.name,
            tuple(
                (
                    param.name,
                    bool(param.free),
                    param.bmin,
                    param.bmax,
                    getattr(getattr(param.twin, "component", None), "name", None)
                    if getattr(param, "twin", None) is not None
                    else None,
                    getattr(param.twin, "name", None)
                    if getattr(param, "twin", None) is not None
                    else None,
                )
                for param in component.parameters
            ),
        )
        for component in rec.model
    )


def test_refinement_stays_stable_on_reported_multispectrum_case():
    print("\n=== Test 1: Stable Refinement on exp_7993 ===")
    session = EDSSession([MULTI_SPEC])
    session.set_elements(MULTI_ELEMENTS)
    session.set_bg_elements(BG_ELEMENTS)
    session.set_background(MULTI_BG)

    rec = session.active_record
    t0 = time.perf_counter()
    rec.fit_model()
    fit_dt = time.perf_counter() - t0
    initial = rec.reduced_chisq
    t1 = time.perf_counter()
    rec.fine_tune_model()
    tune_dt = time.perf_counter() - t1
    tuned = rec.reduced_chisq
    tuned_shift = rec.reference_bg_shift
    tuned_resolution = rec.get_signal_for_fit().metadata.get_item(
        "Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa"
    )

    t2 = time.perf_counter()
    rec.fit_model()
    refit_dt = time.perf_counter() - t2
    refit = rec.reduced_chisq

    assert tuned < initial, f"Fine-tuning should improve exp_7993: {initial} -> {tuned}"
    assert refit < initial, f"Post-refinement refit should stay improved vs. initial fit: {initial} vs {refit}"
    assert refit <= max(tuned * 1.5, tuned + 0.1), (
        f"Follow-up fit should stay in the same good basin after refinement: {tuned} vs {refit}"
    )
    assert 120.0 <= tuned_resolution <= 140.0, (
        f"Refined resolution should stay in a physically reasonable range, got {tuned_resolution}"
    )
    assert tuned_shift > 0, "Reference BG shift refinement should be retained"
    print(f"  Initial chi2r: {initial:.3f}")
    print(f"  Tuned chi2r:   {tuned:.3f}")
    print(f"  Refit chi2r:   {refit:.3f}")
    print(f"  Timings:       fit {fit_dt:.2f}s, refine {tune_dt:.2f}s, refit {refit_dt:.2f}s")
    print(f"  Resolution:    {tuned_resolution:.2f} eV")
    print(f"  BG shift:      {tuned_shift:.5f} keV")
    print("OK stable refinement test passed")


def test_repeat_refinement_does_not_degrade_supported_cases():
    print("\n=== Test 2: Repeat Refinement Stability on Validated Cases ===")
    for filename in MULTI_REPEAT_CASES:
        session = EDSSession([os.path.join("acac", filename)])
        session.set_elements(MULTI_ELEMENTS)
        session.set_bg_elements(BG_ELEMENTS)
        session.set_background(MULTI_BG)

        rec = session.active_record
        t0 = time.perf_counter()
        rec.fit_model()
        fit_dt = time.perf_counter() - t0
        signature_before = _structure_signature(rec)
        initial = rec.reduced_chisq

        t1 = time.perf_counter()
        rec.fine_tune_model()
        first_dt = time.perf_counter() - t1
        first = rec.reduced_chisq
        signature_after = _structure_signature(rec)
        resolution_after_first = rec.get_signal_for_fit().metadata.get_item(
            "Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa"
        )

        t2 = time.perf_counter()
        rec.fine_tune_model()
        second_dt = time.perf_counter() - t2
        second = rec.reduced_chisq
        resolution_after_second = rec.get_signal_for_fit().metadata.get_item(
            "Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa"
        )

        assert signature_after == signature_before, (
            f"Fine-tuning should preserve the model free/fixed/twin structure for {filename}"
        )
        assert first < initial, f"First refinement should improve {filename}: {initial} -> {first}"
        assert second <= first + 0.05, (
            f"Repeated refinement should stay near the first refined result for {filename}: "
            f"{first} -> {second}"
        )
        assert abs(resolution_after_second - resolution_after_first) < 5.0, (
            f"Repeated refinement should not jump to a wildly different retained resolution for {filename}: "
            f"{resolution_after_first} -> {resolution_after_second}"
        )
        print(
            f"  {filename}: {initial:.3f} -> {first:.3f} -> {second:.3f} | "
            f"times: fit {fit_dt:.2f}s, refine1 {first_dt:.2f}s, refine2 {second_dt:.2f}s"
        )
    print("OK repeated refinement remains stable on validated refined solutions")


def test_apply_active_fine_tuning_improves_batch_average():
    print("\n=== Test 3: Apply Active Fine-Tuning to Batch ===")
    paths = sorted(
        os.path.join("acac", name)
        for name in os.listdir("acac")
        if name.lower().startswith("exp_") and name.lower().endswith(".eds")
    )
    session = EDSSession(paths)
    session.set_elements(MULTI_ELEMENTS)
    session.set_bg_elements(BG_ELEMENTS)
    session.set_background(MULTI_BG)
    t0 = time.perf_counter()
    session.fit_all_models()
    fit_all_dt = time.perf_counter() - t0

    before = {
        name: rec.reduced_chisq
        for name, rec in session.records.items()
        if rec.model is not None
    }
    session.set_active("exp_7993")
    t1 = time.perf_counter()
    session.active_record.fine_tune_model()
    active_refine_dt = time.perf_counter() - t1
    t2 = time.perf_counter()
    session.apply_active_fine_tuning_to_all_models()
    apply_dt = time.perf_counter() - t2
    after = {
        name: rec.reduced_chisq
        for name, rec in session.records.items()
        if rec.model is not None
    }

    before_mean = sum(before.values()) / len(before)
    after_mean = sum(after.values()) / len(after)
    assert after_mean < before_mean, (
        f"Applying active fine-tuning should improve the batch mean chi2r: {before_mean} -> {after_mean}"
    )
    print(f"  Batch mean chi2r: {before_mean:.3f} -> {after_mean:.3f}")
    print(f"  Timings:          fit_all {fit_all_dt:.2f}s, active refine {active_refine_dt:.2f}s, apply {apply_dt:.2f}s")
    print("OK apply-to-all test passed")


def test_clear_fit_and_fit_range_inheritance():
    print("\n=== Test 4: Clear Fit and Fit Range Inheritance ===")
    session = EDSSession([SPEC_FILE_1])
    session.set_elements(["Na", "S", "K", "Si", "Cu", "C", "O", "Cl"])
    session.set_background(BG_FILE)
    session.set_fit_energy_range(0.35, 12.5)
    session.set_reference_bg_ignore_sample_half_width(0.08)

    rec = session.active_record
    default_offset = rec._default_energy_offset
    t0 = time.perf_counter()
    rec.fit_model()
    fit_dt = time.perf_counter() - t0
    initial = rec.reduced_chisq
    t1 = time.perf_counter()
    rec.fine_tune_model()
    refine_dt = time.perf_counter() - t1
    assert rec.reduced_chisq < initial, "Fine-tuning should improve the test spectrum before clear_fit()"
    rec.clear_fit()

    reset_resolution = rec.get_signal_for_fit().metadata.get_item(
        "Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa"
    )
    reset_offset = rec.get_signal_for_fit().axes_manager.signal_axes[0].offset
    assert rec.model is None, "clear_fit() should drop the model"
    assert rec.reference_bg_shift == 0.0, "clear_fit() should reset the reference BG shift"
    assert reset_resolution == 128, f"clear_fit() should reset the resolution, got {reset_resolution}"
    assert abs(reset_offset - default_offset) < 1e-12, "clear_fit() should reset the energy offset"

    session.load([SPEC_FILE_2])
    new_rec = session.records["grain1_thick"]
    assert new_rec.fit_energy_min_keV == 0.35, "Fit lower limit should propagate to newly loaded spectra"
    assert new_rec.fit_energy_max_keV == 12.5, "Fit upper limit should propagate to newly loaded spectra"
    assert new_rec.reference_bg_ignore_sample_half_width_keV == 0.08, (
        "Reference BG ignore half-width should propagate to newly loaded spectra"
    )
    print(f"  Timings: fit {fit_dt:.2f}s, refine {refine_dt:.2f}s")
    print("OK clear-fit reset and fit-range inheritance test passed")


def main():
    print("=" * 60)
    print("Testing Refinement Stability and Fit Range Handling")
    print("=" * 60)
    _require_files()

    test_refinement_stays_stable_on_reported_multispectrum_case()
    test_repeat_refinement_does_not_degrade_supported_cases()
    test_apply_active_fine_tuning_improves_batch_average()
    test_clear_fit_and_fit_range_inheritance()

    print("\n" + "=" * 60)
    print("All refinement stability tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
