"""Keep import chatter quiet while making startup failures diagnosable."""
from contextlib import contextmanager, redirect_stderr
import io
import os
from pathlib import Path
import sys
import tempfile
import traceback


def report_startup_failure(error, *, show_dialog=False, print_traceback=True):
    details = ''.join(traceback.format_exception(type(error), error, error.__traceback__))
    log_path = Path(tempfile.gettempdir()) / 'eds_tool_startup_error.log'
    try:
        log_path.write_text(details, encoding='utf-8')
        location = f'Details saved to:\n{log_path}'
    except OSError:
        location = 'The diagnostic log could not be written.'
    if print_traceback and sys.stderr is not None:
        print(details, file=sys.stderr)
        print(location, file=sys.stderr)
    if show_dialog and os.name == 'nt':
        # Qt may itself be the failing dependency; this must not import it.
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None, f'EDS Tool could not start.\n\n{error}\n\n{location}', 'EDS Tool startup error', 0x10)
    return log_path


@contextmanager
def startup_imports(*, show_dialog=False):
    """Restore stderr even if an import fails, then log and propagate it."""
    try:
        with redirect_stderr(io.StringIO()):
            yield
    except Exception as error:
        report_startup_failure(error, show_dialog=show_dialog, print_traceback=False)
        raise
