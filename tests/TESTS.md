# EDS Tool Test Suite

This file documents the current automated and manual tests. Use the
`eds-mini` wrapper for every Python command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fit_protocol_module.py
```

Last updated: 2026-04-23

## Quick Regression Set

Run these after broad fitting, session, background, or GUI-control changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fit_protocol_module.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_refinement_stability.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_parallel_batch_fit.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_bg_handling.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_session_bg_handling.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_refit_on_element_change.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_hspy_roundtrip.py
```

Run syntax checks after editing Python:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python -m py_compile eds_fit_protocol.py eds_session.py eds_tool.py
```

## Test Data

Common files used by tests:

- `grain1_thin.eds`
- `grain1_thick.eds`
- `bg_near_grain1_thin.eds`
- `bg_near_grain1_thick.eds`
- `acac/*.EDS`
- `acac/near_7994.EDS`

Do not modify these data files unless the tests are intentionally updated.

## Core Tests

### `test_fit_protocol_module.py`

Purpose: direct regression test for `eds_fit_protocol.py`.

Checks:

- `fit_spectrum()` and `refine_fit()` on validated multi-spectrum and
  single-spectrum cases.
- Masked reference-background `yscale` prefit is present in `bg_spec`.
- Low-energy peak-sum screening keeps positive-evidence lines active and fixes
  clearly absent low-energy lines at zero.
- `exp_7987` with extra absent `F` stays in the short bounded-fit path.
- `exp_7985` with real `F` keeps `F_Ka` active.
- First refinement improves the initial fit.
- Repeat refinement stays close to the first refined solution.

Output includes:

- Initial, refined, and repeat `chi2r`.
- Runtime for each phase.
- Per-step `nfev`.
- Low-energy between-peak residual metrics.

Run after:

- Any change to `eds_fit_protocol.py`.
- Any change to model-building, parameter bounds, low-energy screening, or
  refinement ordering.

### `test_refinement_stability.py`

Purpose: integrated `EDSSpectrumRecord` refinement and fit-range regression.

Checks:

- `acac/exp_7993.EDS` no longer blows up after refinement.
- A fresh `fit_model()` after refinement reproduces the same good basin.
- Repeat refinement stays stable on validated cases.
- `clear_fit()` resets model and hidden calibration state.
- Fit lower/upper limits and reference-background ignore width propagate to new
  records in a session.
- Applying active fine-tuning to a batch improves the fitted-batch mean
  `chi2r`.

Run after:

- Changes to `EDSSpectrumRecord.fit_model()`.
- Changes to `EDSSpectrumRecord.fine_tune_model()`.
- Changes to fit-range, calibration reset, or session propagation.

### `test_parallel_batch_fit.py`

Purpose: batch execution regression.

Checks:

- `fit_all_models()` reproduces sequential per-spectrum fits.
- `fine_tune_all_models()` keeps every fitted record valid.
- `apply_active_fine_tuning_to_all_models()` completes and preserves model
  results.
- Prints wall-clock timings for sequential baseline and batch operations.

Run after:

- Changes to `EDSSession` batch methods.
- Changes to thread-pool behavior.
- Changes to numexpr thread handling.

### `test_bg_handling.py`

Purpose: background handling and explicit signal-source regression.

Checks:

- Basic record loading and default signal modes.
- `bg_elements` mode fits on CPS-normalized data.
- `bg_spec` mode creates the reference-background fixed-pattern component.
- Raw, measured-background-subtracted, and fitted-reference-subtracted signal
  modes work when available.
- Invalid fitted-reference subtraction raises clear errors.
- `bg_fit_mode="none"` works.

Run after:

- Changes to background fitting modes.
- Changes to display/peak-sum source selection.
- Changes to fitted-reference subtraction.

### `test_session_bg_handling.py`

Purpose: session-level background and source-mode propagation.

Checks:

- Multiple records receive common elements and background settings.
- Explicit display and peak-sum source modes are preserved.
- Invalid fitted-reference source modes are rejected when unavailable.
- Peak-sum intensities use the selected source.

Run after:

- Changes to `EDSSession` setting propagation.
- Changes to display/peak-sum source defaults.

### `test_refit_on_element_change.py`

Purpose: model update behavior when elements change.

Checks:

- Changing sample elements re-fits fitted spectra.
- Changing background elements re-fits when `bg_elements` mode uses them.
- No automatic fit is created when no model exists.
- Session-level element changes update fitted records consistently.

Run after:

- Changes to `set_elements()`.
- Changes to `set_bg_elements()`.
- Changes to in-place model update logic.

### `test_hspy_roundtrip.py`

Purpose: `.hspy` persistence regression.

Checks:

- Exported `.hspy` files preserve EDS Tool state metadata.
- Loading `.hspy` restores fit settings, reference background, source modes,
  model state, `chi2r`, offset, and resolution.
- Re-fitting a loaded `.hspy` remains stable.
- Loader prefers `.hspy` over same-stem `.eds`.

Run after:

- Changes to serialization/deserialization.
- Changes to export formats.
- Changes to load-path preference.

### `test_default_resolution.py`

Purpose: ensure spectra and background spectra default to 128 eV energy
resolution.

Run after:

- Changes to record initialization.
- Changes to background loading.

### `test_fine_tune_timing.py`

Purpose: timing smoke test for the fine-tuning path.

This is older and less complete than `test_fit_protocol_module.py`, but still
useful as a simple performance check for a single spectrum.

Run after:

- Changes expected to affect fitting/refinement runtime.

### `test_calibrate_includes_fit.py`

Purpose: diagnostic test documenting HyperSpy/exSpy calibration behavior.

Use when investigating whether calibration helpers internally run fitting.

### `test_param_locking.py`

Purpose: diagnostic test for parameter free/fixed state during calibration.

Use when investigating slow or unstable refinement. It is not a normal release
gate.

## Standalone Protocol Explorer

`tests/explore_fitting_protocols.py` is an investigation tool rather than a
normal regression test.

It can:

- Build one live exSpy model per case.
- Snapshot and restore candidate states.
- Compare refinement orderings.
- Export per-step CSV traces, fit-call summaries, baseline curves, and anomaly
  JSON files.

Typical command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 `
  python tests\explore_fitting_protocols.py `
  --protocols offset_bgshift_resolution_search `
  --repeat-cycle `
  --remove-readd
```

Read `FITTING_TESTS.md` before using or modifying this script.

## Manual GUI Test

### `test_fine_tune_gui.py`

Purpose: interactive smoke test for GUI fitting and plotting.

Use after GUI changes that affect:

- Fit/refine buttons.
- Plot updates.
- Display source controls.
- Fitted reference-background display.
- Static progress dialog behavior.

Expected behavior:

- Fit and refine controls enable/disable sensibly.
- Long-running operations show the static progress dialog.
- Plot does not get recreated unnecessarily.
- `Fitted reference` view can show fit and residual.
- `Subtract measured` view behaves as signal-only.

## When to Update This File

Update this file when:

- A test is added, removed, or renamed.
- A test's purpose or data set changes.
- A test becomes diagnostic-only or moves into the main regression set.
- Required commands or environment assumptions change.

Keep this file ASCII-only. Avoid checkmarks and other symbols because the
Windows console used for these tests may not encode them reliably.
