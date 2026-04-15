# EDS Tool Manual Test Review

This document reviews the manual tests in this directory and identifies which ones remain useful for development, debugging, and performance monitoring.

## Summary

**Total tests**: 31  
**Recommended to keep**: 8-10 key tests  
**Can be archived/removed**: ~21 tests (mostly exploration/debug scripts)

---

## Essential Tests (Keep & Maintain)

### Performance & Timing Tests

#### `test_fine_tune_timing.py` ⭐ **CRITICAL**
**Purpose**: Benchmark fine-tuning performance  
**What it tests**: 
- Initial fit time vs fine-tuning time
- Chi-square improvement from fine-tuning
- Detects if fine-tuning is unreasonably slow (>3x initial fit)

**Why keep**: Essential for detecting performance regressions in fine-tuning

**Current baseline**: Fine-tuning should be ~1.0x the initial fit time (~6 seconds)

---

### Background Handling Tests

#### `test_bg_handling.py` ⭐ **IMPORTANT**
**Purpose**: Test background handling modes  
**What it tests**:
- Basic loading and element setting
- `bg_elements` mode (adding background elements to model)
- `bg_spec` mode (using ScalableFixedPattern with background spectrum)
- Switching between modes

**Why keep**: Core functionality for background subtraction approaches

#### `test_session_bg_handling.py` ⭐ **IMPORTANT**
**Purpose**: Test background handling at session level  
**What it tests**:
- Setting background for entire session
- Integration with EDSSession API
- Background propagation to all spectra

**Why keep**: Tests session-level background API

---

### Element & Refit Tests

#### `test_refit_on_element_change.py` ⭐ **IMPORTANT**
**Purpose**: Test automatic refitting when elements change  
**What it tests**:
- Changing sample elements triggers refit
- Changing background elements triggers refit
- Model is properly updated (new object created)

**Why keep**: Critical for GUI usability - ensures model stays consistent with element selection

---

### Calibration & Resolution Tests

#### `test_default_resolution.py` ⭐ **IMPORTANT**
**Purpose**: Verify default energy resolution is 128 eV  
**What it tests**:
- Spectrum loads with 128 eV resolution (not HyperSpy default of 133 eV)
- Background spectrum also gets 128 eV

**Why keep**: Regression test for important default value correction

#### `test_calibrate_includes_fit.py` ⭐ **USEFUL**
**Purpose**: Investigate if calibration methods include internal fitting  
**What it tests**:
- Whether `calibrate_energy_axis()` changes chi-square
- Performance of calibration with/without explicit `fit()` call
- Timing comparison

**Why keep**: Documents important behavior of exspy calibration methods that affects our fine-tuning implementation

---

### Parameter Locking Tests

#### `test_param_locking.py` ⭐ **USEFUL**
**Purpose**: Debug which parameters are free during calibration  
**What it tests**:
- Parameter states before/after each calibration step
- Whether calibration methods lock/unlock parameters
- Maxfev warnings during resolution calibration

**Why keep**: Useful for debugging fine-tuning issues; documents that exspy calibration doesn't lock parameters automatically

---

### GUI Tests

#### `test_fine_tune_gui.py` ⭐ **USEFUL**
**Purpose**: Interactive GUI test for fine-tuning  
**What it tests**:
- Fine-tune button functionality
- GUI responsiveness during fine-tuning
- Visual feedback of chi-square improvement

**Why keep**: Manual integration test for GUI fine-tuning workflow

---

## Exploration/Debug Tests (Can Archive)

These tests were useful during development but are now superseded or no longer needed:

### Fine-tuning Exploration (Superseded)
- `test_fine_tune.py` - Basic fine-tuning test (superseded by test_fine_tune_timing.py)
- `test_fine_tune_comprehensive.py` - Multi-spectrum test (covered by GUI tests)
- `test_fine_tune_debug.py` - Debug output (used for investigation, not needed now)
- `test_fine_tune_updated.py` - Exploration version (superseded by final implementation)
- `test_fine_tune_no_extra_fits.py` - Performance experiment (findings incorporated into final impl)

### Calibration Exploration (Findings Documented)
- `test_calibrate_resolution.py` - Resolution calibration exploration
- `test_calibration_debug.py` - Debug script
- `test_calibration_steps.py` - Step-by-step calibration investigation
- `test_calibration_with_fit.py` - Calibration + fit timing
- `test_offset_only.py` - Offset-only calibration test
- `test_resolution_workflow.py` - Resolution workflow exploration
- `test_xray_manual_calib.py` - Manual X-ray line calibration (abandoned approach)
- `test_xray_params.py` - X-ray parameter investigation

