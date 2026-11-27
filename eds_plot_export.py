"""Export the displayed Matplotlib artists with an independently sized footer."""

from datetime import datetime
from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.font_manager import FontProperties


def fit_notes(record, normalize_to=None):
    """Use full precision results, never the rounded GUI table."""
    modes = {
        'raw': 'Raw (no background subtraction)',
        'measured_bg_subtracted': 'Measured background subtracted',
        'fitted_reference_bg_subtracted': 'Fitted reference background subtracted',
    }
    notes = [f"Display: {modes[record.display_signal_mode]}"]
    if record.model is None:
        notes.append('Fit: not applied')
        return notes
    notes.append('Fitted sample elements: ' + (', '.join(record.elements) or 'none'))
    values = {
        sig.metadata.get_item('Sample.xray_lines')[0]: float(np.asarray(sig.data).ravel()[0])
        for sig in (record.fitted_intensities or [])
    }
    notes.append('Peak integrals (raw, CPS): ' + (
        ';  '.join(f'{line} = {value:.6g}' for line, value in values.items()) or 'unavailable'))
    if normalize_to:
        denominator = values.get(normalize_to, float('nan'))
        if np.isfinite(denominator) and denominator != 0:
            ratios = ';  '.join(f'{line} = {value / denominator:.6g}' for line, value in values.items())
        else:
            ratios = 'unavailable (reference line missing, zero, or non-finite)'
        notes.append(f'Normalized to {normalize_to} = 1: {ratios}')
    if record.bg_fit_mode == 'bg_elements':
        notes.append('Background fit: elements ' + (', '.join(record.bg_elements) or 'none'))
    elif record.bg_fit_mode == 'bg_spec' and record._background is not None:
        name = record.bg_file or record._background.metadata.get_item('General.original_filename', default='')
        notes.append('Background fit: numerical reference spectrum')
        if name:
            path = Path(name).resolve()
            notes.extend([f'Background file: {path.name}', f'Background path: {path.parent}'])
            # On Windows st_ctime is the file creation time (not acquisition time).
            created = datetime.fromtimestamp(path.stat().st_ctime).isoformat(sep=' ', timespec='seconds') if path.is_file() else 'unavailable (file not found)'
            notes.append(f'Background file creation date: {created}')
        else:
            notes.append('Background file/path/creation date: unavailable (embedded reference)')
    else:
        notes.append('Background fit: no external background')
    notes.append(f'Continuum: polynomial, order {record.background_polynomial_order}')
    return notes


def rescale_y(ax):
    """Scale visible data curves within the displayed energy interval."""
    lo, hi = sorted(ax.get_xlim())
    chunks = []
    for line in ax.lines:
        if not line.get_visible() or line.get_transform() != ax.transData:
            continue
        x, y = np.asarray(line.get_xdata()), np.asarray(line.get_ydata())
        if x.shape == y.shape:
            chunks.append(y[(x >= lo) & (x <= hi) & np.isfinite(y)])
    if not chunks:
        return
    data = np.concatenate(chunks)
    if ax.get_yscale() == 'log':
        data = data[data > 0]
    if not data.size:
        return
    low, high = float(data.min()), float(data.max())
    if ax.get_yscale() == 'log':
        pad = max(np.log10(high) - np.log10(low), 0.2) * 0.05
        ax.set_ylim(10 ** (np.log10(low) - pad), 10 ** (np.log10(high) + pad))
    else:
        pad = max(high - low, abs(high) * 0.1, 1e-9) * 0.05
        ax.set_ylim(min(0, low) - pad, high + pad)


