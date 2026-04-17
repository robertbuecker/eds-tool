# EDS Tool Test Suite

This directory contains the essential tests for the EDS Tool. These tests verify core functionality, performance, and correct behavior after code changes.

**Last Updated**: 2026-04-16  
**Total Tests**: 8 (7 automated + 1 manual GUI test)

---

## Quick Start

Run all automated tests from the project root:

```bash
# Core functionality tests
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_default_resolution.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_bg_handling.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_session_bg_handling.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_refit_on_element_change.py

# Performance & behavior tests
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fine_tune_timing.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_calibrate_includes_fit.py
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_param_locking.py

# Manual GUI test (requires interaction)
powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fine_tune_gui.py
```

---

## Test Categories

### ⚡ Performance Tests

#### `test_fine_tune_timing.py` ⭐ **CRITICAL**

**Purpose**: Benchmark fine-tuning performance to detect regressions

**What it tests**:
- Initial fit time
- Fine-tuning time
- Chi-square improvement
- Detects if fine-tuning becomes unreasonably slow

**Expected Output**:
```
=== Test: Fine-tune Timing ===
Initial fit...
  Initial fit took: ~3s
  Initial χ²ᵣ: ~0.27

Fine-tuning...
=== Fine-tuning grain1_thin ===
Initial χ²ᵣ: ~0.27
Initial offset: -0.002152 keV
Initial resolution: 128.00 eV
Initial BG shift: 0.000000 keV

After offset calibration:
  Offset: 0.002169 keV (Δ = 4.32 eV)
  χ²ᵣ: ~0.21 (Δ ≈ -21%)

After background shift refinement:
  BG shift: 0.002733 keV (Δ = 2.73 eV)
  χ²ᵣ: ~0.21

After resolution calibration (with locked parameters):
  Resolution: 127.21 eV (Δ = -0.79 eV)
  χ²ᵣ: ~0.19 (Δ ≈ -9%)

After final refinement fit:
  χ²ᵣ: ~0.20

--- Summary ---
Total offset change: +4.32 eV
Total resolution change: -0.79 eV
Total BG shift change: +2.73 eV
χ²ᵣ: ~0.27 → ~0.20 (+26.3%)

  Fine-tune took: ~3s
  After fine-tuning χ²ᵣ: ~0.20
  Improvement: chi-square should still improve substantially; absolute values changed after moving the fit/model path to CPS

✓ Fine-tuning time is reasonable (~1.0x initial fit time)
```

**Success Criteria**:
- ✅ Fine-tuning time ≤ 3x initial fit time (ideally ~1.0x)
- ✅ No maxfev warnings
- ✅ Chi-square improves by ~20-30%
- ✅ Absolute χ²ᵣ values may differ from older counts-based runs because the fit/model path is now CPS-normalized
- ✅ Offset change typically 3-5 eV
- ✅ Resolution change typically 1-5 eV

**Failure Indicators**:
- ❌ Fine-tuning >10x initial fit time → Check parameter locking in fine_tune_model()
- ❌ maxfev warnings → Parameters not properly locked during resolution calibration
- ❌ Chi-square increases → Check calibration sequence

**When to Run**:
- After ANY changes to `fine_tune_model()` method
- After updating exspy/hyperspy versions
- Before releases
- When investigating GUI freezing issues

**Files Used**:
- `grain1_thin.eds` - Sample spectrum
- `bg_near_grain1_thin.eds` - Background spectrum

---

### 🔬 Core Functionality Tests

#### `test_default_resolution.py` ⭐

