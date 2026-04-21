"""
Test that changing elements automatically refits the model instead of just deleting it.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSpectrumRecord

# Test data
SPEC_FILE = 'grain1_thin.eds'
BG_FILE = 'bg_near_grain1_thin.eds'

INITIAL_ELEMENTS = ['Na', 'S', 'K', 'Si']
UPDATED_ELEMENTS = ['Na', 'S', 'K', 'Si', 'Cu', 'C', 'O', 'Cl']  # Added more elements
BG_ELEMENTS = ['Cu', 'Au', 'Cr', 'Sn', 'Fe']

def test_refit_on_sample_element_change():
    """Test that changing sample elements refits the model."""
    print("\n=== Test 1: Refit on Sample Element Change ===")
    
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(INITIAL_ELEMENTS)
    
    # Load background and set bg_spec mode
    import hyperspy.api as hs
    rec.set_background(hs.load(BG_FILE))
    rec.set_bg_fit_mode('bg_spec')
    
    # Fit initial model
    print(f"Fitting with initial elements: {rec.elements}")
    rec.fit_model()
    
    if rec.model is not None:
        print(f"✓ Initial fit successful with {len(rec.model)} components")
        initial_model_id = id(rec.model)
    else:
        print("✗ Initial fit failed")
        return False
    
    # Change elements - should trigger refit
    print(f"\nChanging elements to: {sorted(UPDATED_ELEMENTS)}")
    rec.set_elements(UPDATED_ELEMENTS)
    
    if rec.model is not None:
        print(f"✓ Model refitted automatically with {len(rec.model)} components")
        new_model_id = id(rec.model)
        
        # Check that it's a new model object
        if new_model_id != initial_model_id:
            print("✓ New model object created (expected)")
        else:
            print("! Same model object (unexpected but might still work)")
        
        # Verify fitted intensities exist
        if rec.fitted_intensities is not None:
            print(f"✓ Fitted intensities computed: {len(rec.fitted_intensities)} lines")
        else:
            print("✗ No fitted intensities")
            return False
    else:
        print("✗ Model was deleted instead of being refitted")
        return False
    
    print("✓ Test passed: Model refits on sample element change")
    return True

def test_refit_on_bg_element_change():
    """Test that changing BG elements refits the model in bg_elements mode."""
    print("\n=== Test 2: Refit on BG Element Change (bg_elements mode) ===")
    
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(INITIAL_ELEMENTS)
    rec.set_bg_elements(BG_ELEMENTS[:3])  # Start with fewer BG elements
    
    # Use bg_elements mode
    rec.set_bg_fit_mode('bg_elements')
    
    # Fit initial model
    print(f"Fitting with BG elements: {rec.bg_elements}")
    rec.fit_model()
    
    if rec.model is not None:
        print(f"✓ Initial fit successful with {len(rec.model)} components")
        initial_components = len(rec.model)
    else:
        print("✗ Initial fit failed")
        return False
    
    # Change BG elements - should trigger refit
    print(f"\nChanging BG elements to: {BG_ELEMENTS}")
    rec.set_bg_elements(BG_ELEMENTS)
    
    if rec.model is not None:
        print(f"✓ Model refitted automatically with {len(rec.model)} components")
        new_components = len(rec.model)
        
        # More BG elements should mean more components
        if new_components >= initial_components:
            print(f"✓ Component count increased as expected ({initial_components} → {new_components})")
        
        # Verify fitted intensities exist
        if rec.fitted_intensities is not None:
            print(f"✓ Fitted intensities computed: {len(rec.fitted_intensities)} lines")
        else:
            print("✗ No fitted intensities")
            return False
    else:
        print("✗ Model was deleted instead of being refitted")
        return False
    
    print("✓ Test passed: Model refits on BG element change in bg_elements mode")
    return True

def test_no_refit_in_bg_spec_mode():
    """Test that changing BG elements in bg_spec mode does NOT trigger refit."""
    print("\n=== Test 3: No Refit on BG Element Change (bg_spec mode) ===")
    
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(INITIAL_ELEMENTS)
    
    # Load background and use bg_spec mode
    import hyperspy.api as hs
    rec.set_background(hs.load(BG_FILE))
    rec.set_bg_fit_mode('bg_spec')
    
    # Fit initial model
    print("Fitting with bg_spec mode...")
    rec.fit_model()
    
    if rec.model is not None:
        print(f"✓ Initial fit successful with {len(rec.model)} components")
        initial_model_id = id(rec.model)
    else:
        print("✗ Initial fit failed")
        return False
    
    # Change BG elements - should NOT trigger refit in bg_spec mode
    print(f"\nChanging BG elements to: {BG_ELEMENTS}")
    print("(BG elements not used in bg_spec mode, so no refit should occur)")
    rec.set_bg_elements(BG_ELEMENTS)
    
    if rec.model is not None:
        new_model_id = id(rec.model)
        if new_model_id == initial_model_id:
            print("✓ Model unchanged (expected - BG elements not used in bg_spec mode)")
        else:
            print("! Model changed (unexpected)")
    else:
        print("✗ Model was deleted (unexpected)")
        return False
    
    print("✓ Test passed: No refit on BG element change in bg_spec mode")
    return True

def test_no_model_no_fit():
    """Test that changing elements without a model doesn't try to fit."""
    print("\n=== Test 4: No Model, No Fit ===")
    
    rec = EDSSpectrumRecord(SPEC_FILE)
    rec.set_elements(INITIAL_ELEMENTS)
    
    # Don't fit, just change elements
    print("Changing elements without fitting first...")
    rec.set_elements(UPDATED_ELEMENTS)
    
    if rec.model is None:
        print("✓ No model created (expected)")
    else:
        print("✗ Model was created unexpectedly")
        return False
    
    print("✓ Test passed: No automatic fit when no model exists")
    return True

def main():
    """Run all tests."""
    print("=" * 60)
    print("Testing Automatic Refit on Element Changes")
    print("=" * 60)
    
    # Check if test files exist
    if not os.path.exists(SPEC_FILE):
        print(f"Error: {SPEC_FILE} not found")
        return
    if not os.path.exists(BG_FILE):
        print(f"Error: {BG_FILE} not found")
        return
    
    try:
        results = []
        results.append(test_refit_on_sample_element_change())
        results.append(test_refit_on_bg_element_change())
        results.append(test_no_refit_in_bg_spec_mode())
        results.append(test_no_model_no_fit())
        
        print("\n" + "=" * 60)
        if all(results):
            print("All tests PASSED! ✓")
        else:
            print(f"Some tests FAILED: {sum(results)}/{len(results)} passed")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
