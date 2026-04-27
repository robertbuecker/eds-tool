"""cx_Freeze entry point for EDS Tool."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _prepare_frozen_runtime() -> None:
    if not getattr(sys, "frozen", False):
        return

    base_dir = Path(sys.executable).resolve().parent
    numba_cache_dir = base_dir / ".numba_cache"
    mpl_config_dir = base_dir / ".matplotlib"
    numba_cache_dir.mkdir(exist_ok=True)
    mpl_config_dir.mkdir(exist_ok=True)

    os.environ.setdefault("NUMBA_CACHE_DIR", str(numba_cache_dir))
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_config_dir))


_prepare_frozen_runtime()

try:
    from eds_tool import main  # noqa: E402
except Exception:
    import traceback

    sys.stderr = sys.__stderr__
    traceback.print_exc()
    raise


if __name__ == "__main__":
    main()
