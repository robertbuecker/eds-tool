@echo off
REM Rebuild EDS Tool with optimized PyInstaller spec
echo Building EDS Tool...
echo.
call conda activate eds-tools
if errorlevel 1 (
    echo ERROR: Could not activate eds-tools environment
    pause
    exit /b 1
)

python -m PyInstaller --clean eds_tool_folder.spec

if errorlevel 1 (
    echo.
    echo Build FAILED - check errors above
    pause
    exit /b 1
)

echo.
echo Build complete! Executable is at: dist\eds_tool\eds_tool.exe
echo.
pause
