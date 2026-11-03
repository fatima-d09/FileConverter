@echo off
REM Double-click to start File Converter. The first run sets everything up automatically.
setlocal
cd /d "%~dp0"
title File Converter

if exist ".venv\Scripts\pythonw.exe" goto :check
echo First run - setting things up. This only happens once.
echo.
call "%~dp0setup.bat" nopause
if errorlevel 1 exit /b 1

:check
echo Starting File Converter ...
".venv\Scripts\python.exe" -c "import PySide6.QtWidgets, converter" > "%TEMP%\fileconverter_error.txt" 2>&1
if not errorlevel 1 goto :launch
if defined RETRIED goto :broken
REM Something is missing (e.g. an earlier setup was interrupted) - repair once.
set "RETRIED=1"
echo Some parts are missing - finishing the setup ...
call "%~dp0setup.bat" nopause
if errorlevel 1 exit /b 1
goto :check

:launch

start "" ".venv\Scripts\pythonw.exe" "%~dp0app.py" %*
exit /b 0

:broken
echo.
echo ----------------------------------------------------------
echo  The app could not start. Error:
echo ----------------------------------------------------------
type "%TEMP%\fileconverter_error.txt"
echo.
echo  Fix: delete the ".venv" folder in this folder, then run run.bat again.
echo  If it still fails, copy this window's text and send it for help.
pause
exit /b 1
