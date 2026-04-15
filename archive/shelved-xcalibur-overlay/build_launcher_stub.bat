@echo off
setlocal

set "SCRIPT_DIR=%~dp0"

where cl >nul 2>nul
if errorlevel 1 (
    echo ERROR: MSVC compiler "cl" not found in PATH.
    echo Open a Developer Command Prompt for Visual Studio and rerun this script.
    exit /b 1
)

cl /nologo /O2 /EHsc /DUNICODE /D_UNICODE /Fe:"%SCRIPT_DIR%eds_tool_launcher.exe" "%SCRIPT_DIR%launcher_stub.c" shell32.lib user32.lib
if errorlevel 1 (
    echo.
    echo Launcher build FAILED.
    exit /b 1
)

echo.
echo Built native launcher:
echo   "%SCRIPT_DIR%eds_tool_launcher.exe"
exit /b 0
