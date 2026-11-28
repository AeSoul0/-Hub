@echo off
rem AEHub on Windows (N11): a double click starts it. Everything is in start.ps1.
rem "AEHub.cmd -Stop" stops it.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1" %*
if errorlevel 1 (
    echo.
    echo AEHub non e partito: leggi il messaggio sopra.
    pause
    exit /b 1
)
