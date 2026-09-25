@echo off
rem Double-click to run the TunCO2 Pro test suite (sets up .venv on first use)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-TunCO2Pro.ps1" -Test
pause
