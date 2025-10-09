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
extra_datas  = collect_data_files('exspy') + collect_data_files('hyperspy')
extra_datas += copy_metadata('exspy') + copy_metadata('hyperspy')
extra_datas += collect_data_files('rsciio')

# Handle lazy/dynamic imports used inside these libs
extra_hiddenimports  = collect_submodules('exspy') + collect_submodules('hyperspy')
extra_hiddenimports += collect_submodules('rsciio')
# extra_hiddenimports += ['rsciio.jeol']

# Common compiled libs used by scientific stack
extra_binaries = []
for _pkg in ['numpy', 'scipy', 'numba', 'skimage']:
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
    excludes=[],
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