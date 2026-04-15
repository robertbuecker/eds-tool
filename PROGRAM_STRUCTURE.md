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
┌─────────────────────────────────────┐
│  eds_tool.py (GUI Layer)           │
│  - Qt GUI components                │
│  - User interaction                 │
│  - Visualization                    │
└─────────────┬───────────────────────┘
              │
              ├─ uses
              ↓
┌─────────────────────────────────────┐
│  eds_session.py (Business Logic)   │
│  - EDSSession (multi-spectrum mgmt) │
│  - EDSSpectrumRecord (single spec)  │
│  - Fitting, calibration, export     │
└─────────────┬───────────────────────┘
              │
              ├─ uses
              ↓
┌─────────────────────────────────────┐
│  Library Layer                      │
│  - HyperSpy (signal/model base)     │
│  - exspy (EDS-specific models)      │
│  - matplotlib (plotting)            │
└─────────────────────────────────────┘
```

### Key Design Decisions

- **No business logic in GUI**: All fitting, calibration, and export logic lives in `eds_session.py`
- **Session-based management**: `EDSSession` manages multiple `EDSSpectrumRecord` objects
- **Lazy computation**: Fitted signals and intensities are cached after fitting
- **Flexible background handling**: Three correction modes, two fitting modes (see [Background Handling](#background-handling))

---

## Core Modules

### `eds_session.py` — Core Business Logic

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
signal: EDSTEMSpectrum       # Current signal (may have bg correction applied)
_signal: EDSTEMSpectrum      # Original signal (always in counts)
_background: EDSTEMSpectrum  # Background spectrum (if loaded)
model: EDSTEMModel           # Fitted model (None if not fitted)
intensities: List[Signal]    # Summed intensities
fitted_intensities: List[Signal]  # Intensities from fit
signal_clean: EDSTEMSpectrum # Signal minus background (cached)
signal_bg: EDSTEMSpectrum    # Background component only (cached)
reduced_chisq: float         # Goodness of fit
bg_fit_mode: str             # 'bg_elements' or 'bg_spec'
bg_correction_mode: str      # 'none', 'subtract_fitted', 'subtract_spectra'
```

**Key Methods**:
- `set_elements(elements)` - Set sample elements, triggers refit if model exists
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
- `set_elements(elements)` - Set elements for all spectra
- `set_background(path_or_signal)` - Load and apply background to all
- `fit_all()` - Fit models for all spectra
- `fine_tune_all()` - Fine-tune all fitted models
- `export_intensity_table()` - Export combined CSV table

### `eds_tool.py` — GUI & CLI Interface

**Components**:
- `NavigatorWidget` - Main window, spectrum list, controls
- `IntensityTableDialog` - Spreadsheet view of intensities
- Auto-workflow functions for batch processing
- Command-line argument parsing

**GUI Design Pattern**:
- GUI code calls `EDSSession` / `EDSSpectrumRecord` methods
- No fitting or computation logic in GUI layer
- Use Qt signals for asynchronous updates (if needed)

---

## Data Model

### Spectrum Lifecycle

```
1. Load → EDSSpectrumRecord created
   - Signal loaded via HyperSpy
   - Metadata parsed
   - Energy resolution set to 128 eV (default)

2. Set Elements → Elements metadata updated
   - If model exists → automatic refit triggered
   
3. Fit Model → Model created and fitted
   - Model type depends on bg_fit_mode
   - Intensities computed from fit
   - Chi-square calculated
   - Fitted signals cached (signal_clean, signal_bg)

4. Fine-Tune → Energy calibration applied
   - Offset calibration
   - Resolution calibration (with locked parameters)
   - Final refinement fit
   - Model and intensities updated

5. Export → Results saved
   - Spectrum (EMSA, CSV, etc.)
   - Plots (PNG, SVG, JPG)
   - Intensities (CSV)
```

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
- Model object is recreated (new ID)

---

## Fitting Approach

### Model Creation

The fitting process uses HyperSpy/exspy's `EDSTEMModel`:

```python
# Create model
self.signal.set_elements(elements)
self.model = self.signal.create_model(
    auto_add_lines=True,      # Add X-ray lines automatically
    auto_background=True       # Add polynomial background
)
self.model.add_family_lines()  # Add all lines for each element family
```

### Two Fitting Modes

#### Mode 1: `bg_fit_mode = 'bg_elements'`
**Use case**: No background spectrum available, but know instrument elements

```python
# Add background elements to model temporarily
all_elements = sample_elements + bg_elements
self.signal.set_elements(all_elements)
self.model = self.signal.create_model(...)
self.model.fit()
# Restore sample elements only
self.signal.set_elements(sample_elements)
```

**Model components**:
- X-ray lines for sample elements
- X-ray lines for background elements
- Polynomial background

#### Mode 2: `bg_fit_mode = 'bg_spec'` ⭐ **PREFERRED**
**Use case**: Have measured background spectrum (recommended for accuracy)

