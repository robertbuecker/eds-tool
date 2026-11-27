r"""Build configuration for cx_Freeze.

Run from the eds-mini environment:

    powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python setup_cx.py build_exe
"""

from __future__ import annotations

import importlib.metadata as metadata
import importlib.util
import shutil
import sys
import zipfile
import os
from eds_version import __version__, VERSION_TAG
from pathlib import Path

from cx_Freeze import Executable, setup
from cx_Freeze.command.build_exe import build_exe as cx_build_exe


sys.setrecursionlimit(10000)

ROOT = Path(__file__).resolve().parent
ENV_PREFIX = Path(sys.prefix).resolve()
BUILD_DIR = ROOT / "dist-cx" / f"eds-tool-{__version__}"
if '--print-version-tag' in sys.argv:
    print(VERSION_TAG)
    raise SystemExit
if Path(sys.prefix).name.lower() != 'eds-mini':
    raise SystemExit('Build using scripts/with-eds-mini.ps1 in eds-mini')

DATA_SUFFIXES = {
    ".cfg",
    ".csv",
    ".ini",
    ".json",
    ".mplstyle",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_DATA_PARTS = {
    "__pycache__",
    "benchmarks",
    "doc",
    "docs",
    "example",
    "examples",
    "test",
    "testing",
    "tests",
}

PRUNE_DIR_NAMES = {
    "__pycache__",
    "benchmarks",
    "doc",
    "docs",
    "example",
    "examples",
    "test",
    "tests",
    "testsuite",
}

PRUNE_PATHS = [
    Path("lib") / "PIL" / "_imagingtk.cp312-win_amd64.pyd",
    Path("lib") / "PIL" / "_imagingtk.cp312-win_amd64.lib",
    Path("lib") / "PIL" / "ImageTk.pyc",
    Path("lib") / "PIL" / "_tkinter_finder.pyc",
    Path("lib") / "skimage" / "data",
]


def _package_dir(package: str) -> Path:
    spec = importlib.util.find_spec(package)
    if spec is None or spec.origin is None:
        raise RuntimeError(f"Cannot locate package {package!r}")
    if spec.submodule_search_locations:
        return Path(next(iter(spec.submodule_search_locations))).resolve()
    return Path(spec.origin).resolve().parent


def _package_data(package: str) -> list[tuple[str, str]]:
    source_root = _package_dir(package)
    target_root = Path("lib", *package.split("."))
    files: list[tuple[str, str]] = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DATA_PARTS for part in path.parts):
            continue
        if path.suffix.lower() not in DATA_SUFFIXES:
            continue
        files.append((str(path), str(target_root / path.relative_to(source_root))))
    return files


def _dist_info(distribution: str) -> list[tuple[str, str]]:
    try:
        dist = metadata.distribution(distribution)
    except metadata.PackageNotFoundError:
        return []

    files: list[tuple[str, str]] = []
    for package_path in dist.files or []:
        parts = package_path.parts
        if not parts:
            continue
        if not parts[0].endswith((".dist-info", ".egg-info")):
            continue
        source = Path(dist.locate_file(package_path)).resolve()
        if source.is_file():
            files.append((str(source), str(Path("lib") / package_path)))
    return files


def _include_files() -> list[tuple[str, str]]:
    include_files: list[tuple[str, str]] = [
        (str(ROOT / "eds_icon.ico"), "eds_icon.ico"),
        (str(ROOT / "eds_icon.png"), "eds_icon.png"),
        # eds_tool.py resolves the PNG relative to its module path in frozen
        # builds, so keep a second copy beside the frozen module files.
        (str(ROOT / "eds_icon.png"), str(Path("lib") / "eds_icon.png")),
    ]

    for package in ("hyperspy", "exspy", "rsciio"):
        include_files.extend(_package_data(package))

    for distribution in (
        "hyperspy",
        "exspy",
        "rosettasciio",
        "qtpy",
        "matplotlib",
        "PyQt6",
        "PyQt6-Qt6",
        "PyQt6_sip",
    ):
        include_files.extend(_dist_info(distribution))

    return include_files


def _remove_zip_dist_info(zip_path: Path, distribution: str) -> None:
    if not zip_path.exists():
        return

    version = metadata.version(distribution)
    dist_info_name = distribution.replace("-", "_").lower()
    dist_info_prefix = f"{dist_info_name}-{version}.dist-info/"
    temp_path = zip_path.with_suffix(".tmp")

    with zipfile.ZipFile(zip_path, "r") as zin:
        entries = {
            info.filename: zin.read(info.filename)
            for info in zin.infolist()
            if not info.filename.startswith(dist_info_prefix)
        }

    with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name, data in entries.items():
            zout.writestr(name, data)

    shutil.move(str(temp_path), str(zip_path))


