"""
Round-trip test for .hspy export/load with preserved EDS Tool fit state.
"""
import os
import shutil
import sys

import hyperspy.api as hs

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSpectrumRecord, EDSSession, _dedupe_preferred_spectrum_paths


SPEC_FILE = "grain1_thin.eds"
BG_FILE = "bg_near_grain1_thin.eds"
ELEMENTS = ["Na", "S", "K", "Si", "Cu", "C", "O", "Cl"]
TMP_DIR = os.path.join("tests", "_tmp_hspy_roundtrip")


def _require_files():
    for path in (SPEC_FILE, BG_FILE):
        if not os.path.exists(path):
            raise FileNotFoundError(path)


def main():
    print("=" * 60)
    print("Testing .hspy round-trip persistence")
    print("=" * 60)
    _require_files()

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    os.makedirs(TMP_DIR, exist_ok=True)

    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(ELEMENTS)
    rec.set_background(hs.load(BG_FILE))
    rec.bg_file = BG_FILE
    rec.set_bg_fit_mode("bg_spec")
    rec.fit_model()
    rec.set_display_signal_mode("fitted_reference_bg_subtracted")
    rec.set_peak_sum_signal_mode("measured_bg_subtracted")

    initial_chisq = rec.reduced_chisq
    initial_resolution = rec.get_energy_resolution()
    initial_offset = rec.get_signal_for_fit().axes_manager.signal_axes[0].offset

    rec.export(folder=TMP_DIR, formats=["hspy"])
    hspy_path = os.path.join(TMP_DIR, f"{rec.name}.hspy")
    assert os.path.exists(hspy_path), ".hspy export did not create a file"
    print(f"Exported round-trip file: {hspy_path}")

    loaded = EDSSpectrumRecord(hspy_path)
    assert loaded.model is not None, "Loaded .hspy record did not restore the fitted model"
    assert loaded._background is not None, "Loaded .hspy record did not restore the reference background"
    assert loaded.bg_fit_mode == "bg_spec", "BG fit mode was not restored"
    assert loaded.display_signal_mode == "fitted_reference_bg_subtracted", "Display mode was not restored"
    assert loaded.peak_sum_signal_mode == "measured_bg_subtracted", "Peak-sum mode was not restored"
    assert loaded.can_use_fitted_reference_bg_subtraction(), "Restored record lost fitted reference BG subtraction"
    assert abs(loaded.reduced_chisq - initial_chisq) < 1e-12, "Reduced chi-square changed during .hspy round-trip"
    assert abs(loaded.get_energy_resolution() - initial_resolution) < 1e-12, "Resolution changed during round-trip"
    assert abs(loaded.get_signal_for_fit().axes_manager.signal_axes[0].offset - initial_offset) < 1e-12, "Offset changed during round-trip"
    print("✓ .hspy load restored fit settings and fitted model state")

    loaded.fit_model()
    assert abs(loaded.reduced_chisq - initial_chisq) < 1e-12, "Re-fitting a loaded .hspy changed the fitted result"
    print("✓ Re-fitting a loaded .hspy preserves the fitted result")

    copied_eds = os.path.join(TMP_DIR, f"{rec.name}.eds")
    shutil.copyfile(SPEC_FILE, copied_eds)
    preferred = _dedupe_preferred_spectrum_paths([copied_eds, hspy_path])
    assert preferred == [os.path.abspath(hspy_path)], "Preferred-path resolution did not choose .hspy over .eds"

    session = EDSSession([copied_eds, hspy_path])
    assert len(session.records) == 1, "Session should only load one preferred spectrum for identical basenames"
    active = session.active_record
    assert active is not None and active.path.lower().endswith(".hspy"), "Session did not prefer .hspy on load"
    print("✓ Session loading prefers .hspy when both .eds and .hspy exist")

    shutil.rmtree(TMP_DIR, ignore_errors=True)
    print("\nAll .hspy round-trip checks passed")


if __name__ == "__main__":
    main()
