@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "XCAL_PY=C:\Xcalibur\Python312\python.exe"

if not exist "%XCAL_PY%" (
    echo ERROR: Fixed interpreter not found at "%XCAL_PY%"
    exit /b 1
)

"%XCAL_PY%" "%SCRIPT_DIR%launch_eds_tool.py" %*
