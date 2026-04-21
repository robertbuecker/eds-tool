"""
Test script for explicit background handling in EDSSession.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession


SPEC_FILE_1 = "grain1_thin.eds"
SPEC_FILE_2 = "grain1_thick.eds"
BG_FILE = "bg_near_grain1_thin.eds"

SAMPLE_ELEMENTS = ["Na", "S", "K", "Si", "Cu", "C", "O", "Cl"]
BG_ELEMENTS_OVERLAP = ["Cu", "Au", "Cr", "Sn", "Fe", "Si", "C", "Nb", "Mo"]


def _require_files():
    for path in (SPEC_FILE_1, SPEC_FILE_2, BG_FILE):
        if not os.path.exists(path):
            raise FileNotFoundError(path)


def test_session_loading():
    print("\n=== Test 1: Session Loading ===")
    session = EDSSession([SPEC_FILE_1, SPEC_FILE_2])
    print(f"Loaded {len(session.records)} spectra")
    print(f"Spectra: {list(session.records.keys())}")
    print("✓ Session loading test passed")
    return session


def test_basic_propagation(session):
    print("\n=== Test 2: Session Propagation ===")
    session.set_elements(SAMPLE_ELEMENTS)
    session.set_bg_elements(BG_ELEMENTS_OVERLAP)
    session.set_background(BG_FILE)
    session.set_bg_fit_mode("bg_spec")
    session.set_unit("counts")
    session.set_bg_correction_mode("subtract_spectra")

    for name, rec in session.records.items():
        assert rec.elements == sorted(SAMPLE_ELEMENTS), f"Elements not set correctly for {name}"
        assert rec.bg_elements == BG_ELEMENTS_OVERLAP, f"BG elements not set correctly for {name}"
        assert rec._background is not None, f"Background not set for {name}"
        assert rec.bg_fit_mode == "bg_spec", f"BG fit mode not set correctly for {name}"
        assert rec.bg_correction_mode == "subtract_spectra", f"BG correction mode not set correctly for {name}"
        assert rec.signal_unit == "counts", f"Signal unit not set correctly for {name}"
        print(f"  {name}: propagated background settings look correct")

    print("✓ Session propagation test passed")


def test_fitted_subtraction_requires_identifiable_external_background(session):
    print("\n=== Test 3: Fitted Subtraction Availability ===")

    session.set_bg_fit_mode("bg_spec")
    session.fit_all_models()
    session.set_bg_correction_mode("subtract_fitted")

    for name, rec in session.records.items():
        assert rec.bg_correction_mode == "subtract_fitted", f"subtract_fitted was not applied to {name}"
        assert rec.can_use_fitted_reference_bg_subtraction(), f"Fitted subtraction should be available for {name}"
        print(f"  {name}: bg_spec fit enables fitted external background subtraction")

    session.set_bg_fit_mode("bg_elements")
    for name, rec in session.records.items():
        rec.set_bg_elements(BG_ELEMENTS_OVERLAP)
        rec.fit_model()

    try:
        session.set_bg_correction_mode("subtract_fitted")
    except ValueError:
        print("  ✓ Session correctly rejects fitted subtraction for overlapping bg_elements fits")
    else:
        raise AssertionError("subtract_fitted should fail for overlapping bg_elements fits")


def test_peak_sum_uses_selected_mode(session):
    print("\n=== Test 4: Peak-Sum Source Selection ===")
    session.set_bg_fit_mode("bg_spec")
    session.fit_all_models()
    session.set_bg_correction_mode("none")
    session.compute_all_intensities()
    raw_values = {
        name: [float(sig.data[0]) for sig in rec.intensities]
        for name, rec in session.records.items()
    }

    session.set_bg_correction_mode("subtract_spectra")
    session.compute_all_intensities()
    corrected_values = {
        name: [float(sig.data[0]) for sig in rec.intensities]
        for name, rec in session.records.items()
    }

    assert any(raw_values[name] != corrected_values[name] for name in session.records), (
        "Peak-sum intensities should respond to the selected background-subtracted source"
    )
    print("✓ Peak-sum mode selection affects computed intensities")


def test_new_spectrum_inherits_settings():
    print("\n=== Test 5: New Spectrum Inherits Stable Settings ===")
    session = EDSSession([SPEC_FILE_1])
    session.set_elements(SAMPLE_ELEMENTS)
    session.set_bg_elements(BG_ELEMENTS_OVERLAP)
    session.set_background(BG_FILE)
    session.set_bg_fit_mode("bg_spec")
    session.set_unit("counts")
    session.set_bg_correction_mode("subtract_spectra")

    session.load([SPEC_FILE_2])
    new_rec = session.records["grain1_thick"]
    assert new_rec.elements == sorted(SAMPLE_ELEMENTS), "Elements not inherited"
    assert new_rec.bg_elements == BG_ELEMENTS_OVERLAP, "BG elements not inherited"
    assert new_rec.bg_fit_mode == "bg_spec", "BG fit mode not inherited"
    assert new_rec.bg_correction_mode == "subtract_spectra", "BG correction mode not inherited"
    assert new_rec.signal_unit == "counts", "Signal unit not inherited"
    assert new_rec._background is not None, "Background not inherited"
    print("✓ New spectrum inherits stable settings")


def test_display_mode_targets_active_record_only():
    print("\n=== Test 6: Display Mode Targets Active Record Only ===")
    session = EDSSession([SPEC_FILE_1, SPEC_FILE_2])
    session.set_elements(SAMPLE_ELEMENTS)
    session.set_background(BG_FILE)
    session.set_bg_fit_mode("bg_spec")

    active = session.active_record
    active.fit_model()
    session.set_display_signal_mode("fitted_reference_bg_subtracted")

    assert active.display_signal_mode == "fitted_reference_bg_subtracted", (
        "Active fitted record should accept fitted reference BG subtraction"
    )
    other = session.records["grain1_thick"]
    assert other.display_signal_mode == "raw", (
        "Unfitted records must stay on raw display instead of blocking the active fitted view"
    )
    print("✓ Active display mode change no longer fails because of unfitted spectra")


def main():
    print("=" * 60)
    print("Testing EDSSession Background Handling")
    print("=" * 60)
    _require_files()

    session = test_session_loading()
    test_basic_propagation(session)
    test_fitted_subtraction_requires_identifiable_external_background(session)
    test_peak_sum_uses_selected_mode(session)
    test_new_spectrum_inherits_settings()
    test_display_mode_targets_active_record_only()

    print("\n" + "=" * 60)
    print("All EDSSession tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
