@echo off
setlocal
pushd "%~dp0"
powershell -ExecutionPolicy Bypass -File "%~dp0scripts\with-eds-mini.ps1" python "%~dp0setup_cx.py" build_exe
set BUILD_RESULT=%ERRORLEVEL%
popd
endlocal & exit /b %BUILD_RESULT%
