# EDS Tool Program Structure & Design

**Version**: 2026-04  
**Python**: 3.12.12  
**Key Dependencies**: HyperSpy, exspy, matplotlib, qtpy

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Core Modules](#core-modules)
4. [Data Model](#data-model)
5. [Fitting Approach](#fitting-approach)
6. [Parameter Management](#parameter-management)
7. [Background Handling](#background-handling)
8. [Fine-Tuning Algorithm](#fine-tuning-algorithm)
9. [Coding Style & Conventions](#coding-style--conventions)
10. [Library Usage Patterns](#library-usage-patterns)
11. [Performance Considerations](#performance-considerations)

---

## Overview

The EDS Tool is a Python application for analyzing Energy-Dispersive X-ray Spectroscopy (EDS) data from electron microscopy. It provides both a GUI and command-line interface for:

- Loading and managing multiple EDS spectra
- Element identification and quantification
- Background subtraction (multiple methods)
- Model fitting with chi-square optimization
- Fine-tuning energy calibration
- Exporting results (spectra, plots, intensity tables)

**Key Design Philosophy**:
- Use HyperSpy/exspy as the core modeling engine
- Minimal GUI coupling - business logic in `eds_session.py`, not GUI code
- Automatic workflows for batch processing
- Performance: Fine-tuning should not freeze the GUI

---

## Architecture

### Three-Tier Design

```
Ã¢â€Å’Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€Â
Ã¢â€â€š  eds_tool.py (GUI Layer)           Ã¢â€â€š
Ã¢â€â€š  - Qt GUI components                Ã¢â€â€š
Ã¢â€â€š  - User interaction                 Ã¢â€â€š
Ã¢â€â€š  - Visualization                    Ã¢â€â€š
Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€Â¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€Ëœ
              Ã¢â€â€š
              Ã¢â€Å“Ã¢â€â‚¬ uses
              Ã¢â€ â€œ
Ã¢â€Å’Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€Â
Ã¢â€â€š  eds_session.py (Business Logic)   Ã¢â€â€š
Ã¢â€â€š  - EDSSession (multi-spectrum mgmt) Ã¢â€â€š
Ã¢â€â€š  - EDSSpectrumRecord (single spec)  Ã¢â€â€š
Ã¢â€â€š  - Fitting, calibration, export     Ã¢â€â€š
Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€Â¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€Ëœ
              Ã¢â€â€š
              Ã¢â€Å“Ã¢â€â‚¬ uses
              Ã¢â€ â€œ
Ã¢â€Å’Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€Â
Ã¢â€â€š  Library Layer                      Ã¢â€â€š
Ã¢â€â€š  - HyperSpy (signal/model base)     Ã¢â€â€š
Ã¢â€â€š  - exspy (EDS-specific models)      Ã¢â€â€š
Ã¢â€â€š  - matplotlib (plotting)            Ã¢â€â€š
Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€â‚¬Ã¢â€Ëœ
```

### Key Design Decisions

- **No business logic in GUI**: All fitting, calibration, and export logic lives in `eds_session.py`
- **Session-based management**: `EDSSession` manages multiple `EDSSpectrumRecord` objects
- **Lazy computation**: Fitted signals and intensities are cached after fitting
- **Separated signal roles**: raw counts, a CPS-normalized fit/model signal, and a mutable display proxy are distinct
- **Flexible background handling**: explicit reference-background modes are separate from the polynomial continuum (see [Background Handling](#background-handling))

---

## Core Modules

### `eds_session.py` Ã¢â‚¬â€ Core Business Logic

**Primary Classes**:

#### `EDSSpectrumRecord`
Represents a single EDS spectrum with its model, intensities, and metadata.

**Key Responsibilities**:
- Load EDS spectrum from file
- Manage element lists (sample elements, background elements)
- Fit model using HyperSpy/exspy
- Fine-tune energy calibration
- Compute intensities (summed or fitted)
- Export spectrum and plots
- Handle background correction

**Key Attributes**:
```python
path: str                    # File path
signal: EDSTEMSpectrum       # Mutable display proxy for signal-only views/export
_signal: EDSTEMSpectrum      # Raw source signal (always in counts)
_fit_signal: EDSTEMSpectrum  # Raw source normalized to CPS for fit/model diagnostics
_background: EDSTEMSpectrum  # Background spectrum in counts (if loaded)
_background_fit_signal: EDSTEMSpectrum  # Background spectrum normalized to CPS
model: EDSTEMModel           # Fitted model on _fit_signal (None if not fitted)
intensities: List[Signal]    # Summed intensities
fitted_intensities: List[Signal]  # Intensities from fit
fitted_reference_clean_signal: EDSTEMSpectrum # CPS signal minus fitted reference BG
fitted_reference_bg_signal: EDSTEMSpectrum    # CPS fitted reference BG only
signal_clean: EDSTEMSpectrum # Legacy alias of fitted_reference_clean_signal
signal_bg: EDSTEMSpectrum    # Legacy alias of fitted_reference_bg_signal
reduced_chisq: float         # Goodness of fit
bg_fit_mode: str             # 'none', 'bg_elements' or 'bg_spec'
background_prefit_mode: str  # 'off', 'exclude_sample' or 'bg_elements_only'
background_polynomial_order: int  # Polynomial baseline order (default 6)
display_signal_mode: str     # 'raw', 'measured_bg_subtracted', 'fitted_reference_bg_subtracted'
peak_sum_signal_mode: str    # Same choices, but for get_lines_intensity()
bg_correction_mode: str      # Legacy summary of the explicit signal modes
signal_unit: str             # 'counts' or 'cps' for signal-only views/export
reference_bg_shift: float    # Stored fixed shift reused when rebuilding bg_spec fits
fit_energy_min_keV: float    # Lower fit/calibration limit
fit_energy_max_keV: float    # Upper fit/calibration limit
reference_bg_ignore_sample_half_width_keV: float  # Sample-line exclusion half-width for BG prefit / reference-BG shift refinement
```

**Key Methods**:
- `set_elements(elements)` - Set sample elements; if a model exists, refit it and reuse the existing model object when possible
- `set_bg_elements(elements)` - Set background elements
- `fit_model()` - Fit model using current elements and background settings
- `fine_tune_model()` - Calibrate energy offset and resolution
- `compute_intensities()` - Compute summed intensities (no fitting required)
- `export()` - Export spectrum to various formats
- `export_plot()` - Export annotated plot
- `plot()` - Interactive matplotlib plot

#### `EDSSession`
Manages multiple spectra and provides session-level operations.

**Key Responsibilities**:
- Load multiple spectra from files/directories
- Apply settings to all spectra (elements, background, units)
- Batch operations (fit all, fine-tune all)
- Export combined intensity tables
- Active spectrum management for GUI

**Key Attributes**:
```python
records: Dict[str, EDSSpectrumRecord]  # All loaded spectra
active_record: EDSSpectrumRecord       # Currently selected spectrum
```

**Key Methods**:
- `set_elements(elements)` - Set elements for all spectra and batch-refit already fitted models
  - In the GUI, right-click element picking is staged first: it updates the entry box and plot-line preview immediately, but only `Apply` triggers the batch refit
- `set_background(path_or_signal)` - Load and apply background to all
- `fit_all_models()` - Fit models for all spectra
- `fine_tune_all_models()` - Fine-tune all fitted models
- `apply_active_fine_tuning_to_all_models()` - Apply the active refined calibration to other fitted models and re-fit them
- `export_intensity_table()` - Export combined CSV table

### `eds_tool.py` - GUI & CLI Interface

**Components**:
- `NavigatorWidget` - Main window, spectrum list, controls
- `IntensityTableDialog` - Spreadsheet view of intensities
- Auto-workflow functions for batch processing
- Command-line argument parsing

**GUI Design Pattern**:
- GUI code calls `EDSSession` / `EDSSpectrumRecord` methods
- No fitting or computation logic in GUI layer
- Use Qt signals for asynchronous updates (if needed)
- `NavigatorWidget` is organized into functional groups: spectrum management, elements/background, fitting/quantification, and display/tables
- Background UI is split into a simple primary path (`Fit background`) plus derived-signal controls in two places:
  - `Spectrum view` lives in `Display and Tables`
  - `Peak-sum source` lives in an `Advanced` section inside `Fitting and Quantification`
- Those derived-signal selectors act on the active spectrum only; they are not forced across every loaded record because fitted-reference views may be valid for one fitted spectrum while still unavailable for unfitted ones. The session only remembers them as defaults for future compatible records.
- That same `Advanced` section exposes fit-range controls:
  - lower / upper fit limits
  - `Ignore sample +/-` for reference-BG shift refinement only
- Current defaults are:
  - fit range `0.2-40.0 keV`
  - `BG prefit = Exclude sample`
  - `Ignore sample +/- = 0.2 keV`
  - `Baseline order = 6`
- The current GUI also exposes:
  - `BG prefit` (`Off`, `Exclude sample`, `BG el. only`)
  - polynomial baseline order (`Baseline order`)
  - `Fit background` modes `None`, `BG Elements`, and `Ref BG Spec`
  - batch `Apply` and `Refine` actions:
    - `Apply` copies the active refined calibration to other already-fitted spectra and re-fits them
    - `Refine` runs per-spectrum refinement across all currently fitted spectra
  - a `BG el.` display toggle for showing background-element markers on demand
- The loaded-spectrum list can be navigated directly with `Up/Down` and now shows fit quality inline, e.g. `[chi2r: 1.50]`
- Long-running fit/refine/apply actions remain synchronous, but the GUI now shows a small static progress dialog before entering the blocking call
- When `Ref BG` is requested before any fit exists, the raw reference-BG spectrum is shown directly in CPS with the legend `Reference background (not fitted)`
- The spectrum list is the primary stretch area because the common workflow is many loaded spectra with one active record
- Initial navigator/plot window sizing is screen-aware rather than fixed, so the control pane can use more vertical space without breaking the side-by-side plot arrangement
- Initial plot-window creation is deferred until the navigator's first real `showEvent`; doing it inside `__init__` caused unstable first-pass Qt layout in nested control groups
- Raw/model HyperSpy plots now use the CPS-normalized fit signal; counts remain a signal-only view/export choice
- The fitted-reference-BG-subtracted spectrum view still uses a live HyperSpy model plot by swapping the signal/model line callbacks to a background-subtracted space; the residual is unchanged because subtracting the same fitted reference BG from both signal and model cancels out
- Plot legends are rebuilt explicitly as `Signal raw/background-corrected`, `Background`, `Fit`, and `Residual` as applicable
- Batch execution is split by what actually dominates the runtime:
  - `fit_all_models()` is intentionally sequential because HyperSpy/exspy model construction (`create_model()`) is dominated by SymPy-based Python work and deep-copy/slicing overhead, so threads serialize there under the GIL and processes are slower on Windows because they cold-import the full scientific stack
  - `fine_tune_all_models()` still uses worker threads because it operates on already-built models and benefits from parallel numeric work
  - session-level element or BG-element changes on already fitted spectra also use the threaded numeric path by updating models in place first and then re-fitting them without rebuilding from scratch
  - refinement concurrency is capped separately from existing-model element refits:
    - `DEFAULT_REFINE_ALL_MAX_WORKERS` controls fine-tuning worker count
    - `DEFAULT_EXISTING_MODEL_REFIT_MAX_WORKERS` controls threaded re-fit after in-place model edits
  - the helper that forces numexpr to one thread is protected by a global ref-counted lock because numexpr thread-count changes are process-global and were causing batch hangs when many refinements entered/exited concurrently

---

## Data Model

### Spectrum Lifecycle

```
1. Load Ã¢â€ â€™ EDSSpectrumRecord created
   - Signal loaded via HyperSpy
   - Metadata parsed
   - Energy resolution set to 128 eV (default)

2. Set Elements Ã¢â€ â€™ Elements metadata updated
   - If model exists Ã¢â€ â€™ automatic refit triggered
   
3. Fit Model Ã¢â€ â€™ Model created and fitted
   - Fit/model diagnostics operate on `_fit_signal` in CPS
   - Model type depends on bg_fit_mode
   - Intensities computed from fit
   - Chi-square calculated
   - External-background-only fitted signals cached

4. Fine-Tune Ã¢â€ â€™ Energy calibration applied
   - Offset calibration
   - Reference-BG shift refinement (if applicable)
   - Resolution calibration (with locked parameters)
   - Stable-state selection via rebuilt candidate fits
   - Model and intensities updated

5. Export Ã¢â€ â€™ Results saved
   - Spectrum (EMSA, CSV, etc.)
   - `.hspy` analysis snapshots with serialized EDS Tool state
   - Plots (PNG, SVG, JPG)
   - Intensities (CSV)
```

### `.hspy` Persistence

- Exporting to `.hspy` saves the raw counts signal, not the current display view.
- EDS Tool state is serialized into metadata and currently includes:
  - fit/background settings
  - current calibration and reset defaults
  - embedded reference-BG signal payload
  - fitted model parameter values / free flags / bounds
  - display and peak-sum source modes
- Loading one of these `.hspy` files reconstructs the fitted model and cached fitted-reference-BG products without immediately re-running a fit.
- When matching `.eds` and `.hspy` files exist with the same basename, path discovery prefers `.hspy`.

### Element Management

**Sample Elements** (`elements`):
- Elements present in the sample
- Always included in the model
- Set via `set_elements()`

**Background Elements** (`bg_elements`):
- Elements from instrument, holder, grid, etc.
- Handling depends on `bg_fit_mode`:
  - `'bg_elements'`: Added to model during fit, removed after
  - `'bg_spec'`: Not used (background spectrum used instead)

**Element Change Behavior**:
- Changing `elements` or `bg_elements` triggers automatic refit if model exists
- Prevents model/element mismatch
- When a fitted model already exists, element changes now update that model in place:
  - remove line families whose elements are no longer needed
  - add missing line families with `add_family_lines()`
  - keep background components, calibration, and fitted state of unchanged lines
- Session-level element changes batch those in-place re-fits across already fitted records using the threaded numeric worker path

---

## Fitting Approach

### Model Creation

The fitting process uses HyperSpy/exspy's `EDSTEMModel`:

```python
# Create model on the CPS-normalized fit signal
self._fit_signal.set_elements(elements)
self.model = self._fit_signal.create_model(
    auto_add_lines=True,      # Add X-ray lines automatically
    auto_background=True       # Add polynomial background
)
self.model.add_family_lines()  # Add all lines for each element family
```

### Two Fitting Modes

#### Mode 1: `bg_fit_mode = 'bg_elements'`
**Use case**: No background spectrum available, but know instrument elements

```python
# Add background elements to the CPS fit signal temporarily
all_elements = sample_elements + bg_elements
self._fit_signal.set_elements(all_elements)
self.model = self._fit_signal.create_model(...)
self.model.fit()
# Restore sample elements only
self._fit_signal.set_elements(sample_elements)
```

**Model components**:
- X-ray lines for sample elements
- X-ray lines for background elements
- Polynomial background

#### Mode 2: `bg_fit_mode = 'bg_spec'` Ã¢Â­Â **PREFERRED**
**Use case**: Have measured background spectrum (recommended for accuracy)

```python
# Create model with sample elements only on the CPS fit signal
self._fit_signal.set_elements(sample_elements)
self.model = self._fit_signal.create_model(...)

# Add background spectrum as ScalableFixedPattern
comp_bg = hs.model.components1D.ScalableFixedPattern(background_fit_signal)
comp_bg.name = 'instrument'
self.model.append(comp_bg)

self.model.fit()
```

**Model components**:
- X-ray lines for sample elements
- Polynomial background (slowly-varying component)
- ScalableFixedPattern 'instrument' component (scales background spectrum)

**Advantages**:
- Background shape is fixed (measured)
- In the optimized path, only `yscale` is fitted during the initial fit.
- `shift` can be refined later during fine-tuning if the measured background is
  slightly offset from the sample spectrum.
- `xscale` is fixed at 1.0 because floating it adds a costly nonlinear degree
  of freedom with negligible benefit for spectra on the same energy calibration.
- More accurate for complex background shapes
- Lower parameter count Ã¢â€ â€™ faster fitting

---

## Parameter Management

### Parameter Types in Model

For a typical fit with 8 elements + background spectrum:

```
Component          | Parameters | Free? | Notes
-------------------+------------+-------+---------------------------
Polynomial_bg      | 7 coeffs   | Yes   | Slowly-varying continuum
instrument yscale  | 1 scale    | Yes   | Background spectrum amplitude
instrument shift   | 1 value    | No*   | Optional BG/signal offset
instrument xscale  | 1 value    | No    | Fixed to 1.0
Element 1 lines    | 1 intensity| Yes   | Per element (family)
Element 2 lines    | 1 intensity| Yes   |
...                | ...        | ...   |
Element N lines    | 1 intensity| Yes   |
EDS resolution     | 1 value    | No*   | Energy resolution (eV)
EDS offset         | 1 value    | No*   | Energy axis offset (keV)
-------------------+------------+-------+---------------------------
Total              | ~18 params | ~18   | *shift can be freed during fine-tuning
```

### Parameter States

**Free Parameters** (`param.free = True`):
- Optimized during fitting
- Default for all component parameters after model creation

**Locked Parameters** (`param.free = False`):
- Fixed during fitting
- Used to speed up calibration by reducing degrees of freedom

### Parameter Bounds

- Bounds are NOT automatically enforced by exspy
- Must set `ext_bounded=True` in component for bounds to take effect
- Most components don't use bounds by default
- Background polynomial: no direct non-negativity regularization in the HyperSpy / exspy EDS model path
- Resolution calibration: explicitly bounded to `127-130 eV` by bounding the reference line `sigma` during the locked resolution-calibration step
- X-ray line intensities: Usually non-negative (Ã¢â€°Â¥0)

---

## Background Handling

### External Background vs Polynomial Continuum

Two different "backgrounds" coexist in the model:

- **External/parasitic background**: holder, grid, instrument, or blank-spectrum contributions modeled by `bg_spec` or `bg_elements`
- **Polynomial continuum**: HyperSpy's smooth baseline terms from `auto_background=True`

Only the first category is treated as user-facing background subtraction. The polynomial continuum remains part of the fit model and is not exposed as a subtraction mode.

### Explicit Signal Source Modes

`EDSSpectrumRecord` now has two explicit selectors:

- `display_signal_mode`
- `peak_sum_signal_mode`

Each can be:

- `'raw'`
- `'measured_bg_subtracted'`
- `'fitted_reference_bg_subtracted'`

These control signal-only views/export and peak-sum intensities. They do not change the CPS-normalized fit/model signal.

### Legacy Compatibility Modes (`bg_correction_mode`)

#### `'none'` Ã¢â‚¬â€ No External Background Subtraction
- Maps to `display_signal_mode = peak_sum_signal_mode = 'raw'`
- Keeps the raw signal for signal-only views/export and peak summation

#### `'subtract_spectra'` Ã¢â‚¬â€ Measured External Background Subtraction
- Maps to `display_signal_mode = peak_sum_signal_mode = 'measured_bg_subtracted'`
- Subtracts the measured background with live-time normalization
- Affects signal-only views/export and peak summation only

#### `'subtract_fitted'` Ã¢â‚¬â€ Fitted Reference Background Subtraction
- Maps to `display_signal_mode = peak_sum_signal_mode = 'fitted_reference_bg_subtracted'`
- Subtracts only explicitly modeled reference-background components
- Available for `bg_spec`
- Also available for `bg_elements` only when BG elements are disjoint from sample elements
- Raises `ValueError` when no identifiable fitted reference background exists

### Two Fitting Modes (`bg_fit_mode`)

See [Fitting Approach](#fitting-approach) section above.

There is also a third explicit mode:

- `bg_fit_mode='none'`
  - sample lines + polynomial baseline only
  - no reference-BG component is modeled
  - fitted reference-BG subtraction is unavailable by design

Optional two-step background prefit is controlled separately through `background_prefit_mode`:

- `'off'`: normal one-stage fit
- `'exclude_sample'`: fit only the background stage first while excluding `Ignore sample Ã‚Â±` windows around sample lines, then freeze background and fit the rest
- `'bg_elements_only'`: in `bg_elements` mode with non-overlapping BG elements, fit the background stage only around BG-element windows, then freeze background and fit the rest

### CPS-First Model Path

- Fitting and model diagnostics always run on `_fit_signal`, which is `_signal` normalized to CPS
- `bg_spec` uses `_background_fit_signal`, the measured background normalized to CPS
- Raw/model HyperSpy plots therefore operate in CPS
- Counts remain available for signal-only views, export, and peak-sum intensities
- Fit lower/upper limits apply to normal fits and energy-axis calibration
- `Ignore sample Ã‚Â±` is narrower: it is only used during reference-BG shift refinement so sample peaks do not dominate the background-alignment step

**Recommendation**: Use `bg_fit_mode='bg_spec'` with raw CPS model diagnostics, and apply measured or fitted external subtraction only where a derived signal is actually needed.

### Fit Deletion Reset

- `clear_fit()` is the canonical way to remove a fit.
- It clears the model, fitted intensities, cached fitted reference-BG signals, and reduced `Ãâ€¡Ã‚Â²Ã¡ÂµÂ£`.
- It also resets the fine-tuned calibration state:
  - energy offset
  - energy scale
  - energy resolution
  - stored `reference_bg_shift`
- This avoids the old surprising behavior where deleting a fit left refined calibration behind.

---

## Fine-Tuning Algorithm

Fine-tuning corrects small energy axis shifts and incorrect detector resolution that cause visible residuals after initial fitting.

**Updated behavior (2026-04-21)**:
- Resolution calibration is hard-bounded through the reference alpha-line `sigma` used by exspy's detector-resolution model, with warnings when the fit hits either bound.
- The current code bounds detector resolution to `127-132 eV`.
- `fine_tune_model()` now ends with a constrained post-calibration fit that re-solves amplitudes, baseline, and reference-BG scale while keeping the calibrated offset, reference-BG shift, and resolution fixed.
- The original free/fixed/twin structure is restored after fine-tuning; only the calibrated offset, reference-BG shift, and detector resolution persist as state changes.
- The reference-BG-shift step reports a masked BG-window chi-square, not the full-spectrum model chi-square.
- Re-running fine-tuning on an unchanged model can still drive the resolution step into a different bound-constrained basin; the implementation therefore keeps the pre-refinement model state as a baseline candidate and restores it if the full fitted model gets worse.

### Problem

Even after good initial fits, residuals often show:
- **Systematic shifts**: All lines shifted left or right (energy offset error)
- **Wrong widths**: Lines too narrow or too broad (resolution parameter error)

These cause poor chi-square even when element selection is correct.

### Solution: Sequential Calibration Plus Restricted Postfit

```python
def fine_tune_model(self):
    """
    Current refinement process:
    1. Offset calibration (all params free)
    2. Background shift refinement (bg_spec mode only)
    3. Resolution calibration (LOCKED PARAMS for speed)
    4. Constrained post-calibration refit
    5. Restore the original model structure
    """
```

The current implementation is:
1. offset calibration
2. reference-BG shift refinement where applicable
3. bounded resolution calibration
4. constrained post-calibration fit with energies, widths, and BG shift fixed
5. keep the resulting live refined model and use later `fit_model()` rebuilds for stable follow-up work

### Step-by-Step Algorithm

#### Step 1: Energy Offset Calibration
**Goal**: Shift energy axis to align lines with spectrum peaks

```python
# All parameters free during offset calibration
self.model.calibrate_energy_axis(calibrate='offset')
```

**What it does**:
- Adjusts `signal.axes_manager[-1].offset` (energy axis offset in keV)
- Internally fits model with offset as free parameter
- Updates model line positions
- Typically takes ~4 seconds with all params free
- Typically improves chi-square by 15-20%

**Observed on the `acac` multi-spectrum dataset**:
```
After offset calibration:
  Offset: 0.001914 keV (ÃŽâ€ = +4.07 eV)
  Ãâ€¡Ã‚Â²Ã¡ÂµÂ£: 615.61 (ÃŽâ€ = -131.42, -17.6%)
```

#### Step 2: Background Shift Refinement
**Goal**: Allow a small x-shift between the measured background spectrum and the sample peaks

**Why it is separate**:
- During the initial fit, `instrument.shift` is fixed so the model stays fast and well-conditioned
- After the peak offset is calibrated, `instrument.shift` can be refined without coupling it to the peak-position calibration

**Typical behavior**:
- Frees only `instrument.shift` and `instrument.yscale`
- Fits the background alignment against otherwise fixed peak/background parameters
- Useful when background and sample spectra have a small relative offset
- Respects the fit lower/upper limits
- Can exclude `Ã‚Â± ignore_sample_half_width` around sample lines so the reference-BG alignment focuses on background-dominated regions
#### Step 3: Energy Resolution Calibration Ã¢Â­Â **KEY OPTIMIZATION**
**Goal**: Adjust detector resolution to match line widths

**Problem**: If all 20 parameters are free, this step takes ~77 seconds and hits maxfev warnings!

**Solution**: Lock all parameters except resolution

```python
# Lock all component parameters
locked_params = []
for component in self.model:
    for param in component.parameters:
        if param.free:
            param.free = False
            locked_params.append(param)

# Calibrate resolution (will unlock resolution param internally)
self.model.calibrate_energy_axis(calibrate='resolution')

# Restore locked parameters to free state
for param in locked_params:
    param.free = True
```

**What it does**:
- Adjusts `metadata.Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa` (in eV)
- Only resolution parameter is optimized (all others fixed)
- Typically takes ~3 seconds with locked params vs ~77 seconds with all free
- Typically improves chi-square by additional 5-10%

**Example output**:
```
After resolution calibration (with locked parameters):
  Resolution: 126.53 eV (ÃŽâ€ = -1.47 eV)
  Ãâ€¡Ã‚Â²Ã¡ÂµÂ£: 585.38 (ÃŽâ€ = -30.23, -4.9%)
```

**Critical**: Without parameter locking, this step is 20-25x slower and can freeze the GUI!

#### Step 4: Stable Candidate Selection
**Goal**: Keep a calibrated state that remains good after a clean rebuild and later re-fits

```python
candidate_states = [initial, offset, bg_shift, resolution]
for state in candidate_states:
    rebuilt_chisq = rebuild_model_on(state)
best_state = min(candidate_states, key=rebuilt_chisq)
```

**What it does**:
- Rebuilds a fresh model for each candidate calibration state
- Compares rebuilt `Ãâ€¡Ã‚Â²Ã¡ÂµÂ£`, not just the transient calibration-stage `Ãâ€¡Ã‚Â²Ã¡ÂµÂ£`
- Rejects unstable resolution-calibration states that look good only before rebuild
- Leaves the record in a robust fitted state for later element changes / re-fits

**Example output**:
```
After final refinement fit:
  Ãâ€¡Ã‚Â²Ã¡ÂµÂ£: 560.47 (ÃŽâ€ = -24.92, -4.3%)
```

Historical note: the old Step 4 candidate-selection description above is no longer the live implementation. The current fine-tuning path now performs a constrained post-calibration refit with only X-ray amplitudes, polynomial background coefficients, and `instrument.yscale` free while keeping the calibrated offset, resolution, and reference-BG shift fixed, and then restores the original free/fixed/twin model structure. This is what makes a single fine-tuning pass effective on difficult spectra such as `acac/exp_7985.EDS` and `acac/exp_7987.EDS`.

### Overall Performance

**Target**: Fine-tuning should be comparable to initial fit time

```
Initial fit:     ~2-4 seconds
Fine-tuning:     ~6-9 seconds
  - Offset calib:              ~1-2s
  - Background shift refine:   ~1s
  - Resolution calib:          ~1s (with locked params)
  - Stable candidate rebuilds: ~2-4s
Total improvement: ~25% chi-square reduction
```

**Without parameter locking**:
```
Fine-tuning:     ~85 seconds (14.2x) Ã¢ÂÅ’ SLOW
  - Offset calib:         ~4s
  - Resolution calib:    ~77s (maxfev warnings)
  - Final fit:            ~1s
```

### Why Parameter Locking Works

**Insight**: During resolution calibration, we're only adjusting the width of X-ray lines, not their positions or relative intensities. Therefore:

- Ã¢Å“â€¦ **Resolution parameter must be free**: That's what we're calibrating
- Ã¢ÂÅ’ **Element intensities should be locked**: Relative peak heights don't change
- Ã¢ÂÅ’ **Background coefficients should be locked**: Background shape doesn't significantly change
- Ã¢ÂÅ’ **Offset should be locked**: Already calibrated in step 1

**Result**: Resolution calibration becomes a ~1-parameter optimization instead of a 20-parameter optimization.

### Important Notes

1. **Calibration methods include fitting**: `calibrate_energy_axis()` internally calls fit(), so explicit fit() calls are optional but improve results slightly.

2. **exspy doesn't auto-lock parameters**: The calibration methods in exspy do NOT automatically lock parameters. You must do it manually.

3. **Stable-state selection matters**: Offset is still first. Reference-BG shift refinement comes next when applicable. Resolution calibration is treated as a candidate, not blindly accepted.

4. **Transient vs stable chi-square**: A calibration stage can report a better transient `Ãâ€¡Ã‚Â²Ã¡ÂµÂ£` and still be unusable after rebuild. The code therefore compares rebuilt fits, not just the transient calibration result.

3. **Order matters**: Offset Ã¢â€ â€™ Resolution Ã¢â€ â€™ Offset sequence was tested. Final approach uses Offset Ã¢â€ â€™ Resolution only, with final refinement fit.

4. **Chi-square may increase after resolution calibration**: Before final refinement fit, chi-square might temporarily be worse. The final fit brings it down.

---

## Coding Style & Conventions

### Python Style

- **PEP 8 compliant**: Standard Python formatting
- **Type hints**: Used for function signatures (Python 3.7+ style)
- **Docstrings**: Google-style or reStructuredText for classes and complex methods
- **Error handling**: Try-except with informative messages, avoid silent failures

### Variable Naming

- **snake_case**: For variables, functions, methods
- **PascalCase**: For classes
- **Private attributes**: Leading underscore (e.g., `_signal`, `_background`)
  - `_signal`: Original signal in counts (immutable after load)
  - `signal`: Current working signal (may have corrections applied)

### Constants

```python
AUTO_SPECTRUM_FORMATS = ['emsa', 'csv', 'hspy']
AUTO_PLOT_FORMATS = ['png', 'svg', 'jpg']
```

### Comments

- **Inline comments**: Explain non-obvious behavior or workarounds
- **Block comments**: Explain algorithms or design decisions
- **TODO comments**: Mark incomplete features or known issues

Example:
```python
# Set default energy resolution to 128 eV (instead of HyperSpy's default of 133 eV)
self._signal.set_microscope_parameters(energy_resolution_MnKa=128)
```

---

## Library Usage Patterns

### HyperSpy/exspy

#### Loading Spectra
```python
import hyperspy.api as hs
signal = hs.load('spectrum.eds')
```

#### Setting Metadata
```python
signal.metadata.set_item('General.title', 'my_spectrum')
signal.set_microscope_parameters(energy_resolution_MnKa=128)
```

#### Creating Models
```python
signal.set_elements(['Fe', 'Ni', 'Cr'])
model = signal.create_model(auto_add_lines=True, auto_background=True)
model.add_family_lines()
model.fit()
```

#### Intensity Computation
```python
# Summed intensities (no fitting required)
intensities = signal.get_lines_intensity()

# Fitted intensities (requires fitted model)
fitted_intensities = model.get_lines_intensity()
```

#### Background Components
```python
# ScalableFixedPattern for measured background
comp_bg = hs.model.components1D.ScalableFixedPattern(bg_signal)
comp_bg.name = 'instrument'
model.append(comp_bg)
```

#### Calibration
```python
# Energy offset calibration
model.calibrate_energy_axis(calibrate='offset')

# Energy resolution calibration
model.calibrate_energy_axis(calibrate='resolution')
```

#### Extracting Fit Quality
```python
# Reduced chi-square
chisq_data = model.red_chisq.data
reduced_chisq = float(chisq_data.item())  # Extract scalar from array
```

### Matplotlib

#### Plotting EDS Spectra
```python
signal.plot(xray_lines=True)  # Uses HyperSpy's built-in plotting
```

#### Custom Plotting
```python
fig, ax = plt.subplots(figsize=(12, 6))
ax.plot(energy_axis, signal.data, label='Spectrum')
ax.plot(energy_axis, model_data, label='Model')
ax.set_xlabel('Energy (keV)')
ax.set_ylabel('Counts')
```

### Qt (qtpy abstraction)

```python
from qtpy import QtWidgets, QtCore
from qtpy.QtGui import QIcon

class MyWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)
        button = QtWidgets.QPushButton("Click me")
        button.clicked.connect(self.on_click)
        layout.addWidget(button)
    
    def on_click(self):
        print("Button clicked")
```

---

## Performance Considerations

### Bottlenecks

1. **Model fitting**: ~1-2 seconds per spectrum after optimization
   - Previously ~6-12 seconds per spectrum in this environment
   - Dominated by repeated model evaluation inside scipy optimization
   - Key fixes:
     - Fix `ScalableFixedPattern.xscale` at 1.0
     - Force `numexpr` to one thread during fitting/calibration for small 1D EDS spectra

2. **Resolution calibration without parameter locking**: ~77 seconds
   - Causes GUI freezing
   - Fixed by locking parameters (reduces to ~1 second)

3. **Loading spectra**: Usually fast (<1 second), unless very large files

### Optimization Strategies

#### 1. Parameter Locking During Calibration Ã¢Â­Â **CRITICAL**
**Impact**: 25x speedup for resolution calibration  
**Implementation**: See [Fine-Tuning Algorithm](#fine-tuning-algorithm)

#### 2. Disable Pointless Background X-Scaling
**Impact**: Large speedup with negligible chi-square change  
**Implementation**: In `bg_spec` mode, set `instrument.xscale.free = False`

#### 3. Use Single-Thread numexpr for Small EDS Fits
**Impact**: Large speedup on typical 4096-channel spectra  
**Why**: HyperSpy evaluates many small component arrays; `numexpr`'s default
multi-threading overhead dominates for this workload  
**Implementation**: Wrap fit/calibration calls in a context that temporarily sets
`numexpr` threads to 1

#### 4. Lazy Computation
**Pattern**: Don't compute until needed
```python
def _compute_fitted_signals(self):
    """Compute and cache fitted signals after fitting."""
    if self.model is None:
        self.signal_clean = None
        self.signal_bg = None
        return
    # ... compute and cache
```

#### 5. Avoid Redundant Fits
**Pattern**: Check if refit is actually needed
```python
def set_elements(self, elements):
    # Check if actually changed
    if sorted(elements) == sorted(self.elements):
        return
    # ... proceed with refit
```

#### 6. Batch Operations
**Pattern**: Fit all spectra in one loop instead of individually
```python
def fit_all(self):
    for rec in self.records.values():
        rec.fit_model()
```

### Performance Targets

```
Operation                    | Target Time | Notes
-----------------------------+-------------+-------------------------
Load spectrum                | <1s         | I/O bound
Initial fit (8 elements)     | 1-2s        | Optimized bg_spec path
Fine-tune                    | 1-2s        | Same as initial fit
Compute summed intensities   | <0.5s       | No fitting required
Export plot (PNG)            | 1-2s        | Matplotlib rendering
```

### Memory Considerations

- Each spectrum: ~few MB (depends on energy resolution)
- Models: ~few MB (stores component data)
- Cached fitted signals: 2-3x spectrum size
- Typical session (10 spectra): ~100-200 MB

---

## Development Workflow

### Testing Fine-Tuning Performance

After any changes to `fine_tune_model()`:

```bash
python tests/test_fine_tune_timing.py
```

**Expected output**:
```
Initial fit took: ~1.4s
Fine-tune took: ~1.4s (1.0x)
Ã¢Å“â€œ Fine-tuning time is reasonable (1.0x initial fit time)
```

**Warning signs**:
- Fine-tuning >10s: Check parameter locking
- maxfev warnings: Parameters not properly locked
- Chi-square increases: Check calibration order

### Adding New Features

1. Implement business logic in `eds_session.py`
2. Add GUI controls in `eds_tool.py`
3. Create manual test in `tests/`
4. Run performance tests if touching fitting code
5. Update this documentation

### Debugging Fitting Issues

**Tools**:
- `test_param_locking.py` - Check which params are free
- `test_calibrate_includes_fit.py` - Check calibration behavior
- Print chi-square at each step of fine-tuning

**Common issues**:
- **High chi-square**: Wrong elements, missing background
- **Slow fitting**: Too many free parameters
- **No convergence**: Bad initial parameter values, conflicting constraints

---

## Summary

**Key Takeaways for Agents**:

1. Ã¢Å“â€¦ **Business logic in** `eds_session.py`, **GUI in** `eds_tool.py`
2. Ã¢Å“â€¦ **Lock parameters during resolution calibration** - critical for performance
3. Ã¢Å“â€¦ **Default energy resolution is 128 eV** (not HyperSpy's 133 eV)
4. Ã¢Å“â€¦ **Use bg_spec mode** with ScalableFixedPattern when possible
5. Ã¢Å“â€¦ **Fix `instrument.xscale` at 1.0** - it adds costly nonlinearity with negligible benefit
6. Ã¢Å“â€¦ **Keep `instrument.shift` fixed during the initial fit** - refine it only during fine-tuning if needed
7. Ã¢Å“â€¦ **Force `numexpr` to 1 thread during EDS fitting** - default multithreading is much slower for 4k-channel spectra
8. Ã¢Å“â€¦ **Changing elements triggers auto-refit** - prevents model/element mismatch
9. Ã¢Å“â€¦ **Fine-tuning should stay in the same order of magnitude as the initial fit** - use timing tests to verify
10. Ã¢Å“â€¦ **Calibration methods include fitting** - explicit fit() calls are optional but help
11. Ã¢Å“â€¦ **exspy doesn't auto-lock parameters** - must do manually

**Most Critical Code Section**: Fine-tuning parameter locking (see lines 236-320 in `eds_session.py`)

**Most Common Pitfall**: Forgetting to lock parameters during resolution calibration Ã¢â€ â€™ 25x performance degradation

**Performance Verification**: Run `test_fine_tune_timing.py` after any changes to fitting/calibration code

---

## Standalone Fitting Protocol Investigation

There is now a dedicated standalone investigation script:

- [tests/explore_fitting_protocols.py](/c:/Users/robert.buecker/codes/eds-tool/tests/explore_fitting_protocols.py:1)

This exists because the in-app fitting path had accumulated enough branching and
stateful edge handling that it became hard to reason about the fitting protocol
itself from GUI behavior alone.

### What It Does

- loads sample and reference-background spectra directly with HyperSpy
- builds exactly one live exSpy model per case
- snapshots and restores that model using `model.store()` /
  `signal.models.restore()`
- compares explicit refinement orderings step by step
- records:
  - `chi2r`
  - offset
  - fitted `energy_resolution_MnKa`
  - reference-BG shift / scale
  - baseline drift from the actual polynomial curve
  - runtime
  - nested `model.fit()` calls triggered inside calibration helpers

### Current Best Protocol

The strongest refinement route found so far is:

1. Initial bounded fit with width fixed at `128 eV`
2. Overall offset calibration
3. Bounded linear re-fit
4. Reference-BG shift-only masked fit
5. Bounded linear re-fit
6. Locked one-parameter width fit
7. Candidate search over width-line groups, including a `skip width` option

This is cleaner than repeated blind refine cycles and avoids the major failure
mode seen in earlier versions: a broad nonlinear width fit absorbing baseline or
reference-background errors.

### exSpy Helper Limitations Found

With the current model shape (polynomial baseline + `ScalableFixedPattern`
reference background), the standalone investigation found that:

- `fit_background()` is not directly usable
- `fix_xray_lines_energy()` / `fix_xray_lines_width()` are only safe through
  explicit x-ray-line paths, not the default `"all"` path
- `calibrate_energy_axis(calibrate='resolution')` cannot be used directly
  because its final width-to-energy-resolution update walks non-line components

So the standalone script still uses official HyperSpy/exSpy model objects, but
reimplements the line-only width update path explicitly where the built-in
helper currently breaks.

### Detailed Results

Detailed notes are in:

- [FITTING_TESTS.md](/c:/Users/robert.buecker/codes/eds-tool/FITTING_TESTS.md:1)

Validated CSV / JSON output bundle from the April 2026 run:

- [tests/fitting_protocol_outputs/20260422_full_search/all_protocol_summary.csv](/c:/Users/robert.buecker/codes/eds-tool/tests/fitting_protocol_outputs/20260422_full_search/all_protocol_summary.csv:1)
