"""Offscreen Qt import/resume regression. Optional input must be a copied subset."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import argparse
import shutil
import sys
import tempfile
import time
from unittest.mock import patch

import numpy as np
import matplotlib
matplotlib.use('QtAgg')
from qtpy import QtWidgets, QtCore, QtGui

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eds_session import EDSSession, EDSSpectrumRecord
from eds_tool import NavigatorWidget, collect_preferred_spectrum_paths


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--copied-directory')
    args = parser.parse_args()
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix='hspy_gui_') as tmp:
        work = Path(tmp)
        if args.copied_directory:
            source = Path(args.copied_directory).resolve()
            if not source.is_relative_to(scratch.resolve()):
                raise ValueError('Input must be a subset already copied into repository .tmp')
            paths = collect_preferred_spectrum_paths([str(source)])
            assert 0 < len(paths) <= 5, 'Only small copied subsets are allowed'
        else:
            for name in ('grain1_thin.eds', 'grain1_thick.eds', 'bg_near_grain1_thin.eds'):
                shutil.copy2(ROOT / name, work / name)
            record = EDSSpectrumRecord(str(work / 'grain1_thin.eds'))
            record.set_elements(['C', 'O', 'Cu'])
            bg = EDSSpectrumRecord(str(work / 'bg_near_grain1_thin.eds'))
            record.set_background(bg._signal)
            record.bg_file = str(work / 'bg_near_grain1_thin.eds')
            record.background_polynomial_order = 5
            record.fit_model()
            record.set_peak_sum_signal_mode('measured_bg_subtracted')
            record.export(folder=str(work), formats=['hspy'])
            paths = [str(work / 'grain1_thin.hspy')]

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        font_path = Path(matplotlib.get_data_path()) / 'fonts' / 'ttf' / 'DejaVuSans.ttf'
        QtGui.QFontDatabase.addApplicationFont(str(font_path))
        app.setFont(QtGui.QFont('DejaVu Sans', 9))
        widget = NavigatorWidget(EDSSession())
        widget.show()
        app.processEvents()
        warnings = []
        with patch.object(EDSSpectrumRecord, 'fit_model', side_effect=AssertionError('GUI import refitted a snapshot')), \
             patch.object(QtWidgets.QMessageBox, 'warning', side_effect=lambda *a: warnings.append(a[-1])), \
             patch.object(QtWidgets.QMessageBox, 'information'):
            start = time.perf_counter()
            widget._load_spectrum_paths(paths)
            app.processEvents()
            print(f'GUI import: {len(paths)} copied snapshots in {time.perf_counter() - start:.3f}s')
            records = list(widget.session.records.values())
            assert len(records) == len(paths)
            assert sum(r._model is not None for r in records) == 1
            record = widget.session.active_record
            assert widget.el_edit.text().split(',') == record.elements
            assert widget.poly_order_spin.value() == record.background_polynomial_order == 5
            assert widget.peak_sum_mode_combo.currentData() == record.peak_sum_signal_mode
            assert record.fitted_intensities and record.reduced_chisq is not None
            widget.show_fitted_intensity_table()
            assert widget.table_views['Fitted Line Intensities'].table.rowCount() == len(records)
            assert sum(r._model is not None for r in records) == 1, 'Opening results built unused models'

            # Continue with a different view, then save and reopen it through GUI actions.
            record.set_display_signal_mode('fitted_reference_bg_subtracted')
            for control, value in [(widget.residual_checkbox, False), (widget.background_checkbox, True),
                                    (widget.log_checkbox, True)]:
                with QtCore.QSignalBlocker(control):
                    control.setChecked(value)
            widget.update_plot()
            widget.ax.set_yscale('log')
            widget.ax.set_xlim(0.35, 12)
            widget.ax.set_ylim(0.001, 100)
            dialog = widget.table_views['Fitted Line Intensities']
            norm_line = 'O_Ka'
            dialog._norm_radio_buttons[dialog.line_names.index(norm_line)].setChecked(True)
            record.path = str(work / f'{record.name}.eds')
            widget.format_entry.setText('hspy')
            widget.export_selected_spectrum()
            saved = work / f'{record.name}.hspy'
            assert saved.exists()
            widget.close()

            resumed = NavigatorWidget(EDSSession())
            resumed.show()
            app.processEvents()
            with patch.object(QtWidgets.QFileDialog, 'getOpenFileName', return_value=(str(saved), '')):
                resumed.add_file()
            app.processEvents()
            active = resumed.session.active_record
            assert active.has_fit and active.reduced_chisq == record.reduced_chisq
            assert resumed.el_edit.text().split(',') == record.elements
            assert resumed.poly_order_spin.value() == 5
            assert resumed.display_mode_combo.currentData() == 'fitted_reference_bg_subtracted'
            assert resumed.peak_sum_mode_combo.currentData() == 'measured_bg_subtracted'
            assert not resumed.residual_checkbox.isChecked() and resumed.background_checkbox.isChecked()
            assert resumed.log_checkbox.isChecked()
            np.testing.assert_allclose(resumed.ax.get_xlim(), [0.35, 12])
            np.testing.assert_allclose(resumed.ax.get_ylim(), [0.001, 100])
            resumed.show_fitted_intensity_table()
            assert resumed._plot_normalization_line() == norm_line
            resumed.close()
            app.processEvents()
            assert not warnings, warnings
    print('PASS: Qt import without refit, populated fit controls/results, saved view and normalization restored')


if __name__ == '__main__':
    main()
