@echo off
:: Enterprise Screen Recorder Launcher
:: Run this as Administrator for best results

setlocal enabledelayedexpansion

echo ========================================
echo  Enterprise Screen Recorder
echo ========================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python is not installed or not in PATH
    pause
    exit /b 1
)

:: Change to script directory
cd /d "%~dp0"

:: Install dependencies if needed
if not exist ".deps_installed" (
    echo Installing dependencies...
    pip install -r requirements.txt
    if not errorlevel 1 (
        echo. > .deps_installed
    )
)

echo.
echo Starting recorder...
echo Press Ctrl+C to stop gracefully
echo.

:: Run with default settings
:: Modify these parameters as needed for your environment:
::   --employee    : Employee name (uses Windows username by default)
::   --fps         : Frames per second (default: 5)
::   --chunk       : Chunk duration in seconds (default: 600 = 10 minutes)
::   --cache       : Local cache folder (default: ./cache)
::   --network     : Network share path

python recorder_enterprise.py ^
    --cache "./cache" ^
    --network "\\OFFICE_SERVER\Recordings" ^
    --fps 5 ^
    --chunk 600

echo.
echo Recorder stopped.
pause

