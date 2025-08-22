@echo off
REM LoudSync Suite Build Script
REM Build script for LoudSync Suite with Fade/Crossfade integration

echo ================================
echo LoudSync Suite Build Script
echo ================================

REM Activate virtual environment if exists
if exist "venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call venv\Scripts\activate.bat
)

REM Install dependencies
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

REM Remove old build files
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM Execute build
echo Building LoudSync Suite...
pyinstaller LoudSyncSuite.spec

REM Check result
if exist "dist\LoudSyncSuite.exe" (
    echo.
    echo ================================
    echo Build SUCCESS!
    echo ================================
    echo Output: dist\LoudSyncSuite.exe
    echo.
    echo FFmpeg binaries should be placed in the same directory as the executable.
    echo.
) else (
    echo.
    echo ================================
    echo Build FAILED!
    echo ================================
    echo Please check the error messages above.
    echo.
)

pause