**Purpose**: Verify energy resolution defaults to correct value (128 eV, not HyperSpy's default 133 eV)

**What it tests**:
- Spectrum loads with 128 eV resolution
- Background spectrum also gets 128 eV

**Expected Output**:
```
=== Test: Default Energy Resolution ===

Energy resolution after loading: 128 eV
✓ Default resolution is correctly set to 128 eV

=== Test: Background Energy Resolution ===

Background energy resolution: 128 eV
✓ Background resolution is correctly set to 128 eV
```

**Success Criteria**:
- ✅ Main spectrum: 128 eV (not 133)
- ✅ Background spectrum: 128 eV

**When to Run**:
- After changes to `EDSSpectrumRecord.__init__()`
- After updating HyperSpy/exspy
- Periodically as regression test

**Files Used**:
- `grain1_thin.eds`
- `bg_near_grain1_thin.eds`

---

#### `test_bg_handling.py` ⭐

**Purpose**: Test all background handling modes and fitting modes

**What it tests**:
1. Basic loading and element setting
2. `bg_elements` mode on the CPS-normalized fit signal
3. `bg_spec` mode (ScalableFixedPattern with CPS-normalized background spectrum)
4. Explicit display / peak-sum source modes
5. Rejection of invalid fitted-background subtraction

**Expected Output**:
```
============================================================
Testing EDSSpectrumRecord Background Handling
============================================================

=== Test 1: Basic Loading ===
Loaded: grain1_thin
...
✓ Basic loading test passed

=== Test 2: BG Elements Mode ===
...
Model fitted successfully with 79 components
✓ BG elements mode test passed

=== Test 3: BG Spec Mode (ScalableFixedPattern) ===
...
Model fitted successfully with 21 components
Has 'instrument' component: True
✓ BG spec mode test passed

=== Test 4: BG Correction Modes ===
...
✓ All BG correction modes tested

=== Test 5: Fallback Behavior ===
...
✓ Fallback to no correction works

============================================================
All tests completed!
============================================================
```

**Success Criteria**:
- ✅ bg_elements mode: fit runs on a CPS signal and overlapping BG elements do not expose fitted subtraction
- ✅ bg_spec mode: 21 components (sample + polynomial + instrument)
- ✅ bg_spec mode keeps `instrument.xscale` and `instrument.shift` fixed in the initial fit
- ✅ Explicit signal modes (`raw`, `measured_bg_subtracted`, `fitted_external_bg_subtracted`) work when available
- ✅ Invalid fitted subtraction raises instead of silently falling back

**When to Run**:
- After changes to background handling logic
- After changes to `fit_model()`, explicit signal-mode handling, or legacy `set_bg_correction_mode()`
- Before releases

**Files Used**:
- `grain1_thin.eds`
- `bg_near_grain1_thin.eds`

---

#### `test_session_bg_handling.py` ⭐

**Purpose**: Test that background settings propagate correctly across all spectra in a session

**What it tests**:
1. Session loading of multiple spectra
2. Element propagation to all spectra
3. BG elements propagation
4. Background spectrum loading for all
5. BG fit mode propagation
6. Stable background mode / unit propagation
7. Fitted subtraction availability only when the external background is identifiable
8. Peak-sum intensity computation with different source modes

**Expected Output**:
```
============================================================
Testing EDSSession Background Handling
============================================================

=== Test 1: Session Loading ===
Loaded 2 spectra
✓ Session loading test passed

=== Test 2: Element Propagation ===
...
✓ Element propagation test passed

[... all tests ...]

============================================================
All tests PASSED! ✓
============================================================
```

**Success Criteria**:
- ✅ All spectra get same elements
- ✅ All spectra get same bg_elements
- ✅ All spectra get same background spectrum
- ✅ Stable signal modes and units propagate to all spectra
- ✅ `subtract_fitted` is rejected for overlapping `bg_elements` fits
- ✅ Peak-sum intensities respond to the selected derived source

**When to Run**:
- After changes to `EDSSession` methods
- After changes to background handling
- Before releases

**Files Used**:
- `grain1_thin.eds`
- `grain1_thick.eds`
- `bg_near_grain1_thin.eds`

---

#### `test_refit_on_element_change.py` ⭐

**Purpose**: Verify that changing elements automatically refits the model

**What it tests**:
1. Changing sample elements triggers refit
2. Changing BG elements triggers refit (in bg_elements mode)
3. Changing BG elements does NOT trigger refit (in bg_spec mode, as expected)
4. No automatic fit when no model exists yet

**Expected Output**:
```
============================================================
Testing Automatic Refit on Element Changes
============================================================

=== Test 1: Refit on Sample Element Change ===
...
✓ Model refitted automatically with 21 components
✓ New model object created (expected)
✓ Test passed: Model refits on sample element change

=== Test 2: Refit on BG Element Change (bg_elements mode) ===
...
✓ Component count increased as expected (38 → 55)
✓ Test passed: Model refits on BG element change in bg_elements mode

=== Test 3: No Refit on BG Element Change (bg_spec mode) ===
...
✓ Model unchanged (expected - BG elements not used in bg_spec mode)
✓ Test passed: No refit on BG element change in bg_spec mode

=== Test 4: No Model, No Fit ===
...
✓ No model created (expected)
✓ Test passed: No automatic fit when no model exists

============================================================
All tests PASSED! ✓
============================================================
```

**Success Criteria**:
- ✅ New model object created when elements change (different ID)
- ✅ Component count changes appropriately
- ✅ Fitted intensities updated
- ✅ Correct behavior in both bg_fit_modes
- ✅ No fit when no existing model

**When to Run**:
- After changes to `set_elements()` or `set_bg_elements()`
- After changes to model creation logic
- Before releases

**Files Used**:
- `grain1_thin.eds`
- `bg_near_grain1_thin.eds`

---

### 🔍 Debugging & Behavior Tests

#### `test_calibrate_includes_fit.py`

**Purpose**: Document that exspy's calibration methods include internal fitting

**What it tests**:
- Whether `calibrate_energy_axis()` changes chi-square (yes, it does)
- Performance with/without explicit `fit()` after calibration
- Timing comparison

**Expected Output**:
```
Initial χ²ᵣ: 747.04

Test 1: calibrate_energy_axis(calibrate='offset') WITHOUT explicit fit()
  Time: 3.38s
  χ²ᵣ: 615.61
  Chi-square changed? True

Test 2: calibrate_energy_axis(calibrate='offset') WITH explicit fit()
  Time: 2.59s
  χ²ᵣ: 613.67
```

**Key Findings**:
- ✅ Calibration methods include fitting (chi-square changes)
- ✅ Additional `fit()` after calibration refines results slightly
- ✅ Additional `fit()` is fast (~0.7s)

**Implications for Code**:
- Explicit `fit()` calls after offset calibration are optional but improve results
- Final refinement fit after resolution calibration is recommended

**When to Run**:
- After updating exspy/hyperspy
- When investigating fine-tuning behavior
- As documentation/reference

**Files Used**:
- `grain1_thin.eds`
- `bg_near_grain1_thin.eds`

---

#### `test_param_locking.py`

**Purpose**: Debug which parameters are free during fine-tuning

**What it tests**:
- Parameter states before/after each calibration step
- Whether exspy automatically locks/unlocks parameters
- Where maxfev warnings occur

**Expected Output** (partial - test is designed to show where it might hang):
```
Initial χ²ᵣ: 747.04

After initial fit:
  ScalableFixedPattern: coefficient
  Polynomial: coefficients.a0, coefficients.a1, ... (7 params)
  [Element lines]: coefficient (10 params)
  Total free parameters: 20

=== Step 1: calibrate_energy_axis(calibrate='offset') ===

After offset calibration (before fit):
  Total free parameters: 20

After offset fit:
  Total free parameters: 20

=== Step 2: calibrate_energy_axis(calibrate='resolution') ===

After resolution calibration (before fit):
  Total free parameters: 20

>>> This is where it might hang or take very long...
```

**Key Findings**:
- ✅ exspy calibration methods do NOT automatically lock parameters
- ✅ All 20 parameters stay free throughout calibration
- ✅ Resolution calibration with 20 free params hits maxfev warnings and takes ~77s
- ✅ Manual parameter locking is required for performance

**When to Run**:
- When investigating fine-tuning performance issues
- After updating exspy/hyperspy
- When debugging parameter-related problems
- As documentation/reference

**Files Used**:
- `grain1_thin.eds`
- `bg_near_grain1_thin.eds`

**Note**: This test may run very slowly or appear to hang during resolution calibration if run without the optimized `fine_tune_model()` implementation.

---

### 🖥️ GUI Tests

#### `test_fine_tune_gui.py` (Manual Test)

**Purpose**: Interactive test for GUI fine-tuning workflow

**Type**: Manual (requires user interaction)

**Instructions**:
1. Run the script: `powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python tests\test_fine_tune_gui.py`
2. GUI window opens with loaded spectrum
3. Click "Fit (sel)" button to fit the model
4. Observe initial chi-square value
5. Click "Fine-tune (sel)" button
6. Observe chi-square improvement and residuals

**Expected Behavior**:
- ✅ Fine-tune button is disabled until after fitting
- ✅ Fine-tuning completes in ~6-10 seconds (doesn't freeze GUI)
- ✅ Chi-square improves by ~20-30%
- ✅ Residual plot shows reduced systematic offsets
- ✅ GUI remains responsive throughout

**Success Criteria**:
- ✅ No GUI freezing
- ✅ Progress visible (if progress indicators implemented)
- ✅ Chi-square updates in UI
- ✅ Plot refreshes after fine-tuning

**Failure Indicators**:
- ❌ GUI freezes for >10 seconds → Check fine_tune_model() performance
- ❌ No chi-square improvement → Check calibration logic
- ❌ Error messages → Check error handling

**When to Run**:
- After changes to fine-tuning implementation
- After GUI changes
- Before releases
- When users report GUI freezing

**Files Used**:
- `grain1_thin.eds`
- `bg_near_grain1_thin.eds`

---

## Test Data Files

All tests use the following data files (must be in project root):

```
grain1_thin.eds            - Sample EDS spectrum (thin section)
grain1_thick.eds           - Sample EDS spectrum (thick section)
bg_near_grain1_thin.eds    - Background spectrum for thin section
bg_near_grain1_thick.eds   - Background spectrum for thick section
```

**Standard Test Elements**:
- Sample elements: `['C', 'Cl', 'Cu', 'K', 'Na', 'O', 'S', 'Ca']` (or `['C', 'Cl', 'Cu', 'K', 'Na', 'O', 'S', 'Si']`)
- Background elements: `['Cu', 'Au', 'Cr', 'Sn', 'Fe', 'Si', 'C', 'Nb', 'Mo']`

---

## Test Results Summary (Last Run: 2026-04-15)

| Test | Status | Time | Notes |
|------|--------|------|-------|
| test_default_resolution.py | ✅ PASS | <1s | 128 eV confirmed |
| test_fine_tune_timing.py | ✅ PASS | ~6s | ~1.0x initial fit time |
| test_bg_handling.py | ✅ PASS | ~25s | All modes work |
| test_session_bg_handling.py | ✅ PASS | ~30s | Propagation correct |
| test_refit_on_element_change.py | ✅ PASS | ~20s | Auto-refit works |
| test_calibrate_includes_fit.py | ✅ PASS | ~15s | Behavior documented |
| test_param_locking.py | ⚠️ DEBUG | Variable | Diagnostic tool |
| test_fine_tune_gui.py | ⚠️ MANUAL | N/A | Requires interaction |

**Overall**: ✅ All automated tests passing, no regressions detected

---

## Regression Testing Checklist

Run these tests after:

### Critical Code Changes
- ✅ **test_fine_tune_timing.py** after ANY changes to `fine_tune_model()`
- ✅ **test_default_resolution.py** after changes to `EDSSpectrumRecord.__init__()`
- ✅ **test_bg_handling.py** after changes to background handling logic
- ✅ **test_refit_on_element_change.py** after changes to `set_elements()`

### Library Updates
- ✅ **test_fine_tune_timing.py** after updating exspy/hyperspy
- ✅ **test_calibrate_includes_fit.py** after updating exspy/hyperspy
- ✅ **test_default_resolution.py** after updating HyperSpy

### Before Releases
- ✅ ALL automated tests
- ✅ **test_fine_tune_gui.py** (manual)

### When Users Report Issues
- GUI freezing → **test_fine_tune_timing.py**, **test_fine_tune_gui.py**
- Wrong chi-square values → **test_bg_handling.py**, **test_fine_tune_timing.py**
- Element changes not working → **test_refit_on_element_change.py**

---

## Troubleshooting Test Failures

### test_fine_tune_timing.py Fails

**Symptom**: Fine-tuning takes >20 seconds

**Likely Causes**:
1. Parameters not locked during resolution calibration
2. Old exspy version with performance bugs
3. Test data files missing

**Fix**:
- Check `fine_tune_model()` implementation in `eds_session.py`, lines 236-320
- Verify parameter locking code is present:
  ```python
  # Lock all parameters before resolution calibration
  locked_params = []
  for component in self.model:
      for param in component.parameters:
          if param.free:
              param.free = False
              locked_params.append(param)
  ```

### test_bg_handling.py Fails

**Symptom**: Wrong number of components or missing 'instrument' component

**Likely Causes**:
1. Background spectrum not loaded correctly
2. Model creation logic changed
3. Element list wrong

**Fix**:
- Check `fit_model()` implementation
- Verify ScalableFixedPattern creation:
  ```python
  comp_bg = hs.model.components1D.ScalableFixedPattern(self._background)
  comp_bg.name = 'instrument'
  self.model.append(comp_bg)
  ```

### test_refit_on_element_change.py Fails

**Symptom**: Model not refitting when elements change

**Likely Causes**:
1. Auto-refit logic removed from `set_elements()`
2. Model comparison not working

**Fix**:
- Check `set_elements()` and `set_bg_elements()` implementations
- Verify refit logic is present

### Import Errors

**Symptom**: `ModuleNotFoundError: No module named 'eds_session'`

**Fix**:
- Tests must be run from project root
- Verify sys.path adjustment at top of test files:
  ```python
  import sys
  import os
  sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
  ```

---

## Adding New Tests

When adding new tests to this suite:

1. **Name the test file** `test_<feature>.py`
2. **Add sys.path adjustment** at the top:
   ```python
   import sys
   import os
   sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
   ```
3. **Print clear output** with ✓/✗ indicators
4. **Use standard test data files** (grain1_thin.eds, etc.)
5. **Document expected output** in this file
6. **Add to regression checklist** if relevant
7. **Test the test** - run it to verify it works
8. **Update this README** with test description and expected output

---

## Python Test Framework Considerations

**Note**: These tests are currently standalone Python scripts, not using pytest or unittest frameworks.

**Advantages**:
- Simple to run
- Clear output format
- Easy to debug
- No framework dependencies

**Disadvantages**:
- No test discovery
- Manual execution required
- No test reporting tools

**Future Consideration**: If the test suite grows significantly, consider migrating to pytest for better organization and reporting.

---

## Maintenance

**Test Data**: Keep test data files (`grain1_*.eds`, `bg_near_*.eds`) in project root. Do not modify these files as tests depend on their specific content.

**Performance Baselines**: Update expected timing values in this document if hardware changes or optimizations are made.

**Test Review**: Review this test suite quarterly or after major changes to ensure tests remain relevant and comprehensive.

---

## Contact

For questions about tests or to report test failures, see project documentation.

**Last Test Run**: 2026-04-15  
**Test Runner**: Automated via conda environment `eds-mini`  
**All Tests**: ✅ PASSING
