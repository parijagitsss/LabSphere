
@echo off
title LabSphere Student Client Setup

cd /d "%~dp0"

echo =====================================
echo       LabSphere Client Setup
echo =====================================
echo.

where py >nul 2>&1
if not errorlevel 1 (
    set "PYTHON=py"
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON=python"
    ) else (
        echo Python was not found.
        echo Please install Python 3.10 or later first.
        echo https://www.python.org/downloads/
        pause
        exit /b 1
    )
)

echo Creating virtual environment...
if not exist ".venv\Scripts\python.exe" (
    %PYTHON% -m venv .venv
    if errorlevel 1 (
        echo Failed to create virtual environment.
        pause
        exit /b 1
    )
)

echo.
echo Installing dependencies...
".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 (
    echo Failed to upgrade pip.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed.
    pause
    exit /b 1
)

echo.
echo =====================================
echo       Setup completed successfully!
echo =====================================
pause
