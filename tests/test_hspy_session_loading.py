"""Regression for resumable snapshots, lazy batch import and conflicting defaults."""
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eds_session import EDSSession, EDSSpectrumRecord, EDS_TOOL_STATE_KEY


def main():
    root = Path(__file__).resolve().parents[1]
    scratch = root / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix='hspy_session_') as tmp:
        work = Path(tmp)
        for source, target in [('grain1_thin.eds', 'alpha.eds'),
                               ('grain1_thick.eds', 'beta.eds'),
                               ('bg_near_grain1_thin.eds', 'background.eds')]:
            shutil.copy2(root / source, work / target)
        alpha = EDSSpectrumRecord(str(work / 'alpha.eds'))
        background = EDSSpectrumRecord(str(work / 'background.eds'))
        alpha.set_elements(['C', 'O', 'Cu'])
        alpha.set_background(background._signal)
        alpha.bg_file = str(work / 'background.eds')
        alpha.background_polynomial_order = 5
        alpha.fit_model()
        alpha.set_display_signal_mode('fitted_reference_bg_subtracted')
        alpha.set_peak_sum_signal_mode('measured_bg_subtracted')
        alpha.set_unit('cps')
        alpha.compute_intensities()
        alpha.plot_state = dict(xlim=[0.3, 9], ylim=[0.01, 100], yscale='log',
                                show_residual=False, show_background=True,
                                show_bg_elements=False, normalization_line='O_Ka', x_range=15.0)
        alpha.model['C_Ka'].active = False
        alpha.model['Cu_Ka'].A.std = 0.123
        alpha.model['Cu_La'].sigma.twin_function_expr = 'x * 0.8'
        alpha.model['Cu_La'].sigma.twin = alpha.model['Cu_Ka'].sigma
        alpha.model.set_signal_range(0.3, 9)
        alpha.model._calculate_chisq()
        prediction = alpha.model.as_signal().data.copy()
        state = alpha._serialize_state()
        alpha.export(folder=tmp, formats=['hspy'])

        beta = EDSSpectrumRecord(str(work / 'beta.eds'))
        beta.set_elements(['O', 'Cu'])
        beta.set_bg_fit_mode('none')
        beta.background_polynomial_order = 3
        beta.apply_calibration(resolution=137)
        beta.fit_model()
        beta.export(folder=tmp, formats=['hspy'])
        (work / 'background.eds').unlink()  # restoration must use the embedded reference

        session = EDSSession()
        # Batch import and fitted tables must not create or fit any model.
        with patch.object(EDSSpectrumRecord, '_make_model', side_effect=AssertionError('eager model build')):
            session.load([str(work / 'alpha.eds'), str(work / 'alpha.hspy'), str(work / 'beta.hspy')])
            assert len(session.records) == 2
            a, b = session.records.values()
            assert a.has_fit and b.has_fit and a._model is None and b._model is None
            assert a.elements == alpha.elements and b.elements == beta.elements
            assert (a.background_polynomial_order, b.background_polynomial_order) == (5, 3)
            assert a.display_signal_mode == 'fitted_reference_bg_subtracted'
            assert a.peak_sum_signal_mode == 'measured_bg_subtracted'
            assert b.get_energy_resolution() == 137
            assert a.plot_state == alpha.plot_state
            assert session.get_intensity_table(fitted=True)
            assert a._serialize_intensities(a.intensities) == alpha._serialize_intensities(alpha.intensities)
            deferred_values = a._serialize_intensities(a.fitted_intensities)
            original_values = alpha._serialize_intensities(alpha.fitted_intensities)
            assert [v['line'] for v in deferred_values] == [v['line'] for v in original_values]
            np.testing.assert_allclose([v['value'] for v in deferred_values],
                                       [v['value'] for v in original_values], rtol=1e-12)
            a.export(folder=str(work / 'resaved'), formats=['hspy'])
        with patch('eds_session.hs.load', side_effect=AssertionError('duplicate reopened')):
            session.load([str(work / 'alpha.hspy')])

        assert EDS_TOOL_STATE_KEY not in a._fit_signal.metadata
        np.testing.assert_allclose(a.model.as_signal().data, prediction, rtol=1e-12, atol=1e-12)
        restored = a._serialize_state()
        for after, before in zip(restored['fit_state']['components'], state['fit_state']['components']):
            assert (after['name'], after['active']) == (before['name'], before['active'])
            for actual, expected in zip(after['parameters'], before['parameters']):
                for key in expected:
                    if key in ('value', 'std') and expected[key] is not None:
                        np.testing.assert_allclose(actual[key], expected[key], rtol=1e-12, equal_nan=True)
                    else:
                        assert actual[key] == expected[key], (after['name'], key)
        assert restored['fit_state']['channel_switches'] == state['fit_state']['channel_switches']
        np.testing.assert_allclose(a.model.red_chisq.data, alpha.model.red_chisq.data)
        assert a._background is not None and a.can_use_fitted_reference_bg_subtraction()
        np.testing.assert_array_equal(a._signal.data, alpha._signal.data)
        np.testing.assert_array_equal(a._fit_signal.data, alpha._fit_signal.data)
        # A newly added saved spectrum keeps its own settings in an existing session.
        populated = EDSSession([str(work / 'beta.hspy')])
        populated.load([str(work / 'alpha.hspy')])
        assert populated.records['alpha'].elements == alpha.elements
        assert populated.records['alpha'].background_polynomial_order == 5
        assert populated.records['alpha'].display_signal_mode == alpha.display_signal_mode
        # Applying an unchanged list must not refit or materialize a saved model.
        with patch.object(EDSSpectrumRecord, 'fit_model', side_effect=AssertionError('implicit refit')):
            same = EDSSession([str(work / 'alpha.hspy')])
            same.set_elements(alpha.elements)
            assert same.active_record._model is None
        cancelled = EDSSession()
        cancelled.load([str(work / 'alpha.hspy'), str(work / 'beta.hspy')],
                       progress=lambda done, total, path: done < 1)
        assert len(cancelled.records) == 1
    print('PASS: full model state, embedded background, diagnostics, lazy results, defaults, duplicates, cancellation')


if __name__ == '__main__':
    main()