def save_displayed_plot(record, figure, formats=('png', 'svg'), normalize_to=None, folder=None, progress=None):
    """Extend below the canvas without changing any axes' physical dimensions.

    Use an Agg canvas temporarily so Qt window geometry and interactive resize
    callbacks are untouched. All figure state is restored even on save failure.
    """
    if isinstance(formats, str):
        formats = formats.split(',')
    formats = list(dict.fromkeys(fmt.strip().lower().lstrip('.') for fmt in formats if fmt.strip()))
    supported = figure.canvas.get_supported_filetypes()
    if not formats or any(fmt not in supported for fmt in formats):
        raise ValueError('Choose supported image formats: ' + ', '.join(sorted(supported)))
    notes = fit_notes(record, normalize_to)
    destination = Path(folder) if folder is not None else Path(record.path).resolve().parent
    destination.mkdir(parents=True, exist_ok=True)
    canvas = figure.canvas
    size = figure.get_size_inches().copy()
    engine = figure.get_layout_engine()
    axes = [(ax, ax.get_position().frozen(), ax.get_in_layout()) for ax in figure.axes]
    texts = [(artist, artist.get_position()) for artist in figure.texts if artist.get_transform() == figure.transFigure]
    footer = None
    try:
        FigureCanvasAgg(figure)
        figure.set_layout_engine(None)
        with figure.canvas.callbacks.blocked(signal='draw_event'):
            figure.canvas.draw()
        renderer = figure.canvas.get_renderer()
        bounds = figure.get_tightbbox(renderer)
        left = max(0, 0.08 - bounds.x0)
        right = max(0, bounds.x1 + 0.08 - size[0])
        top = max(0, bounds.y1 + 0.08 - size[1])
        bottom = max(0, 0.08 - bounds.y0)
        width = size[0] + left + right
        font = FontProperties(family='DejaVu Sans', size=9)
        max_width = (width - 0.6) * figure.dpi
        # Pixel-measured wrapping also handles long paths without spaces.
        lines = []
        for note in notes:
            line = ''
            for word in note.split(' '):
                candidate = (line + ' ' + word).strip()
                if renderer.get_text_width_height_descent(candidate, font, False)[0] <= max_width:
                    line = candidate
                    continue
                if line:
                    lines.append(line)
                line = ''
                for char in word:
                    if line and renderer.get_text_width_height_descent(line + char, font, False)[0] > max_width:
                        lines.append(line)
                        line = ''
                    line += char
            lines.append(line)
        extra = (len(lines) * 13 + 24) / 72
        height = size[1] + extra + top + bottom
        figure.set_size_inches(width, height, forward=False)
        for ax, pos, _ in axes:
            ax.set_position([(pos.x0 * size[0] + left) / width,
                             (pos.y0 * size[1] + extra + bottom) / height,
                             pos.width * size[0] / width, pos.height * size[1] / height])
        for artist, (x, y) in texts:
            artist.set_position(((x * size[0] + left) / width,
                                 (y * size[1] + extra + bottom) / height))
        footer = figure.text(0.3 / width, (extra - 0.12) / height, '\n'.join(lines),
                             va='top', ha='left', fontproperties=font,
                             linespacing=13 / 9, color='#333333', parse_math=False)
        targets = []
        for index, fmt in enumerate(formats):
            if progress:
                progress(index, len(formats), f'Saving {record.name}: {fmt}')
            target = destination / f'{record.name}.{fmt}'
            # No tight cropping: preserve the exact axes size and plot canvas.
            # HyperSpy's interactive blit callback requires an Agg renderer;
            # vector save backends must not invoke it (or update its cache).
            with figure.canvas.callbacks.blocked(signal='draw_event'):
                figure.savefig(target, format=fmt, dpi=150, bbox_inches=None)
            targets.append(target)
        if progress:
            progress(len(formats), len(formats), 'Saved plot')
        return targets
    finally:
        if footer is not None:
            footer.remove()
        figure.set_size_inches(size, forward=False)
        for ax, pos, in_layout in axes:
            ax.set_position(pos)
            ax.set_in_layout(in_layout)
        for artist, position in texts:
            artist.set_position(position)
        figure.set_layout_engine(engine)
        figure.set_canvas(canvas)
        canvas.draw_idle()


def save_all_displayed_plots(records, active, figure, ax, *, formats, auto_y=False,
                             normalize_to=None, plot_options=None, progress=None):
    """Apply the active view to each record, retaining every record's settings."""
    import matplotlib.pyplot as plt

    limits = ax.get_xlim(), ax.get_ylim()
    autoscale_y = ax.get_autoscaley_on()
    scales = ax.get_xscale(), ax.get_yscale()
    size, position = figure.get_size_inches().copy(), ax.get_position().frozen()
    exported, errors = [], []
    for index, record in enumerate(records):
        if progress:
            progress(index, len(records), f'Saving plot {record.name}')
        other_figure = None
        old_mode, old_unit = record.display_signal_mode, record.signal_unit
        try:
            if record is active:
                current_figure, current_ax = figure, ax
            else:
                record.set_display_signal_mode(active.display_signal_mode)
                record.set_unit('cps' if active.uses_model_plot() else active.signal_unit)
                with plt.ioff():
                    other_figure, current_ax = record.plot(**(plot_options or {}))
                current_figure = other_figure
                current_figure.set_size_inches(size, forward=False)
                current_ax.set_position(position)
                current_ax.set_xscale(scales[0])
                current_ax.set_yscale(scales[1])
                current_ax.set_xlim(limits[0])
                current_ax.set_ylim(limits[1])
            if auto_y:
                rescale_y(current_ax)
            exported.extend(save_displayed_plot(record, current_figure, formats, normalize_to))
        except Exception as exc:
            errors.append(f'{record.name}: {exc}')
        finally:
            if record is active:
                ax.set_ylim(limits[1])
                ax.set_autoscaley_on(autoscale_y)
            else:
                if other_figure is not None:
                    plt.close(other_figure)
                record.set_unit(old_unit)
                record.set_display_signal_mode(old_mode)
    figure.canvas.draw_idle()
    if progress:
        progress(len(records), len(records), 'Saved plots')
    return exported, errors
