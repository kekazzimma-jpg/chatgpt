@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "FALLBACK_PY=python"

if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT_DIR%convert.py" "%~1"
) else (
  %FALLBACK_PY% "%SCRIPT_DIR%convert.py" "%~1"
)

endlocal
