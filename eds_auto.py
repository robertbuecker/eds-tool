"""Guarded automatic fitting on CPS data; never silently mask unknown peaks."""
import json
from pathlib import Path
from time import perf_counter
from dataclasses import replace

import numpy as np
from eds_fit_protocol import fit_spectrum, refine_fit
from eds_plot_export import save_displayed_plot, rescale_y


def assess_fit(record, *, max_chi2r=10.0):
    signal = record.get_signal_for_fit()
    x = signal.axes_manager.signal_axes[0].axis
    use = (x >= record.fit_energy_min_keV) & (x <= record.fit_energy_max_keV)
    y = np.asarray(signal.data, dtype=float)[use]
    prediction = np.asarray(record.model.as_signal(out_of_range_to_nan=False).data)[use]
    total = max(float(np.maximum(y, 0).sum()), 1e-12)
    residual = y - prediction
    between = x[use] <= 4
    for component in record.model:
        if hasattr(component, 'centre') and hasattr(component, 'sigma'):
            between &= np.abs(x[use] - component.centre.value) > max(3 * component.sigma.value, 0.08)
    noise = np.sqrt(np.maximum(y * record.get_live_time(), 1)) / record.get_live_time()
    significant = residual > np.maximum(8 * noise, 0.03 * max(float(y.max()), 1e-12))
    # Isolated noisy channels should not be confused with a missing peak family.
    significant &= np.convolve(significant.astype(int), np.ones(3, dtype=int), mode='same') >= 3
    metrics = dict(chi2r=float(record.reduced_chisq),
                   unexplained_peak_fraction=float(np.maximum(residual[significant], 0).sum() / total),
                   negative_model_fraction=float(np.maximum(-prediction, 0).sum() / total),
                   residual_fraction=float(np.abs(residual).sum() / total),
                   low_energy_between_peaks_mean=float(np.mean(residual[between])) if between.any() else None,
                   low_energy_between_peaks_mean_abs=float(np.mean(np.abs(residual[between]))) if between.any() else None)
    bg = record.fitted_reference_bg_signal
    metrics['background_excess_fraction'] = (float(np.maximum(np.asarray(bg.data)[use] - np.maximum(y, 0), 0).sum() / total)
                                               if bg is not None else 0.0)
    reasons = []
    if total * record.get_live_time() < 100:
        reasons.append('fewer than 100 counts in the fit range; calibration is unsupported')
    if not np.all(np.isfinite(prediction)) or not np.isfinite(metrics['chi2r']):
        reasons.append('non-finite model or fit statistic')
    for key, limit in [('chi2r', max_chi2r), ('unexplained_peak_fraction', 0.03),
                       ('negative_model_fraction', 0.05), ('background_excess_fraction', 0.30)]:
        if metrics[key] > limit:
            reasons.append(f'{key}={metrics[key]:.4g} exceeds {limit:g}')
    return dict(accepted=not reasons, reasons=reasons, metrics=metrics)


def fit_automatically(session, logger=print):
    """Refine the first record, transfer calibration, then fit remaining records.

    Reject a poor first calibration before touching subsequent fits. Rejected
    fits are cleared; raw data and a JSON diagnostic remain available.
    """
    records = list(session.records.values())
    reports = []
    calibration = None
    for index, record in enumerate(records):
        started = perf_counter()
        report = dict(spectrum=record.name, steps=[])
        try:
            if not record.elements:
                raise ValueError('No sample elements defined')
            record.clear_fit(reset_calibration=False)
            record.bg_fit_mode = 'bg_spec' if record._background is not None else 'none'
            if calibration:
                record.apply_calibration(**calibration)
            options = dict(config=replace(record._protocol_config(), max_nfev=200), background_signal=record._background_fit_signal,
                           bg_fit_mode=record.bg_fit_mode, bg_elements=record.bg_elements,
                           reference_bg_shift_keV=record.reference_bg_shift, logger=logger)
            result = fit_spectrum(record.get_signal_for_fit(), **options)
            record._apply_protocol_fit_result(result)
            report['steps'].append(dict(stage='fit', nfev=result.nfev_by_step, seconds=perf_counter() - started))
            if index == 0:
                # A high chi2r can be corrected by offset/resolution refinement;
                # numerical divergence or an exploding background cannot.
                preliminary = assess_fit(record, max_chi2r=float('inf'))
                report['preliminary'] = preliminary
                fatal = [reason for reason in preliminary['reasons'] if not reason.startswith('unexplained_peak_fraction')]
                if fatal:
                    raise ValueError('; '.join(fatal))
                options['config'] = replace(record._protocol_config(), max_nfev=200)
                refine_start = perf_counter()
                result = refine_fit(record.get_signal_for_fit(), record.model, **options)
                record._apply_protocol_fit_result(result)
                report['steps'].append(dict(stage='refine', nfev=result.nfev_by_step, seconds=perf_counter() - refine_start))
            report.update(assess_fit(record))
            if not report['accepted']:
                raise ValueError('; '.join(report['reasons']))
            if index == 0:
                calibration = dict(offset=record.get_signal_for_fit().axes_manager.signal_axes[0].offset,
                                   resolution=record.get_energy_resolution(), reference_bg_shift=record.reference_bg_shift)
            record.set_display_signal_mode('fitted_reference_bg_subtracted' if record._background is not None else 'raw')
        except Exception as exc:
            report.update(accepted=False, error=str(exc))
            logger(f'WARNING: fit rejected for {record.name}: {exc}')
            record.clear_fit(reset_calibration=False)
        report['seconds'] = perf_counter() - started
        reports.append(report)
        Path(record.path).with_suffix('.fit_quality.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        if index == 0 and not report['accepted']:
            logger('WARNING: automatic fitting cancelled: first-spectrum calibration was rejected.')
            return reports
    return reports


def save_fit_plot(record, formats, max_energy=None):
    import matplotlib.pyplot as plt
    with plt.ioff():
        figure, ax = record.plot(show_residual=True, show_background=False)
    try:
        if max_energy is not None:
            ax.set_xlim(left=max(0, ax.get_xlim()[0]), right=max_energy)
        rescale_y(ax)
        return save_displayed_plot(record, figure, formats)
    finally:
        plt.close(figure)
