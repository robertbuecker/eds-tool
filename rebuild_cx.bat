@echo off
REM Rebuild EDS Tool with cx_Freeze into dist-cx.
echo Building EDS Tool with cx_Freeze...
echo.

powershell -ExecutionPolicy Bypass -File .\scripts\with-eds-mini.ps1 python setup_cx.py build_exe
if errorlevel 1 (
    echo.
    echo cx_Freeze build FAILED - check errors above
    pause
    exit /b 1
)

echo.
echo Build complete! Executable is at: dist-cx\eds_tool.exe
echo.
pause
