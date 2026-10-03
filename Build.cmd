@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Installer.ps1" -RunTests
if errorlevel 1 exit /b 1
echo The installer is in the dist folder.
pause
