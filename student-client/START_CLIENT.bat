
@echo off
title LabSphere Student Client

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Setup has not been completed yet.
    echo Please run SETUP.bat first.
    pause
    exit /b 1
)

echo =====================================
echo       Starting LabSphere Client
echo =====================================
echo.

".venv\Scripts\python.exe" student.py

echo.
echo Student client has stopped.
pause
