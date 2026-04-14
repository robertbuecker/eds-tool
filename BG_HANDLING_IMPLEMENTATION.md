# Background Handling Implementation Summary

## Overview
Successfully integrated sophisticated background handling using the `ScalableFixedPattern` component from HyperSpy, following the elegant approach demonstrated in `archive/prototypes/bg_fit_prototype.py`.

## Core Features Implemented

### 1. EDSSpectrumRecord Enhancements

#### New Attributes
- `bg_elements`: List[str] - Elements from background (instrument, holder, grid, etc.)
- `bg_fit_mode`: str - Either 'bg_elements' or 'bg_spec'
- `bg_correction_mode`: str - 'none', 'subtract_fitted', or 'subtract_spectra'

#### Background Fit Modes

**BG Elements Mode** (`bg_fit_mode='bg_elements'`)
- Temporarily adds BG elements to sample elements during fitting
- Creates model with all elements (sample + BG)
- After fitting, restores original sample elements
- When plotted with fit, displays all element lines (sample + BG)

**BG Spec Mode** (`bg_fit_mode='bg_spec'`) - **RECOMMENDED**
- Uses `ScalableFixedPattern` component with background spectrum
- Creates model with only sample elements
- Adds 'instrument' component for scalable background subtraction
- More accurate and faster than BG Elements mode
- Automatically selected when background spectrum is loaded

#### Background Correction Modes (for Intensities)

**No BG Correction** (`bg_correction_mode='none'`)
- Uses raw signal for intensity calculations
- Default mode

**Subtract Fitted BG** (`bg_correction_mode='subtract_fitted'`)
- Requires fitted model with 'instrument' component
- Creates clean spectrum: `signal - model['instrument']`
- Equivalent to `spec_clean` in the prototype notebook
- Uses cleaned spectrum for intensity calculations
- Falls back to 'none' if no suitable model exists

**Subtract Spectra** (`bg_correction_mode='subtract_spectra'`)
- Direct subtraction of background spectrum (scaled by live time)
- Legacy method, works without fitting
- Updates the signal directly

### 2. EDSSession Integration

All background settings propagate across all records:
- `set_bg_elements(elements)` - Set BG elements for all spectra
- `set_bg_fit_mode(mode)` - Set fit mode for all spectra
- `set_bg_correction_mode(mode)` - Set correction mode for all spectra
- `set_background(bg_path)` - Load BG spectrum for all spectra

Settings are inherited when new spectra are loaded into an existing session.

### 3. GUI Updates

#### New Controls

**BG Elements Entry Field** (below Sample Elements)
- Enter comma-separated BG element symbols
- Automatically applied on text change
- Disabled when "BG Spec" fit mode is selected

**Fit Background Option Menu** (below Fit buttons)
- "BG Elements" - Uses bg_elements fit mode
- "BG Spec (recommended)" - Uses ScalableFixedPattern (default)
- When BG Spec is selected without loaded BG, prompts to load one
- Automatically selected when BG spectrum is loaded

**BG Correction Option Menu** (replaces "Apply BG correction" checkbox)
- "No BG correction" - No background correction for intensities
- "Subtract fitted BG" - Uses fitted instrument component for correction
- "Subtract spectra" - Direct spectral subtraction

## Testing

Comprehensive test suites created:

### archive/manual-tests/test_bg_handling.py
Tests EDSSpectrumRecord functionality:
- Basic loading and element setting
- BG elements mode fitting
- BG spec mode with ScalableFixedPattern
- All three BG correction modes
- Fallback behavior when model unavailable

### archive/manual-tests/test_session_bg_handling.py
Tests EDSSession integration:
- Session loading and element propagation
- BG elements and settings propagation
- BG spectrum loading across all records
- Fit mode propagation
- Correction mode propagation
- Fitting all models with bg_spec mode
- Intensities with different correction modes
- Settings inheritance for newly loaded spectra

All tests pass successfully! ✓

## Usage Example

```python
from eds_session import EDSSession

# Load spectra
session = EDSSession(['grain1_thin.eds', 'grain1_thick.eds'])

# Set sample elements
session.set_elements(['Na', 'S', 'K', 'Si', 'Cu', 'C', 'O', 'Cl'])

# Load background spectrum
session.set_background('bg_near_grain1_thin.eds')

# Set fit mode (automatically done when loading BG)
session.set_bg_fit_mode('bg_spec')  # Uses ScalableFixedPattern

# Fit all spectra
session.fit_all_models()

# Set correction mode for intensity calculations
session.set_bg_correction_mode('subtract_fitted')

# Compute intensities (will use cleaned spectrum)
session.compute_all_intensities()
```

## Technical Details

### Signal.quantity Metadata
The `Signal.quantity` field now reflects the current state:
- "X-rays (Counts)" - counts, no BG correction
- "X-rays (Counts, BG)" - counts, spectral subtraction
- "X-rays (Counts, BG Fitted)" - counts, fitted BG subtraction
- "X-rays (CPS)" - counts per second, no BG correction
- "X-rays (CPS, BG)" - CPS, spectral subtraction
- "X-rays (CPS, BG Fitted)" - CPS, fitted BG subtraction

### Model Persistence
Changing `bg_correction_mode` does NOT invalidate the fitted model.
The model remains valid because:
- It was fitted on the original data
- BG correction is applied during intensity calculation, not fitting
- Only fitted_intensities remain valid; summed intensities are recomputed

### Backward Compatibility
Legacy methods preserved:
- `set_unit_and_bg(unit, bg_correct)` - maps bool to 'none'/'subtract_spectra'
- `set_unit(unit)` - preserves current BG state
- `set_bg_correction(active)` - maps bool to correction mode

## Files Modified

1. **eds_session.py**
   - Enhanced EDSSpectrumRecord with new background handling
   - Updated EDSSession with propagation methods
   - Added helper methods for mode management

2. **eds_tool.py**
   - Updated GUI with new controls
   - Implemented handler methods for new combo boxes
   - Updated spectrum change handler to sync UI state

3. **Test files created**
   - archive/manual-tests/test_bg_handling.py
   - archive/manual-tests/test_session_bg_handling.py

## Recommendations

1. **Use "BG Spec (recommended)" mode** when possible
   - More accurate than BG Elements
   - Faster fitting (fewer components)
   - Cleaner separation of sample and instrument signals

2. **Use "Subtract fitted BG" correction** for intensities
   - Most accurate after fitting
   - Accounts for actual fitted background
   - Falls back gracefully if model unavailable

3. **Element Management**
   - Only put sample elements in "Elements" field
   - Put instrument/holder elements in "BG Elements" field (only used with BG Elements fit mode)
   - When using BG Spec mode, BG Elements entry is disabled (not needed)

## Future Enhancements (Optional)

- Export clean spectra option
- Visualize instrument component separately
- Support for multiple background spectra
- Per-spectrum BG settings (currently session-wide)
