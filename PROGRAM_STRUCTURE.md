# EDS Tool Program Structure

This document describes the current code structure and design rules for the EDS
Tool. It is intended as onboarding material for humans and agents working on the
repository.

## Scope

EDS Tool is a HyperSpy/exSpy based application for interactive and batch
analysis of TEM EDS spectra. It supports:

- Loading one or many `.eds` or `.hspy` spectra.
- Loading spectra listed by a CAP Data Explorer CSV, retaining source columns.
- Managing sample elements and optional reference/background information.
- Fitting EDS line models with a polynomial baseline and optional reference
  background spectrum.
- Refining energy offset, detector resolution, and reference-background shift.
- Displaying raw, measured-background-subtracted, and fitted-reference views.
- Exporting spectra, plots, intensity tables, and `.hspy` analysis snapshots.

The code is optimized around practical multi-spectrum work: it is common for a
session to contain many spectra from different grains or compounds, while the
same candidate element list is applied to all of them.

## Top-Level Modules

### `eds_tool.py`

GUI and command-line entry point.

Responsibilities:

- Parse CLI arguments.
- Create the Qt control window and HyperSpy/Matplotlib plot window.
- Route user actions to `EDSSession` / `EDSSpectrumRecord`.
- Keep GUI controls synchronized with the active record.
- Provide the non-GUI `--auto` workflow.

The GUI must not contain fitting logic. It should expose state and call the
business objects.

`eds_startup.py` suppresses routine library import chatter using a context
manager that always restores stderr. Failed imports keep their original
exception/traceback and write `eds_tool_startup_error.log` in the temporary
directory. Direct GUI/frozen startup also reports the failure using a native
Windows error dialog, which works even if Qt itself cannot load. Optional Qt
import errors retain their cause for the GUI startup check.

### `eds_session.py`

Business layer for spectra and sessions.

Important classes:

- `EDSSpectrumRecord`: one spectrum, its signals, model, fit settings, fitted
  signals, intensities, and exports.
- `EDSSession`: collection of records plus session-level operations such as
  applying elements, reference backgrounds, fitting all spectra, refining all
  spectra, and exporting combined tables.

### `eds_fit_protocol.py`

Current fitting and refinement implementation.

Responsibilities:

- Build or update an exSpy model for one CPS-normalized spectrum.
- Add the polynomial baseline and optional reference-background component.
- Apply parameter hygiene and amplitude bounds.
- Run the current initial-fit protocol.
- Run the current refinement protocol.
- Return fitted intensities, reduced chi-square, reference-background shift,
  per-step function-evaluation counts, and screening decisions.

New fitting work should start here, not inside the GUI.

### `eds_auto.py`

Guarded `--auto --fit` orchestration, CPS fit-quality diagnostics, first-spectrum
calibration/refinement and transfer to subsequent fits, and headless fitted
figure saving. Poor fits are warned about and cancelled, not silently masked.
Diagnostics and limits are documented in `AUTO_WORKFLOW_README.md`. Each attempt
writes JSON decisions, timings, nfev and between-peak residual metrics. Rejected
models are cleared; a rejected first calibration stops the batch. Auto-mode
optimizer calls use an optional 200-evaluation budget in the protocol config;
normal GUI fitting defaults are unchanged.

GUI fitting/saving uses modal QProgressDialog bars. Known file/spectrum totals
advance on completion; individual fitting stages show a busy indicator and
stage text. Session completion callbacks execute on the caller thread; worker
fit log callbacks never manipulate Qt widgets. Callbacks/cursors are restored
even after failures. Image saves report per-format or per-spectrum completion.

### `eds_plot_export.py`

Interactive plot-image export and fit annotation layout. Saves the actual
displayed Matplotlib artists with an extra footer; retains physical axes size,
limits, scales, legends, and overlays. Uses a temporary Agg canvas and restores
the original canvas, layout, and positions even after a save error. HyperSpy
blit callbacks are blocked during vector saves. Small outer padding prevents
axis decorations being clipped without shrinking the axes.

Batch image export applies the active display mode, unit, overlay controls,
X limits, scales, and figure/axes size to each spectrum. The user chooses fixed
Y limits or per-spectrum scaling within the visible X range. It keeps the
active plot alive and restores record settings. An unavailable background view
is reported for that record, rather than silently changing subtraction mode.

### `eds_cap_import.py`

