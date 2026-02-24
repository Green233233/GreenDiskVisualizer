@echo off
rem Simple launcher for Green Disk Visualizer (alpha v0.0.1)
cd /d "%~dp0"

rem Prefer pythonw (no console window) over python
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw main.py
    exit
)

where pyw >nul 2>nul
if %errorlevel%==0 (
    start "" pyw main.py
    exit
)

rem Fallback: use python (console may briefly appear, hidden by the app)
where python >nul 2>nul
if %errorlevel%==0 (
    python main.py
) else (
    py main.py
)
