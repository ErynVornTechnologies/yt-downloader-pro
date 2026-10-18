@echo off
rem Launcher for the YT Downloader Pro GUI.
rem Finds a usable Python, verifies dependencies (auto-installs if missing),
rem then starts the app window without keeping a console open.
setlocal EnableExtensions
title YT Downloader Pro
cd /d "%~dp0"

rem --- Pick a Python interpreter -------------------------------------------
set "PYEXE="
py -3.12 -c "import sys; sys.exit(0)" >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYEXE=py -3.12"
    goto :deps
)
py -c "import sys; sys.exit(0)" >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYEXE=py"
    goto :deps
)
where python >nul 2>&1
if %ERRORLEVEL%==0 (
    set "PYEXE=python"
    goto :deps
)
echo No Python found. Install Python 3.10+ from python.org
pause
exit /b 1

:deps
rem --- Verify dependencies; install them into the chosen interpreter -------
%PYEXE% -c "import yt_dlp, customtkinter, PIL" >nul 2>&1
if not %ERRORLEVEL%==0 (
    echo First run: installing dependencies...
    %PYEXE% -m pip install --quiet yt-dlp customtkinter pillow
    %PYEXE% -c "import yt_dlp, customtkinter, PIL" >nul 2>&1
    if not %ERRORLEVEL%==0 (
        echo Dependency installation failed. Check your internet connection.
        pause
        exit /b 1
    )
)

rem --- Start the GUI detached from this console ----------------------------
start "" pyw -3.12 "%~dp0downloader.py"
endlocal