Reads CAP Data Explorer CSV files with or without their VERSION/header
preamble. Finds `Experiment_name`, preserves every column value as text, and
pads short rows with empty strings. Resolves
`<CSV folder>/<experiment>/EDS/<experiment>_edsauto.{hspy,eds}` first, then
`Experiment_path/EDS/...`, preferring saved HSPY over EDS within each location.
This permits moving the CSV together with its experiment folders. Does not
scan recursively or load spectra while resolving rows. Missing files are
reported; duplicate/invalid experiment names and malformed headers are errors.

`EDSSession.load()` accepts explicit CAP CSV paths through the same interface
as spectrum paths. It stores provenance and all original columns in
`Signal.metadata.CAP_Data_Explorer` (`source_file`, `row_number`, `columns`).
Metadata is attached to source, fit and display signals and retained in HSPY
saves. An already-open matching spectrum can be enriched without reloading or
refitting it. Directory scans still discover only spectra, not unrelated CSVs.

### `tests/`

Regression tests, diagnostics, and standalone fitting-protocol exploration.
See `tests/TESTS.md`.

### `AUTO_WORKFLOW_README.md`

Notes for the non-GUI automatic workflow.

### `FITTING_TESTS.md`

Design reference for fitting approaches that were evaluated, discarded, or
chosen. Read it before changing `eds_fit_protocol.py`.

## Data Model

### `EDSSpectrumRecord`

Each record keeps distinct signal roles:

- `_signal`: immutable source spectrum in counts.
- `_fit_signal`: CPS-normalized copy used for all fitting and model diagnostics.
- `signal`: mutable display/export proxy used for signal-only views.
- `_background`: loaded reference/background spectrum in counts, if any.
- `_background_fit_signal`: CPS-normalized reference/background spectrum.

Model and result fields:

- `model`: exSpy `EDSTEMModel` fitted on `_fit_signal`.
- `has_fit`: availability check that does not materialize a saved model.
- `_pending_fit_state`: saved parameters awaiting first actual model use.
- `intensities`: peak-sum intensities from the selected peak-sum source.
- `fitted_intensities`: model-derived intensities from `model.get_lines_intensity()`.
- `fitted_reference_bg_signal`: fitted reference-background contribution in CPS.
- `fitted_reference_clean_signal`: `_fit_signal` minus fitted reference background.
- `signal_bg` and `signal_clean`: compatibility aliases for the fitted-reference
  signals.
- `reduced_chisq`: current model reduced chi-square.

Fit settings:

- `elements`: sample elements stored in spectrum metadata.
- `bg_fit_mode`: `bg_spec`, `bg_elements`, or `none`.
- `bg_elements`: parasitic/background elements for `bg_elements` mode.
- `background_polynomial_order`: baseline polynomial order.
- `fit_energy_min_keV` / `fit_energy_max_keV`: active model fit range.
- `reference_bg_ignore_sample_half_width_keV`: sample-line exclusion width used
  for masked reference-background shift refinement.
- `reference_bg_shift`: stored reference-background x-shift, in keV.

Display/source settings:

- `signal_unit`: `counts` or `cps` for signal-only views/export.
- `display_signal_mode`: `raw`, `measured_bg_subtracted`, or
  `fitted_reference_bg_subtracted`.
- `peak_sum_signal_mode`: same choices, but for peak-sum intensity computation.

### `EDSSession`

The session owns records and tracks one active record. It propagates settings to
all records where appropriate:

- Elements.
- Reference/background spectrum.
- Background fit mode.
- Background elements.
- Fit range.
- Display and peak-sum defaults.

Session-level fitting rules:

- `fit_all_models()` is sequential. Model creation is Python/SymPy heavy and did
  not benefit from threads or Windows processes.
- `fine_tune_all_models()` uses a capped thread pool because it operates on
  already-built models and can benefit from numeric parallelism.
- Re-fitting existing models after element changes can also use threaded
  numeric work, but initial cold model creation remains sequential.

## Background Handling

User-facing "background" means external or parasitic background, not the
polynomial continuum. The polynomial baseline is always part of the model unless
that code path is explicitly changed.

### `bg_spec`

Preferred mode when a measured reference/background spectrum is available.

Model components:

- Sample x-ray lines.
- Polynomial baseline.
- `ScalableFixedPattern` named `instrument`, built from the CPS-normalized
  reference spectrum.

Parameter rules:

- `instrument.yscale` is fit.
- `instrument.shift` is fixed during the initial fit and refined only in the
  masked reference-background shift step.
- `instrument.xscale` is fixed at 1.0.

### `bg_elements`

