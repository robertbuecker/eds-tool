@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "XCAL_PY=C:\Xcalibur\Python312\python.exe"
set "OVERLAY_DIR=%SCRIPT_DIR%runtime\site-packages"
set "REQ_FILE=%SCRIPT_DIR%requirements-overlay.txt"
set "MISSING_REQ_FILE=%SCRIPT_DIR%runtime\requirements-overlay.missing.txt"

if not exist "%XCAL_PY%" (
    echo ERROR: Fixed interpreter not found at "%XCAL_PY%"
    exit /b 1
)

if not exist "%SCRIPT_DIR%runtime" mkdir "%SCRIPT_DIR%runtime"
if exist "%OVERLAY_DIR%" (
    echo Removing previous overlay at "%OVERLAY_DIR%"
    rmdir /s /q "%OVERLAY_DIR%"
)

echo Comparing "%REQ_FILE%" against the fixed Xcalibur environment...
"%XCAL_PY%" "%SCRIPT_DIR%report_overlay_requirements.py" --requirements "%REQ_FILE%" --write-missing "%MISSING_REQ_FILE%"
if errorlevel 1 (
    echo.
    echo Requirement analysis FAILED.
    exit /b 1
)

if not exist "%MISSING_REQ_FILE%" (
    echo ERROR: Missing-requirements file was not created.
    exit /b 1
)

for %%A in ("%MISSING_REQ_FILE%") do set "MISSING_SIZE=%%~zA"
if "%MISSING_SIZE%"=="0" (
    echo.
    echo All overlay requirements are already satisfied by the fixed environment.
    echo No packages were installed into "%OVERLAY_DIR%".
    exit /b 0
)

echo.
echo Installing missing overlay packages into "%OVERLAY_DIR%"
"%XCAL_PY%" -m pip install --target "%OVERLAY_DIR%" -r "%MISSING_REQ_FILE%"
if errorlevel 1 (
    echo.
    echo Overlay build FAILED.
    exit /b 1
)

echo.
echo Overlay build complete.
echo Launch with:
echo   "%XCAL_PY%" "%SCRIPT_DIR%launch_eds_tool.py"
exit /b 0
