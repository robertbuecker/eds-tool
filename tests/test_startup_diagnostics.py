"""Startup imports restore stderr and retain dependency exception details."""
import contextlib
import io
from pathlib import Path
import sys
import tempfile
import subprocess
import os
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eds_startup import report_startup_failure, startup_imports


def main():
    scratch = ROOT / '.tmp'
    scratch.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=scratch) as tmp:
        with patch('eds_startup.tempfile.gettempdir', return_value=tmp):
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                with startup_imports():
                    print('normal library import chatter', file=sys.stderr)
                assert sys.stderr is stderr and stderr.getvalue() == ''
                error = ImportError('example native DLL procedure missing')
                try:
                    with startup_imports():
                        raise error
                except ImportError as actual:
                    assert actual is error
                else:
                    raise AssertionError('Startup failure was swallowed')
                assert sys.stderr is stderr
                log_path = Path(tmp) / 'eds_tool_startup_error.log'
                assert 'ImportError: example native DLL procedure missing' in log_path.read_text()
                report_startup_failure(error)
                assert 'example native DLL procedure missing' in stderr.getvalue()
            with patch('eds_startup.sys.stderr', None):
                report_startup_failure(error)
                with startup_imports():
                    pass
                assert sys.stderr is None
        # Exercise the actual entry module with one deliberately failed import.
        code = '''
import builtins, sys
original_import = builtins.__import__
original_stderr = sys.stderr
def fail_session(name, *args, **kwargs):
    if name == 'eds_session':
        raise ImportError('injected startup dependency failure')
    return original_import(name, *args, **kwargs)
builtins.__import__ = fail_session
try:
    import eds_tool
except ImportError as error:
    assert str(error) == 'injected startup dependency failure'
else:
    raise AssertionError('Dependency import did not fail')
assert sys.stderr is original_stderr
'''
        env = dict(os.environ, TEMP=tmp, TMP=tmp)
        subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                       check=True, capture_output=True, text=True, timeout=30)
        assert 'injected startup dependency failure' in (Path(tmp) / 'eds_tool_startup_error.log').read_text()
    print('PASS: stderr restoration, original exception, startup log and missing console')


if __name__ == '__main__':
    main()
