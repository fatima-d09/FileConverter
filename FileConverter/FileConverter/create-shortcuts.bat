@echo off
REM Puts a "File Converter" shortcut (with its own icon) on the Desktop and in the Start menu.
setlocal
cd /d "%~dp0"
title File Converter - Shortcuts

if exist ".venv\Scripts\python.exe" goto :ok
echo Run run.bat once first, then run this again.
pause
exit /b 1

:ok
echo Preparing ...
".venv\Scripts\python.exe" -m pip install --quiet pywin32
echo Creating shortcuts ...
".venv\Scripts\python.exe" create_shortcuts.py
echo.
echo Done. To pin it to the taskbar:
echo   right-click "File Converter" on your Desktop
echo   - Windows 11: Show more options, then Pin to taskbar
echo   - Windows 10: Pin to taskbar
echo.
pause
