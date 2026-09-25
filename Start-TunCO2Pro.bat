@echo off
rem Double-click to start TunCO2 Pro
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-TunCO2Pro.ps1"
if errorlevel 1 pause
