# %%
import hyperspy.api as hs
import matplotlib.pyplot as plt
from exspy.models import EDSTEMModel
import exspy

# %%
# Background spectrum from empty region, contains contributions from microscope, holder, grid
spec_bg = hs.load('bg_near_grain1_thin.eds')
# Background elements. Those depend on the aperture and holder
bg_elements = ['Cu', 'Au', 'Cr', 'Sn', 'Fe', 'Si'] + ['C', 'Nb', 'Mo'] # C, Nb, Mo if thin-foil aperture is used; absent with top-hat aperture

# Actual spectrum
spec = hs.load('grain1_thin.eds')
# Elements present in the actual sample
model_elements = ['Na', 'S', 'K', 'Si', 'Cu', 'C', 'O', 'Cl']

spec_bg.set_elements(bg_elements)
spec.set_elements(model_elements)

# %%
# For BG fitting, do you want to include spurious elements in the fits, or use a BG spectrum?
use_bg_for_model = True

if use_bg_for_model:
    # Create background model component
    comp_bg = hs.model.components1D.ScalableFixedPattern(spec_bg)
    comp_bg.name = 'instrument'

    # Create full model
    spec.set_elements(model_elements)
    model = spec.create_model(auto_add_lines=True, auto_background=True)
    model.add_family_lines()
    model.append(comp_bg)
    
else:
    # Add background elements to the model
    spec.set_elements(model_elements + bg_elements)
    model = spec.create_model(auto_add_lines=True, auto_background=True)

# %%
# Fit model and plot
model.fit()
model.plot(xray_lines=True)

# %%
# Get clean spectrum without instrument background
spec_clean = spec - model.as_signal(component_list=['instrument'])

# Create model for clean spectrum by omitting instrument from original model
model_clean = spec_clean.create_model(auto_add_lines=False, auto_background=False)
model_clean.extend([m for m in model if m.name != 'instrument'])
# model_clean.fit() # this is actually not necessary since only the background component needs to be adjusted
model_clean.plot(xray_lines=True)


