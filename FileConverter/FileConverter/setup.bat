@echo off
REM One-time setup: finds (or installs) Python, then installs the app's libraries.
REM run.bat calls this automatically the first time - you normally don't need to run it.
setlocal
cd /d "%~dp0"
title File Converter - Setup
set "NOPAUSE=%~1"

echo ==========================================================
echo    File Converter - one-time setup
echo    This downloads about 300 MB and can take 5-10 minutes.
echo ==========================================================
echo.

call :findpython
if defined PY goto :havepy

echo Python 3.10 or newer was not found on this PC.
echo.
choice /c YN /m "Download and install Python 3.12 from python.org now"
if errorlevel 2 goto :manualpython
echo.
set "PYURL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
set "PYEXE=%TEMP%\python-3.12.10-amd64.exe"
echo Downloading Python 3.12 (about 25 MB) ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = 'Tls12'; $ProgressPreference = 'SilentlyContinue'; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYEXE%' -UseBasicParsing"
if not exist "%PYEXE%" goto :downloadfailed
echo Installing Python 3.12 (a small progress window will appear) ...
start "" /wait "%PYEXE%" /passive InstallAllUsers=0 InstallLauncherAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0
del "%PYEXE%" >nul 2>nul
call :findpython
if defined PY goto :havepy
echo.
echo Python seems to be installed, but this window can't see it yet.
echo Close this window and double-click run.bat again.
goto :fail

:downloadfailed
echo.
echo The download failed (no internet, or blocked by antivirus / network).
goto :manualpython

:manualpython
echo Please install Python:
echo   1. Go to https://www.python.org/downloads/
echo   2. Download and run the installer
echo   3. IMPORTANT: tick "Add python.exe to PATH" on the first screen
echo   4. Then double-click run.bat again
start "" "https://www.python.org/downloads/"
goto :fail

:havepy
echo Using:
%PY% --version
echo.

if exist ".venv\Scripts\python.exe" goto :venvok
echo Creating a private Python environment in the .venv folder ...
%PY% -m venv .venv
if errorlevel 1 goto :fail
:venvok

echo Installing libraries (PySide6, pandoc, PDF and image tools, ffmpeg) ...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail

echo.
echo ==========================================================
echo    Setup complete!
echo ==========================================================
if /i not "%NOPAUSE%"=="nopause" pause
exit /b 0

:fail
echo.
echo ----------------------------------------------------------
echo  Setup did NOT finish. Read the messages above.
echo  If you ask for help, copy this whole window's text
echo  (right-click the title bar, Edit, Select All, then Enter).
echo ----------------------------------------------------------
pause
exit /b 1


REM ---- sets PY to a working Python 3.10+ command, or leaves it empty ----
:findpython
set "PY="
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :trypython
set "PY=py -3"
exit /b 0
:trypython
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :trylocal
set "PY=python"
exit /b 0
:trylocal
for /d %%D in ("%LocalAppData%\Programs\Python\Python3*") do if exist "%%D\python.exe" set PY="%%D\python.exe"
exit /b 0
