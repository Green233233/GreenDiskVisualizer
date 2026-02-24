@echo off
rem Simple launcher for Green Disk Visualizer (alpha v0.0.1)
cd /d "%~dp0"

rem Prefer python if available, otherwise try py
where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
) else (
    py main.py
)

