@echo off
setlocal
cd /d "%~dp0"
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  py -3.12 source_start.py
) else (
  py -3 source_start.py
)
if errorlevel 1 pause
endlocal
