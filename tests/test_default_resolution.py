"""
Test that energy resolution defaults to 128 eV.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession

print("=== Test: Default Energy Resolution ===\n")

# Load spectrum without explicitly setting resolution
session = EDSSession(['grain1_thin.eds'])
rec = session.active_record

resolution = rec.signal.metadata.Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa
print(f"Energy resolution after loading: {resolution} eV")

if resolution == 128:
    print("✓ Default resolution is correctly set to 128 eV")
else:
    print(f"✗ Default resolution should be 128 eV, but got {resolution} eV")

# Test with background
print("\n=== Test: Background Energy Resolution ===\n")
session.set_background('bg_near_grain1_thin.eds')
bg_resolution = rec._background.metadata.Acquisition_instrument.TEM.Detector.EDS.energy_resolution_MnKa
print(f"Background energy resolution: {bg_resolution} eV")

if bg_resolution == 128:
    print("✓ Background resolution is correctly set to 128 eV")
else:
    print(f"✗ Background resolution should be 128 eV, but got {bg_resolution} eV")
