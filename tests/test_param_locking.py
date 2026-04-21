"""
Debug parameter states during fine-tuning to see what's being freed.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession

session = EDSSession(['grain1_thin.eds'])
session.set_elements(['C', 'Cl', 'Cu', 'K', 'Na', 'O', 'S', 'Ca'])
session.set_background('bg_near_grain1_thin.eds')

rec = session.active_record
rec.fit_model()

print(f"Initial χ²ᵣ: {rec.reduced_chisq:.2f}\n")

def print_free_params(label):
    """Print which parameters are free."""
    print(f"\n{label}:")
    free_count = 0
    for comp in rec.model:
        comp_free = []
        for param in comp.parameters:
            if param.free:
                comp_free.append(param.name)
                free_count += 1
        if comp_free:
            print(f"  {comp.name}: {', '.join(comp_free)}")
    print(f"  Total free parameters: {free_count}")
    return free_count

# Check initial state
initial_free = print_free_params("After initial fit")

# Step 1: offset calibration
print("\n\n=== Step 1: calibrate_energy_axis(calibrate='offset') ===")
rec.model.calibrate_energy_axis(calibrate='offset')
after_offset_calib = print_free_params("After offset calibration (before fit)")

rec.model.fit()
after_offset_fit = print_free_params("After offset fit")

# Step 2: resolution calibration
print("\n\n=== Step 2: calibrate_energy_axis(calibrate='resolution') ===")
rec.model.calibrate_energy_axis(calibrate='resolution')
after_res_calib = print_free_params("After resolution calibration (before fit)")

print("\n>>> This is where it might hang or take very long...")
