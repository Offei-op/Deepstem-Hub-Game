@echo off
setlocal
cd /d "%~dp0"
echo Starting public HTTPS access with isolated game previews.
echo Keep this window open while teams are connected. Ctrl+C stops online access.
call "Start Studio.cmd" --share %*
