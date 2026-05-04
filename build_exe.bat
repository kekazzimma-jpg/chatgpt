@echo off
setlocal

REM Build a portable Windows EXE for p7m_tool.py using PyInstaller.

where py >nul 2>nul
if errorlevel 1 (
  echo [ERRORE] Python non trovato. Installa Python 3.10+ e riprova.
  exit /b 1
)

py -m pip install --upgrade pip
if errorlevel 1 exit /b 1

py -m pip install -r requirements.txt pyinstaller
if errorlevel 1 exit /b 1

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist p7m-portable.spec del /q p7m-portable.spec

py -m PyInstaller --onefile --windowed --name p7m-portable p7m_tool.py
if errorlevel 1 (
  echo [ERRORE] Build fallita.
  exit /b 1
)

echo.
echo [OK] EXE creato: dist\p7m-portable.exe
endlocal