Fallback mode when no measured reference spectrum exists but parasitic elements
are known.

Model components:

- Sample x-ray lines.
- Background-element x-ray lines.
- Polynomial baseline.

Fitted-reference subtraction is only available when sample elements and
background elements are disjoint. If they overlap, contributions are not
separable.

### `none`

No external/reference background component. The model still contains the
polynomial baseline.

### Measured Background Subtraction

Measured subtraction is a derived signal view/export option. It subtracts the
loaded reference spectrum scaled by live time. It is not used as fitting input.

### Fitted Reference Subtraction

Fitted-reference subtraction subtracts only the fitted external/reference
background:

- `bg_spec`: the fitted `instrument` component.
- `bg_elements`: disjoint background-element families.

It never subtracts the polynomial baseline.

## Fitting Protocol

All fitting is done in CPS because CPS is intensive with respect to acquisition
time. Counts remain available for signal-only display/export.

The current initial fit in `fit_spectrum()` is:

1. Build/update one live exSpy model on `_fit_signal`.
2. Add family lines and polynomial baseline.
3. Add `instrument` reference-background component for `bg_spec`.
4. Set x-ray amplitude lower bounds to zero.
5. Fix x-ray line centers and widths.
6. If in `bg_spec`, prefit only `instrument.yscale` in sample-excluded windows.
7. Screen low-energy primary x-ray families up to 4 keV using HyperSpy peak-sum
   estimates.
8. Fix non-positive-evidence screened lines at zero.
9. Run bounded `trf` fit for amplitudes, polynomial baseline, and reference
   background scale.

Low-energy screening is deliberately conservative. It is not a full qualitative
peak finder. It only prevents clearly absent low-energy families from entering a
poorly conditioned fit. Positive evidence stays active.

The current refinement in `refine_fit()` is:

1. Re-apply low-energy screening constraints.
2. Calibrate overall energy offset.
3. Bounded linear re-fit of x-ray amplitudes, polynomial baseline, and reference
   background scale.
4. If a reference spectrum is present, fit reference-background shift in
   sample-excluded windows with only `instrument.shift` and `instrument.yscale`
   free.
5. Bounded linear re-fit again.
6. Run candidate resolution calibration from a stored pre-resolution state.
7. Keep the candidate with the best score.

Resolution candidate scoring is:

```text
score = chi2r + resolution_score_penalty * (eV outside expected range)^2
```

The candidate set includes an explicit `skip` option. This avoids forcing a
resolution update when the current state is already best.

## HyperSpy/exSpy Usage Rules

The fitting code should work with one live model whenever possible.

Important rules:

- Do not fit on display-derived signals.
- Do not manually clone model internals to represent candidate states.
- Use `model.store()` and `signal.models.restore()` for model snapshots.
- Restore free/fixed/twin state after temporary calibration steps.
- Re-apply amplitude bounds and screening constraints after any operation that
  changes model state.
- Use `model.fit(..., return_info=True)` when changing fitting code so `nfev`
  can be recorded.
- Keep `instrument.xscale` fixed.
- Keep x-ray line widths fixed except during the locked one-parameter resolution
  calibration.
- Keep x-ray line centers fixed except during explicit offset calibration.

Known exSpy limitations for this model shape:

- `fit_background()` is not reliable with polynomial baseline plus
  `ScalableFixedPattern` reference background.
- Broad free resolution calibration is unstable and can use detector width as a
  background surrogate.
- Helper methods that operate on "all" components can touch polynomial or fixed
  pattern components; prefer explicit x-ray-line paths.

## Plotting Model

HyperSpy plots are dynamic. The GUI should avoid destroying/recreating plots
unless necessary.

Current behavior:

- Raw and fitted-reference-subtracted views can show the live model and residual.
- Fitted-reference-subtracted view keeps the same live model but swaps plot data
  callbacks so signal and fit are shown in the same background-subtracted space.
- Measured-subtracted view is a signal-only derived view; model/residual overlays
  are not directly comparable.
- Showing the reference background before fitting displays the raw reference
  background in CPS.

When changing plotting, preserve the existing live-object approach unless there
is a clear reason not to.

## GUI Organization

The control window is divided into:

- Spectrum Management: loaded spectra, add/remove/save actions, save formats.
- Elements and Background: sample elements, background modeling mode,
  background elements, reference-background file.
- Fitting and Quantification: selected/all actions for peak sums, model fits,
  refinement, clearing fits, plus advanced fit settings.
