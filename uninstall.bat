@echo off
setlocal EnableDelayedExpansion

:: ============================================================
:: Screen Recorder - Uninstaller
:: Stops the recorder and removes from startup
:: ============================================================

title Screen Recorder Uninstaller
color 0C

echo.
echo ============================================================
echo        SCREEN RECORDER - UNINSTALLER
echo ============================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Stop any running instances
echo [1/2] Stopping recorder...
taskkill /F /IM pythonw.exe >nul 2>&1
taskkill /F /IM ffmpeg.exe >nul 2>&1
echo       Done
echo.

:: Remove from startup
echo [2/2] Removing from Windows startup...
python "%SCRIPT_DIR%setup_autostart.py" --remove

echo.
echo ============================================================
echo                    UNINSTALL COMPLETE
echo ============================================================
echo.
echo   The recorder has been stopped and removed from startup.
echo.
echo   Note: Recording files are kept in: %SCRIPT_DIR%recordings\
echo   Delete them manually if you don't need them.
echo.
echo ============================================================
echo.
pause

