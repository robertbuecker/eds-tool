"""
Test fine-tuning with timing to ensure it's fast.
"""
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eds_session import EDSSession

def test_fine_tune_timing():
    """Test fine-tuning performance"""
    print("\n=== Test: Fine-tune Timing ===")
    
    # Create session and load spectrum
    session = EDSSession(['grain1_thin.eds'])
    session.set_elements(['C', 'Cl', 'Cu', 'K', 'Na', 'O', 'S', 'Ca'])
    session.set_background('bg_near_grain1_thin.eds')
    
    # Fit model
    rec = session.active_record
    print("Initial fit...")
    start = time.time()
    rec.fit_model()
    fit_time = time.time() - start
    
    print(f"  Initial fit took: {fit_time:.2f}s")
    print(f"  Initial χ²ᵣ: {rec.reduced_chisq:.4f}")
    
    # Fine-tune
    print("\nFine-tuning...")
    start = time.time()
    rec.fine_tune_model()
    finetune_time = time.time() - start
    
    print(f"  Fine-tune took: {finetune_time:.2f}s")
    print(f"  After fine-tuning χ²ᵣ: {rec.reduced_chisq:.4f}")
    print(f"  Improvement: {(1 - rec.reduced_chisq/6605.1745)*100:.1f}%")
    
    if finetune_time > fit_time * 3:
        print(f"\n⚠ Warning: Fine-tuning took {finetune_time/fit_time:.1f}x longer than initial fit!")
        print("  This suggests parameters are not properly locked.")
    else:
        print(f"\n✓ Fine-tuning time is reasonable ({finetune_time/fit_time:.1f}x initial fit time)")

if __name__ == "__main__":
    test_fine_tune_timing()
