"""Real-data quality gates and automatic fit/save integration on copied inputs."""
from pathlib import Path
import sys, shutil, json, time
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import matplotlib
matplotlib.use('Agg')
from eds_session import EDSSession, EDSSpectrumRecord
from eds_auto import fit_automatically, save_fit_plot, assess_fit
import numpy as np
import exspy


def main():
    root = Path(__file__).resolve().parents[1]
    work = root / '.tmp' / 'auto_fit_tests'
    work.mkdir(parents=True, exist_ok=True)
    cases = [
        ('good', 'grain1_thin.eds', 'bg_near_grain1_thin.eds', ['Na','S','K','Si','Cu','C','O','Cl'], True),
        ('missing_cu', 'grain1_thin.eds', 'bg_near_grain1_thin.eds', ['C','O'], False),
        ('grain_no_bg', 'grain1_thin.eds', None, ['Na','S','K','Si','Cu','C','O','Cl'], False),
        ('acac_good', 'acac/exp_7993.EDS', 'acac/near_7994.EDS', ['C','O','Fe','Al','Ga','Ge','N'], True),
        ('acac_missing_fe', 'acac/exp_7993.EDS', 'acac/near_7994.EDS', ['C','O'], False),
        ('acac_no_bg', 'acac/exp_7993.EDS', None, ['C','O','Fe','Al','Ga','Ge','N'], False),
    ]
    summaries = []
    for name, spectrum, background, elements, expected in cases:
        folder = work / name
        folder.mkdir(exist_ok=True)
        destination = folder / Path(spectrum).name
        # Remove the previous derivative snapshot so input preference cannot
        # turn a fresh bad-input case into a resumed good fit.
        destination.with_suffix('.hspy').unlink(missing_ok=True)
        shutil.copy2(root / spectrum, destination)
        session = EDSSession([str(destination)])
        if name == 'good':
            replica = folder / 'replica.eds'
            replica.with_suffix('.hspy').unlink(missing_ok=True)
            shutil.copy2(root / spectrum, replica)
            session.load([str(replica)])
        session.set_elements(elements)
        if background:
            bg_path = folder / Path(background).name
            shutil.copy2(root / background, bg_path)
            session.set_background(str(bg_path))
        reports = fit_automatically(session)
        rec = session.active_record
        if name == 'good':
            assert len(reports) == 2 and reports[1]['accepted'], reports
            assert [step['stage'] for step in reports[1]['steps']] == ['fit']
            assert session.records['replica'].get_energy_resolution() == rec.get_energy_resolution()
        print(name, json.dumps(reports[0]), flush=True)
        if expected is not None:
            assert reports[0]['accepted'] is expected, (name, reports)
        if reports[0]['accepted']:
            save_fit_plot(rec, ['png','svg'], 12)
            rec.export(formats=['hspy'])
            restored = EDSSpectrumRecord(str(destination.with_suffix('.hspy')))
            assert restored.has_fit and restored.display_signal_mode == rec.display_signal_mode
            if background:
                instrument = rec._get_instrument_component()
                scale = instrument.yscale.value
                instrument.yscale.value = 1e5
                instrument.yscale.assign_current_value_to_all()
                assert not assess_fit(rec)['accepted'], 'Exploding background accepted'
                instrument.yscale.value = scale
                instrument.yscale.assign_current_value_to_all()
        else:
            assert not rec.has_fit
        summaries.append(dict(case=name, **reports[0]))
    # A valid raw no-background spectrum must not be rejected merely for
    # lacking a reference. Generate one independent, Poisson-sampled C peak.
    raw = exspy.signals.EDSTEMSpectrum(np.zeros(4096))
    axis = raw.axes_manager.signal_axes[0]
    axis.name, axis.units, axis.scale = 'Energy', 'keV', 0.01
    raw.set_microscope_parameters(beam_energy=200, live_time=100, energy_resolution_MnKa=128)
    energy, fwhm = raw._get_line_energy('C_Ka', FWHM_MnKa='auto')
    cps = 1 + 50 * np.exp(-0.5 * ((axis.axis - energy) / (fwhm / 2.35482)) ** 2)
    raw.data = np.random.default_rng(23).poisson(100 * cps)
    raw_path = work / 'synthetic_raw.hspy'
    raw.save(str(raw_path), overwrite=True)
    session = EDSSession([str(raw_path)])
    session.set_elements(['C'])
    session.set_background_polynomial_order(1)
    report = fit_automatically(session)[0]
    assert report['accepted'], report
    assert session.active_record.display_signal_mode == 'raw'
    save_fit_plot(session.active_record, ['png','svg'], 4)
    summaries.append(dict(case='synthetic_raw', **report))
    (work / 'summary.json').write_text(json.dumps(summaries, indent=2))
    print('PASS: real-data auto fitting and quality diagnostics')


if __name__ == '__main__':
    main()
