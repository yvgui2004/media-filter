@echo off
rem Double-click to launch Media Filter
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" goto run

echo [ERROR] venv ".venv" not found. Install dependencies first:
echo   python -m venv .venv
echo   .venv\Scripts\python.exe -m pip install -e ".[ai]"
echo.
echo Also install FFmpeg ^(ffmpeg.exe + ffprobe.exe^) and put it on PATH
echo or in C:\ffmpeg\bin. See README.md for the full setup.
pause
exit /b 1

:run
".venv\Scripts\python.exe" -m mediafilter
if errorlevel 1 pause
