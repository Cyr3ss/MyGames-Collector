@echo off
title Auto Collect MyGames - Build Release
chcp 65001 > nul
cd /d "%~dp0"

echo ====================================================================
echo   Auto Collect MyGames: Building Release for GitHub
echo ====================================================================
echo.

REM 1. Detect Python and PyInstaller executable
set PYTHON_EXE=python
if exist ".\.venv\Scripts\python.exe" (
    set PYTHON_EXE=.\.venv\Scripts\python.exe
)

set PYINSTALLER_EXE=pyinstaller
if exist ".\.venv\Scripts\pyinstaller.exe" (
    set PYINSTALLER_EXE=.\.venv\Scripts\pyinstaller.exe
)

echo [*] Checking PyInstaller...
%PYINSTALLER_EXE% --version >nul 2>&1
if errorlevel 1 (
    echo [!] PyInstaller not found. Installing dependencies...
    %PYTHON_EXE% -m pip install -r requirements.txt
)

echo [*] Cleaning previous builds...
if exist "build" rmdir /s /q "build"
if exist "dist\AutoCollect" rmdir /s /q "dist\AutoCollect"
if exist "dist\AutoCollect-Release.zip" del /f /q "dist\AutoCollect-Release.zip"

echo [*] Compiling application using PyInstaller...
%PYINSTALLER_EXE% --noconfirm --onedir --windowed --name "AutoCollect" --add-data "ui;ui" --collect-all playwright app.py

if errorlevel 1 (
    echo.
    echo [X] ERROR: Build failed.
    pause
    exit /b 1
)

echo [*] Copying config.example.yaml to dist as default config...
if exist "config.example.yaml" (
    copy /y "config.example.yaml" "dist\AutoCollect\config.yaml" >nul
)

echo [*] Creating ZIP archive for GitHub Releases...
powershell -Command "Compress-Archive -Path 'dist\AutoCollect\*' -DestinationPath 'dist\AutoCollect-Release.zip' -Force"

echo.
echo ====================================================================
echo   [V] BUILD COMPLETED SUCCESSFULLY!
echo ====================================================================
echo   Release artifacts:
echo     - Directory: dist\AutoCollect\
echo     - ZIP archive: dist\AutoCollect-Release.zip
echo.
echo   How to publish the release on GitHub:
echo     1. Go to your GitHub repository.
echo     2. Click 'Releases' -> 'Draft a new release'.
echo     3. Specify the tag version (e.g. v1.0.0).
echo     4. Drag and drop 'dist\AutoCollect-Release.zip' into the binaries area.
echo     5. Click 'Publish release'!
echo ====================================================================
echo.
pause
