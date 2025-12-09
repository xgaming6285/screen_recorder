@echo off
:: Keep window open on any error
if not defined IN_INSTALL (
    set IN_INSTALL=1
    cmd /k "%~f0" %*
    exit /b
)

setlocal EnableDelayedExpansion

:: ============================================================
:: Screen Recorder - Universal Windows Installer
:: Run this on ANY Windows PC - it installs everything needed
:: ============================================================

title Screen Recorder Installer
color 0A

echo.
echo ============================================================
echo        SCREEN RECORDER - UNIVERSAL INSTALLER
echo ============================================================
echo.

:: Get the directory where this script is located
set "SCRIPT_DIR=%~dp0"
echo Script directory: %SCRIPT_DIR%
cd /d "%SCRIPT_DIR%"
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Could not change to script directory
    goto :error
)

:: ============================================================
:: STEP 1: Check/Install Python
:: ============================================================
echo.
echo [1/4] Checking Python installation...

python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYVER=%%i
    echo       Found: !PYVER!
    goto :python_ok
)

echo       Python not found. Will install...
echo.
echo       Downloading Python installer (this may take a moment)...

set "PYTHON_URL=https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
set "PYTHON_INSTALLER=%TEMP%\python_installer.exe"

:: Download using PowerShell
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYTHON_URL%' -OutFile '%PYTHON_INSTALLER%'"

if not exist "%PYTHON_INSTALLER%" (
    echo       ERROR: Failed to download Python installer
    echo       Please install Python manually from https://python.org
    goto :error
)

echo       Installing Python (this may take 1-2 minutes)...
echo       Please wait...
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0

:: Wait a moment for installation to complete
timeout /t 5 /nobreak >nul

:: Refresh environment variables
echo       Refreshing environment...
for /f "tokens=2*" %%a in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%b"
set "PATH=%USER_PATH%;%PATH%"
set "PATH=%LOCALAPPDATA%\Programs\Python\Python311;%LOCALAPPDATA%\Programs\Python\Python311\Scripts;%PATH%"

del "%PYTHON_INSTALLER%" 2>nul
echo       Python installed!

:python_ok
:: Verify Python works
python --version >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo       ERROR: Python not accessible after installation.
    echo       Please close this window, restart your computer, and run install.bat again.
    goto :error
)
echo       [OK] Python ready
echo.

:: ============================================================
:: STEP 2: Check/Install FFmpeg
:: ============================================================
echo [2/4] Checking FFmpeg installation...

:: First check if ffmpeg.exe exists in script folder
if exist "%SCRIPT_DIR%ffmpeg.exe" (
    echo       [OK] FFmpeg found in script folder
    goto :ffmpeg_ok
)

:: Then check PATH
where ffmpeg >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo       [OK] FFmpeg found in PATH
    goto :ffmpeg_ok
)

echo       FFmpeg not found. Downloading...
echo.

set "FFMPEG_DIR=%SCRIPT_DIR%ffmpeg_temp"
set "FFMPEG_ZIP=%TEMP%\ffmpeg.zip"
set "FFMPEG_URL=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

echo       Downloading FFmpeg (about 80MB, please wait)...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%FFMPEG_URL%' -OutFile '%FFMPEG_ZIP%'"

if not exist "%FFMPEG_ZIP%" (
    echo       ERROR: Failed to download FFmpeg
    echo       Please download manually from https://ffmpeg.org/download.html
    goto :error
)

echo       Extracting FFmpeg...
if exist "%FFMPEG_DIR%" rmdir /s /q "%FFMPEG_DIR%"
powershell -Command "Expand-Archive -Path '%FFMPEG_ZIP%' -DestinationPath '%FFMPEG_DIR%' -Force"

:: Find and copy ffmpeg.exe using PowerShell (more reliable with paths)
echo       Copying ffmpeg.exe to script folder...
set "FFMPEG_DEST=%SCRIPT_DIR%ffmpeg.exe"
powershell -Command "$src = Get-ChildItem -Path '%FFMPEG_DIR%' -Recurse -Filter 'ffmpeg.exe' | Select-Object -First 1; if ($src) { Copy-Item $src.FullName -Destination '%FFMPEG_DEST%' -Force; Write-Host '       Copied from:' $src.FullName } else { Write-Host '       ERROR: ffmpeg.exe not found in archive' }"

:: Clean up temp folder
echo       Cleaning up...
del "%FFMPEG_ZIP%" 2>nul
rmdir /s /q "%FFMPEG_DIR%" 2>nul

:: Verify ffmpeg.exe exists
if exist "%FFMPEG_DEST%" (
    echo       [OK] FFmpeg installed successfully
) else (
    echo       ERROR: Could not copy FFmpeg to script folder
    echo       Try manually downloading ffmpeg.exe and placing it in:
    echo       %SCRIPT_DIR%
    goto :error
)

:ffmpeg_ok
echo.

:: ============================================================
:: STEP 3: Check script files exist
:: ============================================================
echo [3/4] Checking script files...

if not exist "%SCRIPT_DIR%recorder_background.pyw" (
    echo       ERROR: recorder_background.pyw not found!
    echo       Make sure all script files are in: %SCRIPT_DIR%
    goto :error
)
echo       [OK] recorder_background.pyw found

if not exist "%SCRIPT_DIR%setup_autostart.py" (
    echo       ERROR: setup_autostart.py not found!
    goto :error
)
echo       [OK] setup_autostart.py found
echo.

:: ============================================================
:: STEP 4: Setup Auto-Start
:: ============================================================
echo [4/4] Setting up auto-start...
echo.

python "%SCRIPT_DIR%setup_autostart.py"
if %ERRORLEVEL% NEQ 0 (
    echo       WARNING: Auto-start setup may have failed
)

echo.
echo Starting recorder in background...
python "%SCRIPT_DIR%setup_autostart.py" --start

echo.
echo ============================================================
echo                    INSTALLATION COMPLETE!
echo ============================================================
echo.
echo   The screen recorder is now:
echo     [x] Running in the background
echo     [x] Set to auto-start on Windows boot
echo.
echo   Recordings: %SCRIPT_DIR%recordings\
echo   Log file:   %SCRIPT_DIR%recorder.log
echo.
echo   Commands:
echo     Stop:    python setup_autostart.py --stop
echo     Start:   python setup_autostart.py --start
echo     Remove:  python setup_autostart.py --remove
echo.
echo ============================================================
echo.
echo You can close this window now.
echo.
goto :end

:error
echo.
echo ============================================================
echo   INSTALLATION FAILED - See error above
echo ============================================================
echo.

:end
echo Press any key to exit...
pause >nul
