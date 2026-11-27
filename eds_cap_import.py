"""Read CAP Data Explorer rows without interpreting their scientific values."""
import csv
import io
from pathlib import Path


CAP_METADATA_KEY = 'CAP_Data_Explorer'


def read_cap_export(path):
    """Return (spectrum paths, metadata by path, missing-file messages).

    CAP exports can contain a VERSION/header preamble and short data rows.
    Resolve relocated experiment folders beside the CSV first, then use the
    exported Experiment_path. No recursive search or spectrum loading is done.
    """
    source = Path(path).resolve()
    raw = source.read_bytes()
    try:
        contents = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        contents = raw.decode('cp1252')
    reader = csv.reader(io.StringIO(contents, newline=''))
    for row in reader:
        headers = [value.strip() for value in row]
        if 'Experiment_name' in headers:
            break
    else:
        raise ValueError(f'No CAP Data Explorer Experiment_name header found in {source}')
    if len(set(headers)) != len(headers) or any(not name for name in headers):
        raise ValueError(f'CAP column names must be unique and nonempty: {source}')
    paths, metadata, missing = [], {}, []
    seen = set()
    for row_number, row in enumerate(reader, 1):
        if not row or not any(value.strip() for value in row):
            continue
        if len(row) > len(headers):
            raise ValueError(f'CAP row at line {reader.line_num} has more values than column names')
        values = dict(zip(headers, row + [''] * (len(headers) - len(row))))
        name = values['Experiment_name'].strip()
        if not name or name in ('.', '..') or any(char in name for char in '/\\'):
            raise ValueError(f'Invalid experiment name at line {reader.line_num}: {name!r}')
        if name in seen:
            raise ValueError(f'Duplicate CAP experiment name: {name}')
        seen.add(name)
        directories = [source.parent / name]
        exported_path = values.get('Experiment_path', '').strip()
        if exported_path and exported_path != '---':
            folder = Path(exported_path)
            directories.append(folder if folder.is_absolute() else source.parent / folder)
        selected = None
        for directory in dict.fromkeys(directories):
            eds_dir = directory / 'EDS'
            if not eds_dir.is_dir():
                continue
            files = {file.name.casefold(): file for file in eds_dir.iterdir() if file.is_file()}
            for extension in ('hspy', 'eds'):
                selected = files.get(f'{name}_edsauto.{extension}'.casefold())
                if selected is not None:
                    break
            if selected is not None:
                break
        if selected is None:
            missing.append(f'{name}: no EDS/{name}_edsauto.hspy or .eds found')
            continue
        resolved = str(selected.resolve())
        paths.append(resolved)
        metadata[resolved] = dict(source_file=str(source), row_number=row_number,
                                  columns=values)
    return paths, metadata, missing
