"""CAP preamble/path resolution, literal row metadata and snapshot persistence."""
import csv
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eds_cap_import import CAP_METADATA_KEY, read_cap_export
from eds_session import EDSSession, EDSSpectrumRecord


def main():
    root = Path(__file__).resolve().parents[1]
    scratch = root / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch, prefix='cap_import_') as tmp:
        work = Path(tmp)
        for name, filename in [('exp_a', 'grain1_thin.eds'), ('exp_b', 'grain1_thick.eds')]:
            folder = work / name / 'EDS'
            folder.mkdir(parents=True)
            shutil.copy2(root / filename, folder / f'{name}_edsauto.eds')
        alpha = EDSSpectrumRecord(str(work / 'exp_a' / 'EDS' / 'exp_a_edsauto.eds'))
        alpha.export(formats=['hspy'])
        headers = ['Experiment_name', 'Experiment_path', 'Cluster', 'Current_unit_cell', 'Comment', 'Absent']
        rows = [['exp_b', 'not_here', '001', '  4.96  5.70', 'note, with "quotes"'],
                ['exp_a', 'not_here', 'C9-2exp', '---', ''], ['missing', '', '', '', '']]
        source = work / 'clustered_exps.csv'
        with source.open('w', encoding='utf-8-sig', newline='') as stream:
            stream.write('VERSION 1\nHEADER INFO:\nNumber of experiments: 3\n\n\n')
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)
        paths, metadata, missing = read_cap_export(source)
        assert [Path(path).stem for path in paths] == ['exp_b_edsauto', 'exp_a_edsauto']
        assert paths[1].endswith('.hspy') and len(missing) == 1
        columns = metadata[paths[0]]['columns']
        assert columns['Cluster'] == '001' and columns['Absent'] == ''
        assert columns['Current_unit_cell'] == '  4.96  5.70'
        assert columns['Comment'] == 'note, with "quotes"'
        session = EDSSession([str(source)])
        assert len(session.records) == 2 and session.load_warnings == missing
        for record in session.records.values():
            for signal in (record._signal, record._fit_signal, record.signal):
                saved = signal.metadata.get_item(CAP_METADATA_KEY).as_dictionary()
                assert saved == metadata[str(Path(record.path).resolve())]
            record.export(folder=str(work / 'saved'), formats=['hspy'])
            restored = EDSSpectrumRecord(str(work / 'saved' / f'{record.name}.hspy'))
            assert restored.get_metadata()[CAP_METADATA_KEY] == record.get_metadata()[CAP_METADATA_KEY]
        # CSV import can enrich an already-open spectrum without duplicating it.
        existing = EDSSession([paths[0]])
        existing.load([str(source)])
        assert len(existing.records) == 2
        assert existing.records['exp_b_edsauto'].get_metadata()[CAP_METADATA_KEY]['columns'] == columns
        # Absolute exported paths work when the experiment is elsewhere.
        remote = work / 'elsewhere'
        remote.mkdir()
        moved = remote / 'export.csv'
        with moved.open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerow(['exp_a', str(work / 'exp_a'), '', '', ''])
        assert read_cap_export(moved)[0] == [paths[1]]
        source.write_text('Energy,Counts\n1,2\n', encoding='utf-8')
        try:
            read_cap_export(source)
            raise AssertionError('A spectrum CSV was mistaken for CAP input')
        except ValueError as exc:
            assert 'Experiment_name' in str(exc)
    print('PASS: CAP preamble, quoted/short rows, literal columns, paths, missing spectra and HSPY metadata')


if __name__ == '__main__':
    main()