### Parameter Investigation (Findings Documented)
- `test_bounds.py` - Parameter bounds exploration
- `test_param_bounds_api.py` - Bounds API investigation  
- `test_param_structure.py` - Parameter structure investigation
- `test_count_params.py` - Count free parameters
- `test_line_positions.py` - Line position investigation

### Other
- `test_auto_cli.py` - Auto workflow CLI test (covered by actual CLI)
- `test_bg_fit_warning.py` - Warning message test (specific bug fix)
- `test_bg_warning_dialog.py` - GUI warning dialog test (specific feature)
- `test_chisq_and_background.py` - Chi-square with background exploration
- `test_energy_resolution.py` - Resolution setting test (covered by test_default_resolution.py)
- `test_session_methods.py` - General session method tests (covered by other tests)

---

## Recommended Test Suite Structure

For a cleaner test organization, keep these 8-10 essential tests:

### Core Functionality (5 tests)
1. `test_bg_handling.py` - Background handling
2. `test_session_bg_handling.py` - Session-level background
3. `test_refit_on_element_change.py` - Auto-refit on element change
4. `test_default_resolution.py` - Default resolution value
5. `test_fine_tune_gui.py` - GUI fine-tuning workflow

### Performance & Debugging (3-5 tests)
6. `test_fine_tune_timing.py` - Fine-tuning performance benchmark ⭐
7. `test_calibrate_includes_fit.py` - Calibration behavior documentation
8. `test_param_locking.py` - Parameter state debugging

*Optional extras:*
- Keep 1-2 exploration tests if actively investigating a specific feature
- Keep any tests that document known bugs or edge cases

---

## Key Findings Documented in Tests

### Fine-tuning Performance (from test_fine_tune_timing.py)
- **Target**: Fine-tuning should be ~1.0x initial fit time (6-7 seconds)
- **Problem solved**: Was 11-14x slower (80-90 seconds) due to all parameters being free during resolution calibration
- **Solution**: Lock all parameters except resolution during `calibrate_energy_axis(calibrate='resolution')`

### Calibration Behavior (from test_calibrate_includes_fit.py)
- **Finding**: `calibrate_energy_axis()` includes internal fitting
- **Impact**: No need for explicit `fit()` after offset calibration, but a final fit helps refine results
- **Timing**: Resolution calibration with locked params: ~3s; with all params free: ~77s (maxfev warnings)

### Parameter Locking (from test_param_locking.py)
- **Finding**: exspy calibration methods do NOT automatically lock parameters
- **Impact**: Must manually lock parameters before resolution calibration for speed
- **Implementation**: Lock all component parameters, let `calibrate_energy_axis` unlock only resolution param

### Default Resolution (from test_default_resolution.py)
- **Correct value**: 128 eV (HyperSpy defaults to 133 eV)
- **Implementation**: Set in `EDSSpectrumRecord.__init__()` via `set_microscope_parameters(energy_resolution_MnKa=128)`
- **Applies to**: Both main spectrum and background spectrum

---

## Running the Essential Tests

All tests use the standard test data files:
- `grain1_thin.eds` / `grain1_thick.eds` - Sample spectra
- `bg_near_grain1_thin.eds` / `bg_near_grain1_thick.eds` - Background spectra

Standard elements for test spectrum:
```python
SAMPLE_ELEMENTS = ['C', 'Cl', 'Cu', 'K', 'Na', 'O', 'S', 'Ca']
```

Run from project root:
```bash
# Performance benchmark (most important)
python archive/manual-tests/test_fine_tune_timing.py

# Background handling
python archive/manual-tests/test_bg_handling.py

# Auto-refit behavior  
python archive/manual-tests/test_refit_on_element_change.py

# Default resolution check
python archive/manual-tests/test_default_resolution.py

# GUI integration (interactive)
python archive/manual-tests/test_fine_tune_gui.py
```

---

## Maintenance Notes

**When to run performance tests:**
- After any changes to `fine_tune_model()` method
- After updating exspy/hyperspy library versions
- When investigating GUI freezing or slowness

**When to update this document:**
- When adding new essential tests
- When discovering new important behaviors through tests
- When creating tests for new features

**Test hygiene:**
- Archive exploration tests once findings are documented
- Keep only one test per distinct feature/behavior
- Update test expectations when implementation deliberately changes
