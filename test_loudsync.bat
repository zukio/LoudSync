@echo off
cd /d "%~dp0"
echo Testing LoudSync Python version...
echo.
"N:/data/github/LoudSync/venv/Scripts/python.exe" main.py --help
echo.
echo Testing with measurement mode on samples directory...
"N:/data/github/LoudSync/venv/Scripts/python.exe" main.py --input-dir samples --mode measure --preset -16 --no-console
pause
