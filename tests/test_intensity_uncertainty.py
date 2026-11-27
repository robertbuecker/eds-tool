"""Fitted interval formatting, normalized GUI views and numerical CSV exports."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import csv
import math
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eds_intensity_uncertainty import (
    amplitude_standard_error, format_with_uncertainty, normalized_half_width, write_fitted_intensity_csv,
    saved_amplitude_standard_errors,
)


def main():
    for free, std, twin in [(False, 99, None), (True, None, None), (True, float('nan'), None),
                             (True, float('inf'), None), (True, -1, None), (True, 0, None),
                             (True, 1, object())]:
        assert math.isnan(amplitude_standard_error(free=free, std=std, twin=twin))
    assert amplitude_standard_error(free=True, std=.123456) == .123456
    assert math.isnan(amplitude_standard_error(free=True, std=.123456, active=False))
    errors = saved_amplitude_standard_errors([
        {'name': 'Si_Ka', 'parameters': [{'name': 'A', 'free': True, 'std': .123456}]},
        {'name': 'S_Ka', 'parameters': [{'name': 'A', 'free': False, 'std': 999}]},
        {'name': 'O_Ka', 'parameters': [{'name': 'A', 'free': True}]},
        {'name': 'Cu_Ka', 'active': False, 'parameters': [{'name': 'A', 'free': True, 'std': .1}]},
    ])
    assert errors['Si_Ka'] == .123456
    assert math.isnan(errors['S_Ka']) and math.isnan(errors['O_Ka'])
    assert math.isnan(errors['Cu_Ka'])
    for value, interval, expected in [
        (12345.6789, 67.89, '12345(67)'),
        (12.3456, .1234, '12.34(12)'),
        (-12.3456, .1234, '-12.34(12)'),
        (1.2345, .1, '1.23(10)'),
        (1.9999, .09999, '1.999(99)'),
        (12345.678, 678.9, '1.234(67)e+4'),
        (.0000123456, .0000006789, '1.234(67)e-5'),
        (0, .0000006789, '0.0(67)e-7'),
        (0, float('nan'), '0(NaN)'),
        (float('nan'), .1, 'NaN'),
        (1, 0, '1(00)'),
    ]:
        actual = format_with_uncertainty(value, interval)
        assert actual == expected, (value, interval, actual, expected)
    assert math.isclose(normalized_half_width(10, 2, 5, .5), math.hypot(.4, .2))
    assert normalized_half_width(5, .5, 5, .5, same_line=True) == 0
    assert math.isnan(normalized_half_width(1, .1, 0, .1))
    assert math.isnan(normalized_half_width(1, float('nan'), 2, .1))
    assert math.isnan(normalized_half_width(1, .1, 2, float('nan')))
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        path = Path(tmp) / 'errors.csv'
        write_fitted_intensity_csv(path, ['Si_Ka', 'S_Ka', 'O_Ka'],
            {'first': {'Si_Ka': 12345.6789123456, 'S_Ka': 0}},
            {'first': {'Si_Ka': .123456789123456, 'S_Ka': float('nan')}})
        with path.open() as handle:
            rows = list(csv.DictReader(handle))
        assert float(rows[0]['Si_Ka']) == 12345.6789123456
        assert float(rows[0]['Si_Ka_standard_error']) == .123456789123456
        assert rows[0]['S_Ka_standard_error'] == 'NaN'
        assert rows[0]['O_Ka'] == rows[0]['O_Ka_standard_error'] == 'NaN'
        write_fitted_intensity_csv(path, [], {'first': {}}, {})
        with path.open() as handle:
            assert list(csv.reader(handle)) == [['Spectrum'], ['first']]
    print('PASS: standard errors, fixed/missing flags, truncation, ratio propagation and full-precision CSV', flush=True)
    if '--format-only' in sys.argv:
        return

    from qtpy import QtWidgets, QtCore, QtGui
    import matplotlib
    from intensity_table_dialog import IntensityTableDialog
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont(str(Path(matplotlib.get_data_path()) / 'fonts/ttf/DejaVuSans.ttf'))
    app.setFont(QtGui.QFont('DejaVu Sans', 9))
    lines = ['Si_Ka', 'S_Ka', 'O_Ka']
    data = [['first', 12345.6789, 0, 100.123456789], ['second', .123456789, 0, 0]]
    intervals = {'first': {'Si_Ka': 67.89, 'S_Ka': float('nan'), 'O_Ka': 1.23456789},
                 'second': {'Si_Ka': .001234567, 'S_Ka': float('nan'), 'O_Ka': float('nan')}}
    dialog = IntensityTableDialog(None, lines, data, 'Fitted Line Intensities', intervals)
    dialog.resize(1000, 350)
    dialog.show()
    app.processEvents()
    assert dialog.table.item(0, 1).text() == '12345(67)'
    assert dialog.table.item(0, 2).text() == '0(NaN)'
    assert '68%' in dialog.table.item(0, 1).toolTip()
    dialog.select_spectrum('first')
    emitted = []
    dialog.spectrum_selected.connect(emitted.append)
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    dialog.grab().save(str(scratch / 'intensity_uncertainty_table.png'))
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        target = Path(tmp) / 'fitted.csv'
        dialog.save_csv(target)
        with target.open() as handle:
            rows = list(csv.DictReader(handle))
        assert float(rows[0]['Si_Ka']) == data[0][1]
        assert float(rows[0]['Si_Ka_standard_error']) == 67.89
        assert rows[0]['S_Ka_standard_error'] == 'NaN'
        assert float(rows[1]['Si_Ka']) == data[1][1]
        dialog._norm_radio_buttons[2].setChecked(True)
        assert dialog.table.item(0, 3).text() == '1(00)'
        assert dialog.table.item(1, 1).text() == 'NaN'
        dialog.line_list.item(1).setCheckState(QtCore.Qt.Unchecked)
        dialog.save_csv(target)
        with target.open() as handle:
            rows = list(csv.DictReader(handle))
        ratio = data[0][1] / data[0][3]
        expected = normalized_half_width(data[0][1], 67.89, data[0][3], 1.23456789)
        assert float(rows[0]['Si_Ka']) == ratio
        assert float(rows[0]['Si_Ka_standard_error']) == expected
        assert 'S_Ka' not in rows[0]
        assert rows[1]['Si_Ka_standard_error'] == 'NaN'
        assert dialog.table.item(dialog.table.currentRow(), 0).text() == 'first'
        assert not emitted, emitted
        summed = IntensityTableDialog(None, lines, data)
        assert summed.table.item(0, 1).text() == '12345.68'
        summed.save_csv(target)
        with target.open() as handle:
            assert next(csv.reader(handle)) == ['Spectrum'] + lines
        summed.close()
    dialog.close()
    print('PASS: one-SE intervals; fixed/missing errors; truncated notation; ratios; full precision CSV; navigation')


if __name__ == '__main__':
    main()
