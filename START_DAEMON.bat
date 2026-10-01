@echo off
title Auto Collect MyGames - Background Daemon
chcp 65001 > nul
cd /d "%~dp0"

echo ========================================================
echo   Auto Collect MyGames: Starting Silent Background Daemon
echo ========================================================
echo.
if exist ".\.venv\Scripts\python.exe" (
    .\.venv\Scripts\python.exe app.py --daemon
) else (
    python app.py --daemon
)
