@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "PY_EXE=py"

where %PY_EXE% >nul 2>nul
if errorlevel 1 (
  echo Python launcher 'py' non trovato. Installa Python 3 da python.org e riprova.
  exit /b 1
)

%PY_EXE% -3 "%SCRIPT_DIR%install_windows.py"
if errorlevel 1 (
  echo Setup fallito.
  exit /b 1
)

echo Setup completato con successo.
endlocal
