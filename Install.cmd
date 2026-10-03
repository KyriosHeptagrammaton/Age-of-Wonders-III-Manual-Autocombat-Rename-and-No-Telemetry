@echo off
echo Building and checking the AoW3 mod installer with Windows' built-in .NET tools...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-Installer.ps1" -RunTests -StartInstaller
if errorlevel 1 (
  echo.
  echo The installer could not be built or its checks failed. No game files were changed.
  echo Keep the error above when asking for help. Windows .NET Framework 4.8 is required.
  pause
  exit /b 1
)
