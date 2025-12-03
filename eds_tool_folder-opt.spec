# --- BEGIN: auto-added for eXSpy/HyperSpy packaging ---
try:
    from PyInstaller.utils.hooks import (
        collect_data_files, collect_submodules, collect_dynamic_libs, copy_metadata
    )
except Exception as _e:
    # Fallback if running plain Python on this file for inspection
    def collect_data_files(*a, **k): return []
    def collect_submodules(*a, **k): return []
    def collect_dynamic_libs(*a, **k): return []
    def copy_metadata(*a, **k): return []

# Package data and metadata (tables, resources, entry-points lookups)
# Keep all data files - these are relatively small and contain element databases, etc.
extra_datas  = collect_data_files('exspy') + collect_data_files('hyperspy')
extra_datas += copy_metadata('exspy') + copy_metadata('hyperspy')
# Only collect JEOL reader data, exclude other formats
try:
    extra_datas += collect_data_files('rsciio.jeol')
except Exception:
    # If rsciio.jeol isn't found, try collecting from rsciio package
    pass
# Try to copy rsciio metadata if available
try:
    extra_datas += copy_metadata('rsciio')
except Exception:
    # rsciio metadata may not be available, skip it
    pass

# Handle lazy/dynamic imports used inside these libs
# Keep collect_submodules to avoid missing private modules
extra_hiddenimports  = collect_submodules('exspy') + collect_submodules('hyperspy')
# Only include JEOL reader, not all rsciio formats
extra_hiddenimports += ['rsciio.jeol', 'rsciio.jeol._api', 'rsciio.utils', 'rsciio._hierarchical']

# Common compiled libs used by scientific stack
extra_binaries = []
for _pkg in ['numpy', 'scipy']:
    try:
        extra_binaries += collect_dynamic_libs(_pkg)
    except Exception:
        pass
# --- END: auto-added for eXSpy/HyperSpy packaging ---

# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['eds_tool.py'],
    pathex=[],
    binaries=[('eds_icon.png','.')] + extra_binaries,
    datas=[
        ('C:\\Users\\robert.buecker\\.conda\\envs\\eds-tools\\Lib\\site-packages\\hyperspy\\hyperspy_extension.yaml', 'hyperspy'),
    ]  + extra_datas ,
    hiddenimports=[] + extra_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude unused matplotlib backends (we only use QtAgg)
        'matplotlib.backends.backend_gtk3',
        'matplotlib.backends.backend_gtk3agg',
        'matplotlib.backends.backend_gtk3cairo',
        'matplotlib.backends.backend_gtk4',
        'matplotlib.backends.backend_gtk4agg',
        'matplotlib.backends.backend_gtk4cairo',
        'matplotlib.backends.backend_wx',
        'matplotlib.backends.backend_wxagg',
        'matplotlib.backends.backend_wxcairo',
        'matplotlib.backends.backend_tkagg',
        'matplotlib.backends.backend_tkcairo',
        'matplotlib.backends.backend_webagg',
        'matplotlib.backends.backend_webagg_core',
        'matplotlib.backends.backend_nbagg',
        'matplotlib.backends.backend_macosx',
        # Exclude unused rsciio readers (we only use JEOL .eds)
        'rsciio.bruker',
        'rsciio.dens',
        'rsciio.edax',
        'rsciio.emd',
        'rsciio.empad',
        'rsciio.fei',
        'rsciio.hspy',
        'rsciio.image',
        'rsciio.impulse',
        'rsciio.mrc',
        'rsciio.mrcz',
        'rsciio.netcdf',
        'rsciio.nexus',
        'rsciio.pantarhei',
        'rsciio.phenom',
        'rsciio.protochips',
        'rsciio.ripple',
        'rsciio.semper',
        'rsciio.sur',
        'rsciio.tiff',
        'rsciio.tvips',
        'rsciio.usid',
        'rsciio.zspy',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    name='eds_tool',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['eds_icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='eds_tool'
)