@echo off
title Auto Collect MyGames - Loader
chcp 65001 > nul
cd /d "%~dp0"

echo ========================================================
echo   Auto Collect MyGames: Starting GUI Application...
echo ========================================================
echo.
if exist ".\.venv\Scripts\python.exe" (
    .\.venv\Scripts\python.exe app.py
) else (
    python app.py
)
