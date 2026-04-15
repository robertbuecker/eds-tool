import os
import sys


def _prepend_overlay_site_packages() -> None:
    root = os.path.dirname(os.path.abspath(__file__))
    overlay = os.path.join(root, "runtime", "site-packages")
    if os.path.isdir(overlay) and overlay not in sys.path:
        sys.path.insert(0, overlay)


def main() -> int:
    _prepend_overlay_site_packages()
    from eds_tool import main as app_main

    return int(app_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
