# EDS Tool Test Suite

This file documents the current automated and manual tests. Use the
`eds-mini` wrapper for every Python command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fit_protocol_module.py
```

Last updated: 2026-11-27

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
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_hspy_session_loading.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_hspy_gui_loading.py
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

### `test_auto_fit.py` / `test_auto_cli_progress.py`

Run via the eds-mini wrapper after automatic workflow or GUI progress changes.
The former fits small copied grain/acac cases with complete/omitted elements
and with/without reference backgrounds, checks an inflated background, and
tests a valid generated raw spectrum. Writes diagnostics and image QA under
`.tmp/auto_fit_tests`. It checks fit rejection rather than masking.
The latter runs real CLI subprocesses to verify default HSPY output, fitted
plots/tables/snapshots, rejection exit status, and Qt progress/cursor cleanup
on successful and failed saves. It uses temporary copies, not external data.

### `test_intensity_uncertainty.py`

Checks one-standard-error reporting, fixed/twinned/stale/missing error handling,
legacy saved parameters without std, two-significant-digit truncation,
scientific notation, ratio propagation, and full-precision CSV columns with
explicit NaN values. The full command also checks offscreen fitted-table
rendering, tooltips, normalization, selected columns, selection preservation,
and unchanged summed-table export. Saves `.tmp/intensity_uncertainty_table.png`.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_intensity_uncertainty.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_intensity_uncertainty.py --format-only
```

The `--format-only` command runs numerical, notation, saved-parameter and CSV
checks without importing Qt or the scientific fitting stack.

On 2026-11-27, the full GUI/numerical/export checks, session integration,
existing intensity-navigation and HSPY session-loading tests passed after
repairing the mixed Conda/pip environment. A separate read-only check of all
93 saved Clinker spectra verified 843 finite free-amplitude errors and 273
fixed-amplitude NaNs, with full-precision CSV round-trip parity. Original
spectra and saved models were not modified by that check.
The standalone fitting-protocol regression and GUI loading of a copied Clinker
snapshot also passed after the repair. The broader refinement-stability,
parallel-batch and background suites were not rerun for this reporting change.
The CAP CSV was refreshed externally to 90 experiments during validation. A
subsequent real-data GUI smoke check loaded all 90 without refitting, restored
only the active model, and verified numerical GUI CSV parity for 815 finite
standard errors and 265 NaNs.

### `test_intensity_uncertainty_session.py`

Uses a real fit on a temporary spectrum copy. Checks fitted amplitude errors,
fixed parameters with stale errors, session CSV output, lazy HSPY uncertainty
reload/export without constructing models, legacy missing errors, and immutable
source counts. Run after uncertainty/session export or saved-state changes.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_intensity_uncertainty_session.py
```

### `test_startup_diagnostics.py`

Checks stderr restoration after successful and failed imports, propagation of
the original dependency exception, traceback logging, and operation without a
console stream. Does not import Qt or the scientific stack.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_startup_diagnostics.py
```

### `test_cap_import.py`

Uses copied repository spectra in a temporary CAP-style folder tree. Checks
preamble/header parsing, quoted CSV fields, short rows, literal values and
missing columns, experiment paths, HSPY preference, missing-spectrum reporting,
enrichment of existing records, and source/fit/display metadata persistence
through HSPY save/reload. Rejects ordinary spectrum CSVs as CAP input.

### `test_intensity_navigation.py`

Offscreen Qt check for compact Selected/All Save control geometry at startup.
Checks bidirectional summed/fitted/control-window row selection, one plot update
per spectrum change, real displayed-spectrum identity, selection stability
during normalization/column filtering, and clearing selection for missing
results. Writes `.tmp/compact_save_controls.png` for visual layout inspection.

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_cap_import.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_intensity_navigation.py
```

### `test_hspy_session_loading.py`

Creates two different fitted snapshots using temporary copies of repository
spectra. Verifies deferred import and immediate fit results; independent saved
settings in empty/existing sessions; component activation, parameter values,
errors, bounds and twin expressions; channel masks and native diagnostics;
summed intensities; calibrated resolution; embedded-reference restoration after
the copied reference file is removed; snapshot re-export without model building;
duplicate avoidance; unchanged-element no-op; and incremental cancellation.
Run after snapshot, session-load, or model-restoration changes.

### `test_hspy_gui_loading.py`

Offscreen Qt regression with temporary local fixtures. Verifies GUI import never
refits, restores only the active model, populates element/background/fit/source
controls and fitted tables, and saves/reopens plot limits, scale, overlays, and
normalization. An optional `--copied-directory` accepts at most five snapshots
already copied into repository `.tmp`; it refuses original data directories.
It saves changed snapshots only into its own temporary workspace.

Example for a small copied external subset:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_hspy_gui_loading.py --copied-directory .tmp\hspy_reload_gui_subset
```

Known existing regression: on 2026-11-20, `test_refinement_stability.py` failed
its positive-background-shift assertion identically with the original session
module and the snapshot changes. See `FITTING_TESTS.md` for the evidence.

### `test_plot_export.py`

Run after interactive plot-export or display integration changes:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_plot_export.py
```

Uses real HyperSpy/exSpy spectra, fitted background-element and numerical
reference-background models. Checks
PNG/SVG saves for raw, fitted-reference-subtracted, and measured-subtracted
views with linear/log Y axes, physical axes-size preservation, footer bounds,
normalization and reference provenance, failure restoration, and batch export
with/without Y rescaling. Verifies immutable source/fit data and that the active
plot is not recreated. Visual QA images are under `.tmp/plot_export_qa`.

Manual GUI check: click Save plot in Selected after zooming/changing overlays;
check PNG/SVG beside the EDS file. Select normalization in Fitted Line
Intensities and check both raw integrals and ratios. Save plots in All: try
Yes, No, and Cancel and verify the original displayed plot remains unchanged.

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