def _prune_build_tree(build_dir: Path) -> None:
    lib_dir = build_dir / "lib"
    if not lib_dir.exists():
        return

    for directory, names, _files in os.walk(lib_dir):
        for name in list(names):
            if name in PRUNE_DIR_NAMES:
                shutil.rmtree(Path(directory) / name, ignore_errors=True)
                names.remove(name)

    for relative_path in PRUNE_PATHS:
        path = build_dir / relative_path
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        else:
            path.unlink()
    # scikit-learn imports this vendored runtime package during normal startup.
    source = _package_dir('sklearn') / 'externals' / 'array_api_extra' / 'testing'
    if source.is_dir():
        shutil.copytree(source, lib_dir / 'sklearn' / 'externals' / 'array_api_extra' / 'testing',
                        dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))


class build_exe(cx_build_exe):
    def run(self) -> None:
        build_dir = Path(self.build_exe)
        if build_dir.exists():
            shutil.rmtree(build_dir)
        super().run()
        _prune_build_tree(build_dir)
        _remove_zip_dist_info(build_dir / "lib" / "library.zip", "exspy")
        shutil.copy2(ROOT / 'CHANGELOG.md', build_dir / 'CHANGELOG.md')
        archive = shutil.make_archive(str(build_dir), 'zip', root_dir=build_dir.parent, base_dir=build_dir.name)
        print(f'Distribution ZIP: {archive}')


build_exe_options = {
    "build_exe": str(BUILD_DIR),
    "include_msvcr": True,
    "bin_path_includes": [
        str(ENV_PREFIX / "Library" / "bin"),
        str(ENV_PREFIX / "DLLs"),
    ],
    "includes": [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtNetwork",
        "PyQt6.QtOpenGL",
        "PyQt6.QtOpenGLWidgets",
        "PyQt6.QtSvg",
        "PyQt6.QtWidgets",
        "matplotlib.backends.backend_agg",
        "matplotlib.backends.backend_pdf",
        "matplotlib.backends.backend_qtagg",
        "matplotlib.backends.backend_svg",
        "rsciio.hspy",
        "rsciio.jeol",
        "rsciio.jeol._api",
        "rsciio.msa",
    ],
    "packages": [
        "dask",
        "exspy",
        "hyperspy",
        "matplotlib",
        "numexpr",
        "qtpy",
        "rsciio",
    ],
    "excludes": [
        "PIL.ImageTk",
        "PIL._imagingtk",
        "PIL._tkinter_finder",
        "bokeh",
        "exspy.tests",
        "hyperspy.tests",
        "llvmlite",
        "matplotlib.backends._backend_tk",
        "matplotlib.backends.backend_tkagg",
        "matplotlib.backends.backend_tkcairo",
        "matplotlib.tests",
        "numba",
        "pyarrow",
        "PyQt6.QAxContainer",
        "PyQt6.QtBluetooth",
        "PyQt6.QtDBus",
        "PyQt6.QtDesigner",
        "PyQt6.QtHelp",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtNfc",
        "PyQt6.QtPdf",
        "PyQt6.QtPdfWidgets",
        "PyQt6.QtPositioning",
        "PyQt6.QtPrintSupport",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuick3D",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtRemoteObjects",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSpatialAudio",
        "PyQt6.QtSql",
        "PyQt6.QtStateMachine",
        "PyQt6.QtSvgWidgets",
        "PyQt6.QtTest",
        "PyQt6.QtTextToSpeech",
        "PyQt6.QtWebChannel",
        "PyQt6.QtWebSockets",
        "PyQt6.QtXml",
        "rsciio.tests",
        "scipy.cluster",
        "scipy.conftest",
        "scipy.datasets",
        "scipy.differentiate",
        "scipy.tests",
        "skimage.data",
        "skimage.future",
        "skimage.graph",
        "skimage.segmentation",
        "skimage.tests",
        "pytest",
        "tk",
        "tcl",
        "tkinter",
        "_tkinter",
    ],
    "include_files": _include_files(),
    "zip_exclude_packages": ["*"],
    "optimize": 0,
}


if '--package-existing' in sys.argv:
    if not (BUILD_DIR / 'eds_tool.exe').is_file():
        raise SystemExit('No existing distribution to package')
    print('Pruning existing distribution...', flush=True)
    _prune_build_tree(BUILD_DIR)
    _remove_zip_dist_info(BUILD_DIR / 'lib' / 'library.zip', 'exspy')
    shutil.copy2(ROOT / 'CHANGELOG.md', BUILD_DIR / 'CHANGELOG.md')
    print('Creating ZIP...', flush=True)
    print(shutil.make_archive(str(BUILD_DIR), 'zip', root_dir=BUILD_DIR.parent, base_dir=BUILD_DIR.name), flush=True)
    raise SystemExit

setup(
    name="EDS Tool",
    version=__version__,
    description="EDS spectrum analysis tool",
    cmdclass={"build_exe": build_exe},
    options={"build_exe": build_exe_options},
    executables=[
        Executable(
            "eds_tool_cx_entry.py",
            target_name="eds_tool.exe",
            icon=str(ROOT / "eds_icon.ico"),
            base="console",
        )
    ],
)
