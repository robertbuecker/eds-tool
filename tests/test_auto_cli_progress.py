"""Subprocess CLI outputs/exit codes and real Qt progress callback cleanup."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from pathlib import Path
import sys, shutil, subprocess, tempfile
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('QtAgg')
from qtpy import QtWidgets
from eds_session import EDSSession
from eds_tool import NavigatorWidget


def main():
    root = Path(__file__).resolve().parents[1]
    (root / '.tmp').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root / '.tmp', prefix='auto_cli_') as tmp:
        folder = Path(tmp)
        for name in ['grain1_thin.eds', 'bg_near_grain1_thin.eds']:
            shutil.copy2(root / name, folder / name)
        spec = folder / 'grain1_thin.eds'
        bg = folder / 'bg_near_grain1_thin.eds'
        base = [sys.executable, str(root / 'eds_tool.py'), '--auto', str(spec), '--max-energy', '12']
        for fit in [False, True]:
            args = base + ['--elements', 'Na,S,K,Si,Cu,C,O,Cl']
            if fit:
                args += ['--fit', '--bg-spectrum', str(bg)]
            result = subprocess.run(args, capture_output=True, text=True, timeout=180)
            assert result.returncode == 0, result.stdout + result.stderr
            for suffix in ['hspy', 'png', 'svg', 'emsa', 'csv']:
                assert spec.with_suffix('.' + suffix).is_file(), (suffix, result.stdout, result.stderr)
            if fit:
                assert (folder / 'fitted_intensities.csv').is_file()
        bad = subprocess.run(base + ['--fit', '--elements', 'C,O', '--bg-spectrum', str(bg)],
                             capture_output=True, text=True, timeout=180)
        assert bad.returncode == 2 and 'cancelled' in bad.stdout
        session = EDSSession([str(spec)])
        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        nav = NavigatorWidget(session)
        values = []
        original = nav._create_progress_dialog
        def create(title):
            dialog = original(title)
            dialog.findChild(QtWidgets.QProgressBar).valueChanged.connect(values.append)
            return dialog
        with patch.object(nav, '_create_progress_dialog', side_effect=create):
            nav._run_with_progress('Save', lambda: session.export_all(str(folder / 'gui'), ['hspy']))
            assert 1 in values
            assert session.progress_callback is None
            assert all(rec.progress_callback is None for rec in session.records.values())
            with patch.object(session.active_record, 'fit_model', side_effect=lambda: session.active_record._fit_log('Fit stage')):
                nav._run_with_progress('Fit', session.fit_all_models)
            assert session.active_record.progress_callback is None
            try:
                nav._run_with_progress('Failure', lambda: (_ for _ in ()).throw(OSError('test')))
            except OSError:
                pass
            assert session.progress_callback is None and QtWidgets.QApplication.overrideCursor() is None
        nav.close()
        app.processEvents()
    print('PASS: auto/fit CLI files, rejection exit status, Qt progress and cleanup')


if __name__ == '__main__':
    main()
