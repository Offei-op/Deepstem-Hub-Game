@echo off
setlocal
cd /d "%~dp0"
set "DEEPSTEM_LAUNCH_ID=%RANDOM%-%RANDOM%-%RANDOM%"
set "DEEPSTEM_RESTART_NOTICE=%~dp0data-private\restart-%DEEPSTEM_LAUNCH_ID%.flag"
if "%~1"=="--share" (
  echo Starting ONLINE studio. Use the public link after ONLINE STUDIO IS READY.
) else if "%~1"=="--stop-share" (
  echo Stopping online studio access.
) else (
  echo Opening Deepstem Studio. A healthy online session will be kept running.
 echo To host on the internet, open Start Event Online.cmd.
)
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" scripts\launch.py %*
) else (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 scripts\launch.py %*
  ) else (
    python scripts\launch.py %*
  )
)
set "STUDIO_EXIT=%ERRORLEVEL%"
if exist "%DEEPSTEM_RESTART_NOTICE%" (
  del /q "%DEEPSTEM_RESTART_NOTICE%" >nul 2>nul
  echo.
  echo This studio window was replaced by another launcher. Use the newest window.
  exit /b 0
)
if not "%STUDIO_EXIT%"=="0" (
  echo.
  echo Studio stopped with exit code %STUDIO_EXIT%. Read the message above or check artifacts\launcher-*.log.
  pause
  exit /b %STUDIO_EXIT%
)
exit /b 0
