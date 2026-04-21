"""
Regression checks for stable post-refinement fit state and fit-range propagation.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession


MULTI_SPEC = os.path.join("acac", "exp_7993.EDS")
MULTI_BG = os.path.join("acac", "near_7994.EDS")
SPEC_FILE_1 = "grain1_thin.eds"
SPEC_FILE_2 = "grain1_thick.eds"
BG_FILE = "bg_near_grain1_thin.eds"


def _require_files():
    for path in (MULTI_SPEC, MULTI_BG, SPEC_FILE_1, SPEC_FILE_2, BG_FILE):
        if not os.path.exists(path):
            raise FileNotFoundError(path)


def test_refinement_stays_stable_on_reported_multispectrum_case():
    print("\n=== Test 1: Stable Refinement on exp_7993 ===")
    session = EDSSession([MULTI_SPEC])
    session.set_elements(["C", "O", "Fe", "Al", "Ga"])
    session.set_bg_elements(["Cu", "Au", "Cr", "Sn", "Fe", "Si", "C", "Nb", "Mo"])
    session.set_background(MULTI_BG)

    rec = session.active_record
    rec.fit_model()
    initial = rec.reduced_chisq
    rec.fine_tune_model()
    tuned = rec.reduced_chisq
    tuned_shift = rec.reference_bg_shift
    tuned_resolution = rec.get_signal_for_fit().metadata.get_item(
        "Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa"
    )

    rec.fit_model()
    refit = rec.reduced_chisq

    assert tuned < initial, f"Fine-tuning should improve exp_7993: {initial} -> {tuned}"
    assert refit < initial, f"Post-refinement refit should stay improved vs. initial fit: {initial} vs {refit}"
    assert refit <= tuned + 1e-9, f"Rebuilt follow-up fit should not blow up after refinement: {tuned} vs {refit}"
    assert 127 <= tuned_resolution <= 130, f"Resolution calibration must stay inside hard bounds, got {tuned_resolution}"
    assert tuned_shift > 0, "Reference BG shift refinement should be retained"
    print(f"  Initial chi2r: {initial:.3f}")
    print(f"  Tuned chi2r:   {tuned:.3f}")
    print(f"  Refit chi2r:   {refit:.3f}")
    print(f"  Resolution:    {tuned_resolution:.2f} eV")
    print(f"  BG shift:      {tuned_shift:.5f} keV")
    print("✓ Stable refinement test passed")


def test_apply_active_fine_tuning_improves_batch_average():
    print("\n=== Test 2: Apply Active Fine-Tuning to Batch ===")
    paths = sorted(
        os.path.join("acac", name)
        for name in os.listdir("acac")
        if name.lower().startswith("exp_") and name.lower().endswith(".eds")
    )
    session = EDSSession(paths)
    session.set_elements(["C", "O", "Fe", "Al", "Ga"])
    session.set_bg_elements(["Cu", "Au", "Cr", "Sn", "Fe", "Si", "C", "Nb", "Mo"])
    session.set_background(MULTI_BG)
    session.fit_all_models()

    before = {
        name: rec.reduced_chisq
        for name, rec in session.records.items()
        if rec.model is not None
    }
    session.set_active("exp_7993")
    session.active_record.fine_tune_model()
    session.apply_active_fine_tuning_to_all_models()
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
    print("âœ“ Apply-to-all test passed")


def test_clear_fit_and_fit_range_inheritance():
    print("\n=== Test 3: Clear Fit and Fit Range Inheritance ===")
    session = EDSSession([SPEC_FILE_1])
    session.set_elements(["Na", "S", "K", "Si", "Cu", "C", "O", "Cl"])
    session.set_background(BG_FILE)
    session.set_fit_energy_range(0.35, 12.5)
    session.set_reference_bg_ignore_sample_half_width(0.08)

    rec = session.active_record
    default_offset = rec._default_energy_offset
    rec.fit_model()
    initial = rec.reduced_chisq
    rec.fine_tune_model()
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
    print("✓ Clear-fit reset and fit-range inheritance test passed")


def main():
    print("=" * 60)
    print("Testing Refinement Stability and Fit Range Handling")
    print("=" * 60)
    _require_files()

    test_refinement_stays_stable_on_reported_multispectrum_case()
    test_apply_active_fine_tuning_improves_batch_average()
    test_clear_fit_and_fit_range_inheritance()

    print("\n" + "=" * 60)
    print("All refinement stability tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
