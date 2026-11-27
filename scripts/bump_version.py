"""Explicit release version increment; builds consume this same source."""
import argparse
from pathlib import Path
import runpy

parser = argparse.ArgumentParser()
parser.add_argument('part', choices=['major', 'minor', 'patch'])
args = parser.parse_args()
path = Path(__file__).resolve().parents[1] / 'eds_version.py'
parts = list(map(int, runpy.run_path(str(path))['__version__'].split('.')))
parts += [0] * (3 - len(parts))
index = ['major', 'minor', 'patch'].index(args.part)
parts[index] += 1
parts[index + 1:] = [0] * (2 - index)
version = '.'.join(map(str, parts))
path.write_text(f'"""Authoritative application and distribution version."""\n__version__ = "{version}"\nVERSION_TAG = f"v{{__version__}}"\n', encoding='utf-8')
print(version)