```python
# Create model with sample elements only
self.signal.set_elements(sample_elements)
self.model = self.signal.create_model(...)

# Add background spectrum as ScalableFixedPattern
comp_bg = hs.model.components1D.ScalableFixedPattern(background_signal)
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
- Lower parameter count → faster fitting

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
- Background polynomial: No bounds
- X-ray line intensities: Usually non-negative (≥0)

---

## Background Handling

### Three Correction Modes (`bg_correction_mode`)

#### `'none'` — No Correction
- Use raw spectrum data
- Fastest, simplest
- Use when background is negligible

#### `'subtract_spectra'` — Subtract Measured Background
- Subtract background spectrum from signal before fitting/intensity calculation
- Accounts for different live times automatically
- Applied in `set_unit_and_bg()` method
- Updates `self.signal` to be `_signal - scaled_background`

#### `'subtract_fitted'` — Subtract Fitted Background Component
- Subtract 'instrument' component after fitting
- Only works with `bg_fit_mode='bg_spec'`
- Used for intensity computation: `signal - model.as_signal(component_list=['instrument'])`
- Requires fitted model

### Two Fitting Modes (`bg_fit_mode`)

See [Fitting Approach](#fitting-approach) section above.

**Recommendation**: Use `bg_fit_mode='bg_spec'` with `bg_correction_mode='none'` for most accurate results.

---

## Fine-Tuning Algorithm

Fine-tuning corrects small energy axis shifts and incorrect detector resolution that cause visible residuals after initial fitting.

### Problem

Even after good initial fits, residuals often show:
- **Systematic shifts**: All lines shifted left or right (energy offset error)
- **Wrong widths**: Lines too narrow or too broad (resolution parameter error)

These cause poor chi-square even when element selection is correct.

### Solution: Sequential Calibration

```python
def fine_tune_model(self):
    """
    Four-step calibration process:
    1. Offset calibration (all params free)
    2. Background shift refinement (bg_spec mode only)
    3. Resolution calibration (LOCKED PARAMS for speed)
    4. Final refinement fit
    """
```

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

**Example output**:
```
After offset calibration:
  Offset: 0.001914 keV (Δ = +4.07 eV)
  χ²ᵣ: 615.61 (Δ = -131.42, -17.6%)
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
#### Step 3: Energy Resolution Calibration ⭐ **KEY OPTIMIZATION**
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
  Resolution: 126.53 eV (Δ = -1.47 eV)
  χ²ᵣ: 585.38 (Δ = -30.23, -4.9%)
```

**Critical**: Without parameter locking, this step is 20-25x slower and can freeze the GUI!

#### Step 4: Final Refinement Fit
**Goal**: Re-optimize all parameters with corrected energy axis

```python
# All parameters free for final fit
self.model.fit()
```

**What it does**:
- Re-fits all component parameters with improved energy calibration
- Typically takes ~1 second
- Typically improves chi-square by additional 3-5%

**Example output**:
```
After final refinement fit:
  χ²ᵣ: 560.47 (Δ = -24.92, -4.3%)
```

### Overall Performance

**Target**: Fine-tuning should be comparable to initial fit time

```
Initial fit:     ~2-4 seconds
Fine-tuning:     ~3-6 seconds
  - Offset calib:              ~1-2s
  - Background shift refine:   ~1s
  - Resolution calib:          ~1s (with locked params)
  - Final fit:                 ~1s
Total improvement: ~25% chi-square reduction
```

**Without parameter locking**:
```
Fine-tuning:     ~85 seconds (14.2x) ❌ SLOW
  - Offset calib:         ~4s
  - Resolution calib:    ~77s (maxfev warnings)
  - Final fit:            ~1s
```

### Why Parameter Locking Works

**Insight**: During resolution calibration, we're only adjusting the width of X-ray lines, not their positions or relative intensities. Therefore:

- ✅ **Resolution parameter must be free**: That's what we're calibrating
- ❌ **Element intensities should be locked**: Relative peak heights don't change
- ❌ **Background coefficients should be locked**: Background shape doesn't significantly change
- ❌ **Offset should be locked**: Already calibrated in step 1

**Result**: Resolution calibration becomes a ~1-parameter optimization instead of a 20-parameter optimization.

### Important Notes

1. **Calibration methods include fitting**: `calibrate_energy_axis()` internally calls fit(), so explicit fit() calls are optional but improve results slightly.

2. **exspy doesn't auto-lock parameters**: The calibration methods in exspy do NOT automatically lock parameters. You must do it manually.

3. **Order matters**: Offset → Resolution → Offset sequence was tested. Final approach uses Offset → Resolution only, with final refinement fit.

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
AUTO_SPECTRUM_FORMATS = ['emsa', 'csv']
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

#### 1. Parameter Locking During Calibration ⭐ **CRITICAL**
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
✓ Fine-tuning time is reasonable (1.0x initial fit time)
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

1. ✅ **Business logic in** `eds_session.py`, **GUI in** `eds_tool.py`
2. ✅ **Lock parameters during resolution calibration** - critical for performance
3. ✅ **Default energy resolution is 128 eV** (not HyperSpy's 133 eV)
4. ✅ **Use bg_spec mode** with ScalableFixedPattern when possible
5. ✅ **Fix `instrument.xscale` at 1.0** - it adds costly nonlinearity with negligible benefit
6. ✅ **Keep `instrument.shift` fixed during the initial fit** - refine it only during fine-tuning if needed
7. ✅ **Force `numexpr` to 1 thread during EDS fitting** - default multithreading is much slower for 4k-channel spectra
8. ✅ **Changing elements triggers auto-refit** - prevents model/element mismatch
9. ✅ **Fine-tuning should stay in the same order of magnitude as the initial fit** - use timing tests to verify
10. ✅ **Calibration methods include fitting** - explicit fit() calls are optional but help
11. ✅ **exspy doesn't auto-lock parameters** - must do manually

**Most Critical Code Section**: Fine-tuning parameter locking (see lines 236-320 in `eds_session.py`)

**Most Common Pitfall**: Forgetting to lock parameters during resolution calibration → 25x performance degradation

**Performance Verification**: Run `test_fine_tune_timing.py` after any changes to fitting/calibration code
