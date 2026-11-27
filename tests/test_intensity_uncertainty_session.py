"""Real fit, lazy HSPY reload and session CSV uncertainty integration."""
from pathlib import Path
import math
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import numpy as np
import pandas as pd
from eds_session import EDSSession, EDSSpectrumRecord


def main():
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix='uncertainty_') as tmp:
        work = Path(tmp)
        source = work / 'spectrum.eds'
        shutil.copy2(ROOT / 'grain1_thin.eds', source)
        rec = EDSSpectrumRecord(str(source))
        raw = rec._signal.data.copy()
        rec.set_elements(['O', 'Si', 'S', 'Cu'])
        rec.set_bg_fit_mode('none')
        rec.fit_model()
        assert rec.has_fit
        errors = rec.get_fitted_intensity_standard_errors()
        assert any(np.isfinite(v) for v in errors.values()), errors
        rec.model['Si_Ka'].A.free = True
        rec.model['Si_Ka'].A.std = .123456789
        fixed = rec.model['S_Ka'].A
        fixed.value = 0
        fixed.free = False
        fixed.std = 999  # Fixed parameters must not expose a stale uncertainty.
        fixed.assign_current_value_to_all()
        rec.fitted_intensities = rec.model.get_lines_intensity()
        session = EDSSession()
        session.records[rec.name] = rec
        before = {row['line']: row for row in session.get_intensity_table(fitted=True)}
        assert before['Si_Ka']['standard_error'] == .123456789
        assert math.isnan(before['S_Ka']['standard_error'])
        rec.export(folder=tmp, formats=['hspy'])
        loaded = EDSSession()
        with patch.object(EDSSpectrumRecord, '_make_model', side_effect=AssertionError('eager model')):
            loaded.load([str(work / f'{rec.name}.hspy')])
            deferred = next(iter(loaded.records.values()))
            assert deferred._model is None
            after = {row['line']: row for row in loaded.get_intensity_table(fitted=True)}
            assert after['Si_Ka']['standard_error'] == before['Si_Ka']['standard_error']
            assert math.isnan(after['S_Ka']['standard_error'])
            loaded.export_intensity_table(tmp, fitted=True)
            exported = pd.read_csv(work / 'fitted_intensities.csv')
            assert math.isclose(exported['Si_Ka_standard_error'][0], before['Si_Ka']['standard_error'])
            assert math.isnan(exported['S_Ka_standard_error'][0])
            assert deferred._model is None
            # Legacy snapshots without std fields must remain readable.
            for comp in deferred._pending_fit_state['components']:
                for parameter in comp['parameters']:
                    parameter.pop('std', None)
            assert all(math.isnan(row['standard_error']) for row in loaded.get_intensity_table(fitted=True))
        assert rec.get_fitted_intensity_standard_errors()['Si_Ka'] == .123456789
        np.testing.assert_array_equal(raw, rec._signal.data)
    print('PASS: fit errors, fixed flags, lazy HSPY reload, legacy missing std and session CSV')


if __name__ == '__main__':
    main()