- Display and Tables: spectrum view, residual/reference-background toggles,
  units, x-range, log scale, intensity table toggles.

The loaded-spectrum list is expected to hold many spectra. Keep it usable and do
not sacrifice it for rarely used controls.
Adjacent file actions use compact Selected/All columns for Remove, Save
spectra and Save plot(s), with shared spectrum/image format entries below.
Startup height respects the layout minimum, keeping actions visible without
reducing the loaded-spectrum list to make room for a vertical button stack.

Summed and fitted intensity dialogs select whole rows by spectrum identity.
Selecting a row changes the active control-window row and displayed spectrum;
control-window selection updates both tables. Programmatic selection is signal
blocked to avoid navigation loops. Normalization/column changes preserve the
selection. Tables without a result for the active spectrum clear selection.

Right-clicking the plot stages candidate elements in the element entry and plot
markers. It does not re-fit until `Apply` is clicked.

Fitted intensity tables show `value(SE)`, where SE is one fitted amplitude
standard error (approximately 68% under a symmetric normal approximation).
The uncertainty has two significant digits; the displayed value is truncated
at the same decimal place. An explicit exponent keeps large/small uncertainties
unambiguous. Fixed/twinned/inactive amplitudes and missing, non-finite or non-positive
standard errors show `(NaN)`, never a misleading zero uncertainty. Tooltips
retain unrounded values. Summed intensity tables keep their existing display.
Normalized uncertainties use first-order ratio propagation, neglect parameter
cross-covariances, and are labeled accordingly. A valid reference/reference
ratio has zero uncertainty; a zero/missing reference produces unavailable data.

`eds_intensity_uncertainty.py` owns shared uncertainty validation, saved-state
extraction, notation, ratio propagation and numerical fitted CSV writing.
`EDSSpectrumRecord.get_fitted_intensity_standard_errors()` reads live amplitude
errors or the already-saved parameter state without restoring a deferred model.
`EDSSession.get_intensity_table(fitted=True)` adds `standard_error` to each row.
Both fitted-table Save CSV and session fitted CSV exports preserve full numeric
precision and place `<line>_standard_error` beside each `<line>` value, with
literal `NaN` for unavailable errors or missing lines. The dialog exports its
selected lines and current normalization. The existing HSPY parameter `std`
fields provide uncertainty persistence; old snapshots without them remain
readable with unavailable errors. No fitting or snapshot schema change is
needed. Spectrum-channel CSVs are independent of fitted-intensity CSVs.

## Saving and Persistence

Supported exports include:

- Spectrum exports such as `csv`, `emsa`, and `hspy`.
- Intensity tables.
- Plot images through HyperSpy/Matplotlib.

The GUI provides `Save plot` (Selected) and `Save plots` (All) alongside a
separate comma-separated plot-format field (default `png, svg`). These write
`<spectrum name>.<format>` beside each source file, replacing existing images.
Selected save takes one click; All asks about Y rescaling and supports
Cancel. Spectrum-save formats and its folder dialog are independent. Existing
Python `export*` APIs are retained for compatibility; GUI actions say Save.

The image footer reports raw/subtracted display handling, fitted sample
elements, fitted line integrals from unrounded results (CPS), background elements or
reference file name/path/filesystem creation date, and polynomial order. If a
normalization line is selected in the Fitted Line Intensities dialog, the footer
adds ratios from unrounded values, explicitly naming the reference line. Missing
or zero normalization references are reported as unavailable. Unfitted spectra
are labeled accordingly. Interactive export does not change automatic workflow
exports or run fitting.

`.hspy` export stores the original count signal plus EDS Tool state metadata.
When both `.eds` and `.hspy` with the same stem are present, loading prefers
`.hspy`.

Snapshot import preserves per-record saved settings, even in an existing
session with different elements/background/defaults. Unsaved raw files still
inherit session settings. Import never applies the GUI element entry or starts
a fit. Duplicate records are detected before reopening their files.

`EDSSession.load()` imports records incrementally with an optional progress
callback and defers model construction. Elements, chi2r, and fitted integrals
are available immediately; accessing `record.model` or plotting that record
restores its live CPS model. Use `record.has_fit` for availability checks and
result-table population. Direct `EDSSpectrumRecord(path)` remains eager by
default; pass `defer_model=True` for deferred construction. GUI import shows
progress with cancellation between files. Models are not fitted on restore.

Transport-only `EDS_Tool.state` metadata is extracted before copying working
signals. It contains an embedded reference spectrum and must not be carried
through every HyperSpy slice or intensity calculation.

