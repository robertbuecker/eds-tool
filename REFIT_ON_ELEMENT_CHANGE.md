# Automatic Refit on Element Changes

## Overview
Improved the behavior when elements are changed while a fitted model exists. Previously, the fit would simply be deleted. Now, the model is automatically refitted with the new elements.

## Changes Made

### EDSSpectrumRecord.set_elements()
**Old Behavior**: Deleted the model when elements changed
```python
self.model = None
self.fitted_intensities = None
```

**New Behavior**: Automatically refits if a model existed
```python
if had_model:
    print(f"Refitting model for {self.name} with updated elements...")
    self.fit_model()
else:
    self.model = None
    self.fitted_intensities = None
```

### EDSSpectrumRecord.set_bg_elements()
**Old Behavior**: Deleted the model when BG elements changed (in bg_elements mode)

**New Behavior**: Automatically refits if a model existed and bg_fit_mode is 'bg_elements'
```python
if self.model is not None and self.bg_fit_mode == 'bg_elements':
    print(f"Refitting model for {self.name} with updated BG elements...")
    self.fit_model()
```

Note: In 'bg_spec' mode, changing BG elements has no effect since BG elements are not used in that mode.

## Benefits

1. **Faster Workflow**: No need to manually refit after changing elements
2. **Fast Refitting**: Since initial values are close, refitting is quick
3. **Consistent State**: Model always reflects current element configuration
4. **User-Friendly**: More intuitive behavior in GUI

## Test Coverage

Created comprehensive test suite (`archive/manual-tests/test_refit_on_element_change.py`) covering:

✓ **Test 1**: Refit on sample element change
- Model refits automatically when sample elements are modified
- New model object created with updated components

✓ **Test 2**: Refit on BG element change (bg_elements mode)
- Model refits when BG elements change in bg_elements mode
- Component count increases as expected

✓ **Test 3**: No refit in bg_spec mode
- BG element changes don't trigger refit in bg_spec mode (correct behavior)
- Model remains unchanged since BG elements are not used

✓ **Test 4**: No automatic fit without existing model
- No fit is triggered if no model existed before element change
- Maintains expected behavior for initial element setting

All tests PASS! ✓

## Usage Example

### GUI Workflow
1. Load a spectrum
2. Set initial elements (e.g., "Na,S,K,Si")
3. Click "Fit (sel)" - model is fitted
4. Add more elements (e.g., "Na,S,K,Si,Cu,C,O,Cl")
5. **Model is automatically refitted** with new elements
6. No need to manually click "Fit" again!

### Programmatic Usage
```python
from eds_session import EDSSpectrumRecord

rec = EDSSpectrumRecord('spectrum.eds')
rec.set_elements(['Na', 'S', 'K', 'Si'])
rec.fit_model()  # Fit with 4 elements

# Add more elements - automatic refit!
rec.set_elements(['Na', 'S', 'K', 'Si', 'Cu', 'C', 'O', 'Cl'])
# Model is now fitted with 8 elements
```

## Implementation Details

### When Refit Occurs
- **Sample elements changed**: Always refits (if model exists)
- **BG elements changed**: Only refits in bg_elements mode (if model exists)
- **No existing model**: No automatic fit (normal behavior)

### Refit Speed
- Fast because initial parameter values are close to optimal
- Model uses auto_add_lines() which intelligently adds new lines
- Background model component (if present) retains its fitted state

## Files Modified
- `eds_session.py`: Updated `set_elements()` and `set_bg_elements()` methods

## Files Created
- `archive/manual-tests/test_refit_on_element_change.py`: Comprehensive test suite
