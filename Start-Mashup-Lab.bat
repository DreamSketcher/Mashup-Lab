@echo off
setlocal DisableDelayedExpansion
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\windows\run-gui.ps1"
set "result=%errorlevel%"
if not "%result%"=="0" (
  echo Launcher exited with code %result%.
  pause
)
exit /b %result%