Version 2 snapshots preserve component activation, parameter values/errors,
free/fixed flags, bounds, twin relationships and their expressions, channel
masks, native chi-square/degrees of freedom, summed intensities, calibrated
axes/resolution, embedded background, and GUI view settings (overlays, X/Y
limits, Y scale, X-range preset and normalization line). GUI spectrum export
captures the current view; headless export retains any stored view. Fitted
tables align lines by name for mixed-element snapshots and use unrounded
intensities. Version 1 files remain supported; missing native diagnostics are
reconstructed from CPS data, without fitting. Settings never stored by version
1 (such as overlay visibility) cannot be recovered retrospectively.

CLI startup preserves saved detector resolution unless `--energy-resolution`
is explicitly supplied. Raw files retain the 128 eV default.

## Distribution

The cx_Freeze build reads eds_version.py, shared with the window title. Version 0.6 adds fitting session recovery, Data Explorer CSV loading, and auto fitting. distribute_cx.bat uses eds-mini and writes dist-cx/eds-tool-0.6 plus its ZIP. Builds never increment versions implicitly; scripts/bump_version.py changes the authoritative version explicitly.

Do not add the whole `PyQt6` package to the cx_Freeze `packages` list. That
causes cx_Freeze to include every PyQt6 extension module and the corresponding
Qt DLL/QML/plugin families. Include only the required Qt modules explicitly in
`setup_cx.py`.

Pruning walks directories top-down and skips removed trees. Preserve runtime
packages named `testing`, especially scikit-learn's vendored array_api_extra
testing package, which is imported in normal startup. `--package-existing`
reapplies pruning/metadata repair and recreates the ZIP without re-freezing.

The cx_Freeze build script now cleans the current version output directory before
building so stale binaries do not survive package-exclusion changes.

Size trimming currently happens in two ways:

- import-time excludes for unused Qt, Tk, SciPy, and scikit-image modules
- post-build pruning of test/example trees and clearly unused payload such as
  `skimage\data`

Keep `skimage._vendored` and `exspy.data`. HyperSpy/exSpy import them during
startup even though this application does not use the corresponding sample data
or 2D workflows directly.

Qt window icons in frozen builds are resolved from either the module directory
or the executable directory, and the application icon is also set on the
`QApplication` so Matplotlib/Qt child windows inherit it more reliably on
Windows.

Use:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python setup_cx.py build_exe
```

or run `rebuild_cx.bat`.

## Performance Notes

- Use `scripts/with-eds-mini.ps1` for all Python commands.
- The existing scientific/Qt stack in `eds-mini` is pip-managed. On
  2026-11-27 a Conda scikit-learn installation was rolled back because it
  overlaid pip NumPy/SciPy files and introduced an incompatible ICU DLL used
  by Qt. NumPy 2.3.4, SciPy 1.16.2 and cloudpickle 3.1.1 were restored from
  pip wheels; scikit-learn 1.9.1 and its pure-Python dependencies were installed
  through pip. Install additions to this stack through the activated Python's
  pip rather than overlaying it with Conda scientific packages. The earlier
  Conda ipykernel installation was retained.
- The fit protocol temporarily limits numexpr to one thread for small 1D fits.
- Multiprocessing was not useful for normal batch fitting on Windows because
  process startup and scientific-stack import dominate.
- Threads are useful only for already-built model work and are capped.
- Any fitting change should report runtimes and `nfev_by_step`.
- Use the problematic `acac` cases when validating performance:
  `exp_7985`, `exp_7987`, `exp_7989`, and `exp_7993`.

## Test Strategy

Use `tests/TESTS.md` for the full list.

Core checks after fitting changes:

- `python tests/test_fit_protocol_module.py`
- `python tests/test_refinement_stability.py`
- `python tests/test_parallel_batch_fit.py`
- `python tests/test_bg_handling.py`

Run through the wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fit_protocol_module.py
```

## Agent Notes

Before modifying the project:

- Read this file.
- Read `FITTING_TESTS.md` before changing fitting or refinement code.
- Read `tests/TESTS.md` before changing tests.

When implementing:

- Keep fitting logic out of the GUI.
- Keep fitting on CPS `_fit_signal`.
- Keep display/export source choices separate from fit input.
- Use the fitting helper module instead of adding new fitting branches to
  `EDSSpectrumRecord`.
- Avoid Unicode in test output and docs unless there is a specific need.
- Update documentation after major behavior changes.
