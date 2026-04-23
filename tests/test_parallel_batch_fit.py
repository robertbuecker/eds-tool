"""
Test that batch fit/refine/apply paths preserve per-spectrum behavior.

`fit_all_models()` is intentionally sequential because HyperSpy/exspy model
construction is dominated by SymPy-based work that is effectively GIL-bound.
`fine_tune_all_models()` still uses worker threads because it operates on
existing models and benefits from parallel numeric work.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession


SPEC_FILE_1 = "grain1_thin.eds"
SPEC_FILE_2 = "grain1_thick.eds"
BG_FILE = "bg_near_grain1_thin.eds"
ELEMENTS = ["Na", "S", "K", "Si", "Cu", "C", "O", "Cl"]


def _require_files():
    for path in (SPEC_FILE_1, SPEC_FILE_2, BG_FILE):
        if not os.path.exists(path):
            raise FileNotFoundError(path)


def main():
    print("=" * 60)
    print("Testing Batch Fit/Refine")
    print("=" * 60)
    _require_files()

    baseline = EDSSession([SPEC_FILE_1, SPEC_FILE_2])
    baseline.set_elements(ELEMENTS)
    baseline.set_background(BG_FILE)
    baseline.set_bg_fit_mode("bg_spec")
    for rec in baseline.records.values():
        t0 = time.perf_counter()
        rec.fit_model()
        print(f"  sequential {rec.name} fit_model(): {time.perf_counter() - t0:.2f}s")
    baseline_chisq = {name: rec.reduced_chisq for name, rec in baseline.records.items()}

    batch = EDSSession([SPEC_FILE_1, SPEC_FILE_2])
    batch.set_elements(ELEMENTS)
    batch.set_background(BG_FILE)
    batch.set_bg_fit_mode("bg_spec")
    t0 = time.perf_counter()
    batch.fit_all_models()
    print(f"  batch fit_all_models(): {time.perf_counter() - t0:.2f}s")
    batch_chisq = {name: rec.reduced_chisq for name, rec in batch.records.items()}

    for name in baseline_chisq:
        assert abs(batch_chisq[name] - baseline_chisq[name]) < 1e-12, (
            f"Batch fit changed chi2r for {name}: {batch_chisq[name]} vs {baseline_chisq[name]}"
        )
    print("OK fit_all_models reproduces sequential per-spectrum fits")

    t0 = time.perf_counter()
    batch.fine_tune_all_models()
    print(f"  batch fine_tune_all_models(): {time.perf_counter() - t0:.2f}s")
    for name, rec in batch.records.items():
        assert rec.model is not None, f"Batch refine lost the model for {name}"
        assert rec.reduced_chisq is not None, f"Batch refine lost chi2r for {name}"
    print("OK fine_tune_all_models keeps all fitted spectra valid")

    source = batch.active_record
    assert source is not None and source.model is not None
    before = {
        name: rec.reduced_chisq
        for name, rec in batch.records.items()
        if rec is not source and rec.model is not None
    }
    t0 = time.perf_counter()
    batch.apply_active_fine_tuning_to_all_models()
    print(f"  batch apply_active_fine_tuning_to_all_models(): {time.perf_counter() - t0:.2f}s")
    after = {
        name: rec.reduced_chisq
        for name, rec in batch.records.items()
        if rec is not source and rec.model is not None
    }
    for name in before:
        assert after[name] is not None, f"Batch apply lost chi2r for {name}"
    print("OK apply_active_fine_tuning_to_all_models completed successfully")

    print("\nAll batch execution checks passed")


if __name__ == "__main__":
    main()
