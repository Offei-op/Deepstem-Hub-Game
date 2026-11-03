@echo off
setlocal
cd /d "%~dp0"
echo Connecting your domain to this laptop. Your existing games and AI settings stay saved.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\permanent_network.py %*
) else (
  echo First open Start Studio.cmd once to prepare the Python environment, then run this setup again.
  pause
  exit /b 1
)
if errorlevel 1 (
  echo Read the setup message above for the next step.
  pause
  exit /b 1
)
echo Setup complete. Open Start Event Online.cmd to host the competition.
pause
