"""Real HyperSpy plot exports plus layout and state-restoration checks."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from eds_session import EDSSpectrumRecord
from eds_plot_export import fit_notes, rescale_y, save_displayed_plot, save_all_displayed_plots


def main():
    root = Path(__file__).resolve().parents[1]
    output = root / '.tmp' / 'plot_export_qa'
    output.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots()
    ax.plot([0, 1, 2, 3], [-2, 4, 8, 10000])
    ax.set_xlim(0, 2)
    rescale_y(ax)
    assert ax.get_ylim()[0] < -2 and 8 < ax.get_ylim()[1] < 10
    ax.set_yscale('log')
    rescale_y(ax)
    assert 0 < ax.get_ylim()[0] < 4 and 8 < ax.get_ylim()[1] < 10
    plt.close(fig)
    record = EDSSpectrumRecord(str(root / 'grain1_thin.eds'))
    record.set_elements(['C', 'O', 'Cu'])
    record.bg_fit_mode = 'bg_elements'
    record.bg_elements = ['Si']
    record.fit_model()
    raw = record._signal.data.copy()
    fit = record._fit_signal.data.copy()
    reference = record.fitted_intensities[0].metadata.get_item('Sample.xray_lines')[0]
    assert any('Normalized to ' + reference in n for n in fit_notes(record, reference))
    assert any('elements Si' in n for n in fit_notes(record))

    for mode in ['raw', 'fitted_reference_bg_subtracted', 'measured_bg_subtracted']:
        if mode == 'measured_bg_subtracted':
            background = EDSSpectrumRecord(str(root / 'bg_near_grain1_thin.eds'))
            record.set_background(background._signal)
        record.set_display_signal_mode(mode)
        for scale in ['linear', 'log']:
            fig, ax = record.plot(show_residual=True, show_background=True, show_bg_elements=True)
            fig.set_size_inches(8, 4.5)
            ax.set_xlim(0.2, 9)
            ax.set_yscale(scale)
            ax.set_ylim((0.01, 100) if scale == 'log' else (-2, 100))
            fig.canvas.draw()
            before = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted()).bounds
            size, pos = fig.get_size_inches().copy(), ax.get_position().bounds
            canvas = fig.canvas
            limits = ax.get_xlim(), ax.get_ylim()
            original_save = fig.savefig

            def checked_save(*args, **kwargs):
                now = ax.get_window_extent().transformed(fig.dpi_scale_trans.inverted()).bounds
                np.testing.assert_allclose(now[2:], before[2:])
                fig.canvas.draw()
                footer = fig.texts[-1].get_window_extent(fig.canvas.get_renderer())
                assert footer.x0 >= 0 and footer.y0 >= 0
                assert footer.x1 <= fig.bbox.width and footer.y1 < ax.bbox.y0
                return original_save(*args, **kwargs)

            with patch.object(fig, 'savefig', side_effect=checked_save):
                paths = save_displayed_plot(record, fig, normalize_to=reference,
                                            folder=output / f'{mode}_{scale}')
            assert all(path.stat().st_size > 1000 for path in paths)
            np.testing.assert_allclose(fig.get_size_inches(), size)
            np.testing.assert_allclose(ax.get_position().bounds, pos)
            assert canvas is fig.canvas and limits == (ax.get_xlim(), ax.get_ylim())
            with patch.object(fig, 'savefig', side_effect=OSError('test save failure')):
                try:
                    save_displayed_plot(record, fig, folder=output)
                    raise AssertionError('save failure was swallowed')
                except OSError:
                    pass
            np.testing.assert_allclose(fig.get_size_inches(), size)
            assert len(fig.texts) == 0 and canvas is fig.canvas
            plt.close(fig)

    record.bg_fit_mode = 'bg_spec'
    record.bg_file = str(root / 'bg_near_grain1_thin.eds')
    notes = '\n'.join(fit_notes(record, 'missing'))
    assert 'creation date:' in notes and 'Background path:' in notes
    assert 'unavailable (reference line' in notes
    record.bg_file = str(output / ('very_long_directory_' * 15) / 'missing.eds')
    fig, ax = record.plot()
    fig.set_size_inches(5, 4)
    save_displayed_plot(record, fig, folder=output / 'long_path')
    plt.close(fig)
    record.set_display_signal_mode('raw')
    fig, ax = record.plot()
    other = EDSSpectrumRecord(str(root / 'grain1_thick.eds'))
    # Redirect destinations so tests never write beside raw inputs.
    record.path = str(output / 'batch' / 'one.eds')
    other.path = str(output / 'batch' / 'two.eds')
    ylim = ax.get_ylim()
    for auto in [False, True]:
        with patch.object(record, 'plot', side_effect=AssertionError('active plot rebuilt')):
            paths, errors = save_all_displayed_plots([record, other], record, fig, ax,
                formats=['png', 'svg'], auto_y=auto, plot_options={'show_residual': False})
        assert not errors, errors
        assert len(paths) == 4 and ax.get_ylim() == ylim
        assert other.display_signal_mode == 'raw' and other.signal_unit == 'counts'
    # An incompatible batch view must be reported, not silently exported raw.
    plt.close(fig)
    record.set_display_signal_mode('fitted_reference_bg_subtracted')
    fig, ax = record.plot()
    paths, errors = save_all_displayed_plots([other], record, fig, ax, formats=['png'])
    assert not paths and len(errors) == 1
    assert other.display_signal_mode == 'raw' and other.signal_unit == 'counts'
    np.testing.assert_array_equal(record._signal.data, raw)
    np.testing.assert_array_equal(record._fit_signal.data, fit)
    numerical = EDSSpectrumRecord(str(root / 'grain1_thin.eds'))
    numerical.set_elements(['C', 'O', 'Cu'])
    numerical.set_background(background._signal)
    numerical.bg_file = str(root / 'bg_near_grain1_thin.eds')
    numerical.fit_model()
    for mode in ['raw', 'fitted_reference_bg_subtracted']:
        numerical.set_display_signal_mode(mode)
        fig, ax = numerical.plot(show_background=True, show_residual=True)
        ax.set_xlim(0.1, 12)
        save_displayed_plot(numerical, fig, folder=output / f'numerical_{mode}')
        plt.close(fig)
    plt.close('all')
    print('PASS: plot export layout, real model views, formats, batch, and failure restoration')
    print(f'Visual QA images: {output}')


if __name__ == '__main__':
    main()
