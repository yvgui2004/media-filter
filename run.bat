@echo off
rem Double-click to launch Media Filter
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] venv ".venv" not found. Install dependencies first:
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -e .
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m mediafilter