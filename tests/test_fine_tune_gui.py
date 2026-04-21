"""
Manual GUI test for fine-tuning functionality.

Instructions:
1. Run this script
2. Fit the spectrum first using the "Fit (sel)" button
3. Click "Fine-tune (sel)" to fine-tune the model
4. Observe the chi-square value change and residuals improve

Expected behavior:
- Fine-tune button is clickable only after fitting
- Chi-square may improve after fine-tuning
- Residuals should be reduced, especially systematic offsets
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from qtpy import QtWidgets
from eds_tool import NavigatorWidget
from eds_session import EDSSession

def test_gui():
    """
    Launch the GUI and test fine-tuning functionality.
    """
    app = QtWidgets.QApplication(sys.argv)
    
    # Create session with test spectrum and background
    session = EDSSession(['grain1_thin.eds'])
    session.set_elements(['C', 'Cl', 'Cu', 'K', 'Na', 'O', 'S', 'Ca'])
    session.set_background('bg_near_grain1_thin.eds')
    
    # Create GUI
    nav = NavigatorWidget(session)
    
    print("\n" + "="*60)
    print("GUI TEST: Fine-tune Model")
    print("="*60)
    print("Instructions:")
    print("1. Click 'Fit (sel)' button to fit the model")
    print("2. Note the χ²ᵣ value")
    print("3. Enable 'Show residual' to see the fit residuals")
    print("4. Click 'Fine-tune (sel)' to optimize the model")
    print("5. Observe changes in χ²ᵣ and residuals")
    print("6. Close the window when done")
    print("="*60 + "\n")
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    test_gui()
