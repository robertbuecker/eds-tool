"""
Test that changing elements refits existing models instead of discarding them,
and that fitted models are updated in place when possible.
"""
import os
import sys

import hyperspy.api as hs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession, EDSSpectrumRecord


SPEC_FILE = "grain1_thin.eds"
SPEC_FILE_2 = "grain1_thick.eds"
BG_FILE = "bg_near_grain1_thin.eds"

INITIAL_ELEMENTS = ["Na", "S", "K", "Si"]
UPDATED_ELEMENTS = ["Na", "S", "K", "Si", "Cu", "C", "O", "Cl"]
BG_ELEMENTS = ["Cu", "Au", "Cr", "Sn", "Fe"]


def _require_files():
    for path in (SPEC_FILE, SPEC_FILE_2, BG_FILE):
        if not os.path.exists(path):
            raise FileNotFoundError(path)


def test_refit_on_sample_element_change():
    print("\n=== Test 1: Refit on Sample Element Change ===")
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(INITIAL_ELEMENTS)
    rec.set_background(hs.load(BG_FILE))
    rec.set_bg_fit_mode("bg_spec")

    print(f"Fitting with initial elements: {rec.elements}")
    rec.fit_model()
    assert rec.model is not None, "Initial fit failed"
    initial_model_id = id(rec.model)

    print(f"\nChanging elements to: {sorted(UPDATED_ELEMENTS)}")
    rec.set_elements(UPDATED_ELEMENTS)

    assert rec.model is not None, "Model was lost after element change"
    assert id(rec.model) == initial_model_id, "Expected in-place model update for sample element change"
    assert rec.fitted_intensities is not None, "No fitted intensities after sample element refit"
    print("OK: Sample element change keeps the existing model object and refits it")


def test_refit_on_bg_element_change():
    print("\n=== Test 2: Refit on BG Element Change (bg_elements mode) ===")
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(INITIAL_ELEMENTS)
    rec.set_bg_elements(BG_ELEMENTS[:3])
    rec.set_bg_fit_mode("bg_elements")

    print(f"Fitting with BG elements: {rec.bg_elements}")
    rec.fit_model()
    assert rec.model is not None, "Initial bg_elements fit failed"
    initial_model_id = id(rec.model)
    initial_components = len(rec.model)

    print(f"\nChanging BG elements to: {BG_ELEMENTS}")
    rec.set_bg_elements(BG_ELEMENTS)

    assert rec.model is not None, "Model was lost after BG element change"
    assert id(rec.model) == initial_model_id, "Expected in-place model update for BG element change"
    assert len(rec.model) >= initial_components, "Component count did not grow after adding BG elements"
    assert rec.fitted_intensities is not None, "No fitted intensities after BG element refit"
    print("OK: BG element change keeps the existing model object and refits it")


def test_no_refit_in_bg_spec_mode():
    print("\n=== Test 3: No Refit on BG Element Change (bg_spec mode) ===")
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(INITIAL_ELEMENTS)
    rec.set_background(hs.load(BG_FILE))
    rec.set_bg_fit_mode("bg_spec")
    rec.fit_model()
    assert rec.model is not None, "Initial bg_spec fit failed"
    initial_model_id = id(rec.model)

    rec.set_bg_elements(BG_ELEMENTS)

    assert rec.model is not None, "Model was lost unexpectedly"
    assert id(rec.model) == initial_model_id, "Model changed unexpectedly in bg_spec mode"
    print("OK: BG element change does not refit in bg_spec mode")


def test_no_model_no_fit():
    print("\n=== Test 4: No Model, No Fit ===")
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(INITIAL_ELEMENTS)
    rec.set_elements(UPDATED_ELEMENTS)
    assert rec.model is None, "Model was created unexpectedly"
    print("OK: No automatic fit when no model exists")


def test_session_element_change_refits_all_fitted_models():
    print("\n=== Test 5: Session Element Change Refits Existing Models ===")
    session = EDSSession([SPEC_FILE, SPEC_FILE_2])
    session.set_elements(INITIAL_ELEMENTS)
    session.set_background(BG_FILE)
    session.set_bg_fit_mode("bg_spec")
    session.fit_all_models()

    initial_ids = {name: id(rec.model) for name, rec in session.records.items()}
    session.set_elements(UPDATED_ELEMENTS)

    for name, rec in session.records.items():
        assert rec.model is not None, f"Model missing after session element change for {name}"
        assert id(rec.model) == initial_ids[name], f"Expected in-place model reuse for {name}"
        assert rec.fitted_intensities is not None, f"No fitted intensities after session element change for {name}"
    print("OK: Session element change keeps and refits all existing models")


def main():
    print("=" * 60)
    print("Testing Refit on Element Changes")
    print("=" * 60)
    _require_files()

    tests = [
        test_refit_on_sample_element_change,
        test_refit_on_bg_element_change,
        test_no_refit_in_bg_spec_mode,
        test_no_model_no_fit,
        test_session_element_change_refits_all_fitted_models,
    ]

    passed = 0
    for test in tests:
        test()
        passed += 1

    print("\n" + "=" * 60)
    print(f"All tests PASSED: {passed}/{len(tests)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
