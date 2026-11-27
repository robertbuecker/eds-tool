"""Offscreen row navigation and startup geometry for compact Save controls."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

import matplotlib
matplotlib.use('QtAgg')
from qtpy import QtWidgets, QtGui, QtCore

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eds_session import EDSSession, EDSSpectrumRecord
from eds_tool import NavigatorWidget


def selected(dialog):
    item = dialog.table.item(dialog.table.currentRow(), 0)
    return item.data(QtCore.Qt.UserRole) if item is not None else None


def main():
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    QtGui.QFontDatabase.addApplicationFont(str(Path(matplotlib.get_data_path()) / 'fonts/ttf/DejaVuSans.ttf'))
    app.setFont(QtGui.QFont('DejaVu Sans', 9))
    with tempfile.TemporaryDirectory(dir=scratch, prefix='intensity_nav_') as tmp:
        paths = []
        for name in ['grain1_thin.eds', 'grain1_thick.eds']:
            target = Path(tmp) / name
            shutil.copy2(ROOT / name, target)
            paths.append(str(target))
        session = EDSSession(paths)
        session.set_elements(['O', 'Cu'])
        names = list(session.records)
        for index, rec in enumerate(session.records.values()):
            data = [{'line': 'O_Ka', 'value': index + 1.5}, {'line': 'Cu_Ka', 'value': index + 3.2}]
            rec.intensities = EDSSpectrumRecord._intensity_signals(data)
            rec.fitted_intensities = EDSSpectrumRecord._intensity_signals(data)
        nav = NavigatorWidget(session)
        nav.show()
        app.processEvents()
        frame = nav.spectrum_actions_widget
        for control in [nav.add_file_btn, nav.add_dir_btn, nav.remove_spec_btn, nav.remove_all_btn,
                        nav.export_selected_btn, nav.export_all_btn, nav.export_plot_btn, nav.export_plots_btn,
                        nav.format_entry, nav.plot_format_entry, nav.ask_folder_checkbox]:
            corner = control.mapTo(frame, QtCore.QPoint(0, 0))
            rectangle = QtCore.QRect(corner, control.size())
            assert frame.rect().contains(rectangle), (control, rectangle, frame.rect())
            assert nav.rect().contains(QtCore.QRect(control.mapTo(nav, QtCore.QPoint(0, 0)), control.size()))
        assert nav.remove_spec_btn.y() == nav.remove_all_btn.y()
        assert nav.export_selected_btn.y() == nav.export_all_btn.y()
        assert nav.export_plot_btn.y() == nav.export_plots_btn.y()
        assert nav.export_selected_btn.text().startswith('Save')
        nav.grab().save(str(scratch / 'compact_save_controls.png'))
        nav.show_summed_intensity_table()
        nav.show_fitted_intensity_table()
        summed = nav.table_views['Summed Line Intensities']
        fitted = nav.table_views['Fitted Line Intensities']
        assert selected(summed) == selected(fitted) == names[0]
        with patch.object(nav, 'update_plot', wraps=nav.update_plot) as updates:
            summed.table.setCurrentCell(1, 1)
            assert updates.call_count == 1
            assert selected(summed) == selected(fitted) == session.active_name == names[1]
            assert nav.list.currentRow() == 1 and names[1] in nav.ax.get_title()
            fitted.table.setCurrentCell(0, 1)
            assert updates.call_count == 2
            assert selected(summed) == selected(fitted) == session.active_name == names[0]
            fitted._norm_radio_buttons[0].setChecked(True)
            fitted.line_list.item(1).setCheckState(QtCore.Qt.Unchecked)
            assert updates.call_count == 2 and selected(fitted) == names[0]
            nav.list.setCurrentRow(1)
            assert updates.call_count == 3
            assert selected(summed) == selected(fitted) == names[1]
        # If a result is absent, clear that table's selection without navigating.
        session.records[names[1]].fitted_intensities = None
        nav.show_fitted_intensity_table()
        assert selected(nav.table_views['Fitted Line Intensities']) is None
        assert session.active_name == names[1]
        nav.close()
        app.processEvents()
    print('PASS: startup Save geometry; summed/fitted/control/plot selection; normalization and missing rows')


if __name__ == '__main__':
    main()
