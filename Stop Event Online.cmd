@echo off
setlocal
cd /d "%~dp0"
call "Start Studio.cmd" --stop-share --no-browser
