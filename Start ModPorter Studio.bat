@echo off
rem ModPorter Studio - double-click launcher (Windows)
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found. Install it from https://www.python.org/downloads/
  pause
  exit /b 1
)
python -m modporter.cli studio
pause
