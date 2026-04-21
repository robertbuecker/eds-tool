"""
Test script for explicit background handling in EDSSpectrumRecord.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import hyperspy.api as hs

from eds_session import EDSSpectrumRecord


SPEC_FILE = "grain1_thin.eds"
BG_FILE = "bg_near_grain1_thin.eds"

SAMPLE_ELEMENTS = ["Na", "S", "K", "Si", "Cu", "C", "O", "Cl"]
BG_ELEMENTS_OVERLAP = ["Cu", "Au", "Cr", "Sn", "Fe", "Si", "C", "Nb", "Mo"]
BG_ELEMENTS_DISJOINT = ["Au", "Cr", "Sn", "Fe", "Nb", "Mo"]


def _require_files():
    for path in (SPEC_FILE, BG_FILE):
        if not os.path.exists(path):
            raise FileNotFoundError(path)


def test_basic_loading():
    print("\n=== Test 1: Basic Loading ===")
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(SAMPLE_ELEMENTS)
    print(f"Loaded: {rec.name}")
    print(f"Elements: {rec.elements}")
    print(f"Display signal mode: {rec.display_signal_mode}")
    print(f"Peak-sum signal mode: {rec.peak_sum_signal_mode}")
    print("✓ Basic loading test passed")
    return rec


def test_bg_elements_mode(rec):
    print("\n=== Test 2: BG Elements Fit Mode ===")
    rec.set_bg_elements(BG_ELEMENTS_OVERLAP)
    rec.set_bg_fit_mode("bg_elements")
    rec.fit_model()

    assert rec.model is not None, "Model fitting failed"
    assert rec.get_signal_for_fit().metadata.get_item("Signal.quantity") == "X-rays (CPS)"
    assert rec.model.signal.metadata.get_item("Signal.quantity") == "X-rays (CPS)"
    assert not rec.can_use_fitted_reference_bg_subtraction(), "Overlapping BG elements must not allow fitted subtraction"
    print(f"Model fitted successfully with {len(rec.model)} components")
    print("✓ BG elements mode test passed")


def test_bg_spec_mode():
    print("\n=== Test 3: BG Spec Fit Mode ===")
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(SAMPLE_ELEMENTS)
    rec.set_background(hs.load(BG_FILE))
    rec.set_bg_fit_mode("bg_spec")
    rec.fit_model()

    assert rec.model is not None, "Model fitting failed"
    instrument = next((c for c in rec.model if c.name == "instrument"), None)
    assert instrument is not None, "Missing instrument component"
    assert not instrument.xscale.free, "instrument.xscale must stay fixed"
    assert not instrument.shift.free, "instrument.shift must stay fixed during initial fit"
    assert rec.can_use_fitted_reference_bg_subtraction(), "bg_spec fit should enable fitted subtraction"
    assert rec.signal.metadata.get_item("Signal.quantity") == "X-rays (Counts)"
    print(f"Model fitted successfully with {len(rec.model)} components")
    print("✓ BG spec mode test passed")
    return rec


def test_explicit_signal_modes(rec):
    print("\n=== Test 4: Explicit Signal Modes ===")

    rec.set_display_signal_mode("raw")
    rec.set_peak_sum_signal_mode("raw")
    rec.compute_intensities()
    assert rec.intensities is not None, "Raw peak-sum intensities failed"
    assert rec.signal.metadata.get_item("Signal.quantity") == "X-rays (Counts)"
    print("  ✓ Raw mode works")

    rec.set_display_signal_mode("measured_bg_subtracted")
    rec.set_peak_sum_signal_mode("measured_bg_subtracted")
    rec.compute_intensities()
    assert rec.intensities is not None, "Measured BG subtraction peak-sum failed"
    assert rec.signal.metadata.get_item("Signal.quantity") == "X-rays (Counts, Measured BG Subtracted)"
    print("  ✓ Measured background subtraction works")

    rec.set_display_signal_mode("fitted_reference_bg_subtracted")
    rec.set_peak_sum_signal_mode("fitted_reference_bg_subtracted")
    rec.compute_intensities()
    assert rec.intensities is not None, "Fitted external BG subtraction peak-sum failed"
    assert rec.signal.metadata.get_item("Signal.quantity") == "X-rays (Counts, Fitted Reference BG Subtracted)"
    print("  ✓ Fitted reference BG subtraction works")


def test_invalid_fitted_subtraction():
    print("\n=== Test 5: Invalid Fitted Subtraction Cases ===")

    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(SAMPLE_ELEMENTS)
    try:
        rec.set_bg_correction_mode("subtract_fitted")
    except ValueError:
        print("  ✓ Unfitted record correctly rejects fitted subtraction")
    else:
        raise AssertionError("subtract_fitted should fail without a fitted external background")

    rec.set_bg_elements(BG_ELEMENTS_OVERLAP)
    rec.set_bg_fit_mode("bg_elements")
    rec.fit_model()
    try:
        rec.set_bg_correction_mode("subtract_fitted")
    except ValueError:
        print("  ✓ Overlapping BG/sample elements correctly reject fitted subtraction")
    else:
        raise AssertionError("subtract_fitted should fail for overlapping bg_elements fits")

    rec.set_bg_elements(BG_ELEMENTS_DISJOINT)
    rec.fit_model()
    rec.set_bg_correction_mode("subtract_fitted")
    assert rec.bg_correction_mode == "subtract_fitted"
    print("  ✓ Disjoint bg_elements fit allows fitted subtraction")


def test_additional_background_fit_modes():
    print("\n=== Test 6: Additional Background Fit Modes ===")

    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(SAMPLE_ELEMENTS)
    rec.set_bg_fit_mode("none")
    rec.fit_model()
    assert rec.model is not None, "bg_fit_mode='none' should still fit the sample + polynomial baseline"
    assert not rec.can_use_fitted_reference_bg_subtraction(), "No fitted reference BG should be available in bg_fit_mode='none'"
    print("  âœ“ bg_fit_mode='none' works")

    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(SAMPLE_ELEMENTS)
    rec.set_background(hs.load(BG_FILE))
    rec.set_background_prefit_mode("exclude_sample")
    rec.set_reference_bg_ignore_sample_half_width(0.08)
    rec.fit_model()
    assert rec.model is not None and rec.reduced_chisq is not None, "Exclude-sample BG prefit should complete"
    print("  âœ“ Exclude-sample BG prefit works")

    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(SAMPLE_ELEMENTS)
    rec.set_bg_elements(BG_ELEMENTS_DISJOINT)
    rec.set_bg_fit_mode("bg_elements")
    rec.set_background_prefit_mode("bg_elements_only")
    rec.fit_model()
    assert rec.model is not None and rec.reduced_chisq is not None, "BG-elements-only prefit should complete"
    print("  âœ“ BG-elements-only prefit works")


def main():
    print("=" * 60)
    print("Testing EDSSpectrumRecord Background Handling")
    print("=" * 60)
    _require_files()

    rec = test_basic_loading()
    test_bg_elements_mode(rec)
    rec = test_bg_spec_mode()
    test_explicit_signal_modes(rec)
    test_invalid_fitted_subtraction()
    test_additional_background_fit_modes()

    print("\n" + "=" * 60)
    print("All tests completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
