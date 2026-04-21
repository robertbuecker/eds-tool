"""
Test if calibration methods already include fitting.
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession

session = EDSSession(['grain1_thin.eds'])
session.set_elements(['C', 'Cl', 'Cu', 'K', 'Na', 'O', 'S', 'Ca'])
session.set_background('bg_near_grain1_thin.eds')

rec = session.active_record
rec.fit_model()

initial_chisq = float(rec.model.red_chisq.data.item())
print(f"Initial χ²ᵣ: {initial_chisq:.2f}\n")

# Test 1: Just calibrate_energy_axis without explicit fit()
print("Test 1: calibrate_energy_axis(calibrate='offset') WITHOUT explicit fit()")
start = time.time()
rec.model.calibrate_energy_axis(calibrate='offset')
elapsed = time.time() - start
chisq = float(rec.model.red_chisq.data.item())
print(f"  Time: {elapsed:.2f}s")
print(f"  χ²ᵣ: {chisq:.2f}")
print(f"  Chi-square changed? {chisq != initial_chisq}")

# Reset
rec.fit_model()

# Test 2: calibrate_energy_axis WITH explicit fit()
print("\nTest 2: calibrate_energy_axis(calibrate='offset') WITH explicit fit()")
start = time.time()
rec.model.calibrate_energy_axis(calibrate='offset')
rec.model.fit()
elapsed = time.time() - start
chisq = float(rec.model.red_chisq.data.item())
print(f"  Time: {elapsed:.2f}s")
print(f"  χ²ᵣ: {chisq:.2f}")
