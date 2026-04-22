@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
set "VENV_PY=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "FALLBACK_PY=python"

if "%~1"=="" (
  echo Nessun file passato allo script.
  pause
  exit /b 1
)

set "INPUT_FILE=%~1"
set "INPUT_DIR=%~dp1"
set "LOG_DIR=%INPUT_DIR%OCR"
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"
set "RUN_LOG=%LOG_DIR%\ocr_run.log"

echo ==============================================>>"%RUN_LOG%"
echo [%date% %time%] Avvio conversione: "%INPUT_FILE%">>"%RUN_LOG%"

if exist "%VENV_PY%" (
  "%VENV_PY%" "%SCRIPT_DIR%convert.py" "%INPUT_FILE%" >>"%RUN_LOG%" 2>&1
) else (
  %FALLBACK_PY% "%SCRIPT_DIR%convert.py" "%INPUT_FILE%" >>"%RUN_LOG%" 2>&1
)

if errorlevel 1 (
  echo [ERRORE] Conversione fallita.>>"%RUN_LOG%"
  echo Conversione fallita. Controlla il log:
  echo "%RUN_LOG%"
  pause
  exit /b 1
)

echo [OK] Conversione completata.>>"%RUN_LOG%"
exit /b 0
