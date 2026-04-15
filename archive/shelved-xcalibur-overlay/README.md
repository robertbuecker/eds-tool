This folder contains a shelved distribution attempt for running the tool from the
fixed `C:\Xcalibur\Python312` interpreter instead of a dedicated Conda environment.

Contents:
- `launch_eds_tool.py`: wrapper that prepended `runtime/site-packages` before launching `eds_tool`.
- `run_eds_tool.bat`: batch entry point for the fixed Xcalibur Python interpreter.
- `requirements-overlay.txt`: packages intended to be installed outside the base Xcalibur tree.
- `report_overlay_requirements.py`: compared the fixed interpreter against the overlay requirements.
- `build_overlay_runtime.bat`: installed missing packages into `runtime/site-packages`.
- `launcher_stub.c`: native launcher bound to `C:\Xcalibur\Python312\pythonw.exe`.
- `build_launcher_stub.bat`: compiled the native launcher.

This path is paused for now and is not part of the active workflow.
