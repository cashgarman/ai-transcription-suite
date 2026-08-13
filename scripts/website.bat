@echo off
rem Thin wrapper so the website manager works from cmd.exe and Explorer.
rem Usage: scripts\website.bat [command] [-Port 3000]
setlocal

if "%~1"=="" (
    set "WEBSITE_COMMAND=status"
) else (
    set "WEBSITE_COMMAND=%~1"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0website.ps1" %*

if errorlevel 1 (
    echo.
    echo Website command "%WEBSITE_COMMAND%" failed.
    exit /b 1
)
