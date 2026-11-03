@echo off
REM Builds a standalone app: dist\FileConverter\FileConverter.exe
REM (copy the whole dist\FileConverter folder anywhere - no Python needed).
setlocal
cd /d "%~dp0"
title File Converter - Build

if exist ".venv\Scripts\python.exe" goto :haveenv
call "%~dp0setup.bat" nopause
if errorlevel 1 exit /b 1
:haveenv

echo Installing PyInstaller ...
".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :error

echo Building - this takes a few minutes ...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --windowed ^
    --name FileConverter ^
    --icon icon.ico ^
    --add-data "icon.ico;." ^
    --collect-all pypandoc ^
    --collect-all imageio_ffmpeg ^
    --collect-all pypdfium2 ^
    --collect-all pypdfium2_raw ^
    --collect-data reportlab ^
    --hidden-import converter.documents ^
    --hidden-import converter.pdf ^
    --hidden-import converter.images ^
    --hidden-import converter.data ^
    --hidden-import converter.media ^
    --hidden-import converter.pdfrender ^
    app.py
if errorlevel 1 goto :error

echo.
echo ==========================================================
echo  Built: dist\FileConverter\FileConverter.exe
echo ==========================================================
explorer "dist\FileConverter"
pause
exit /b 0

:error
echo.
echo  Build failed - copy this window's text and send it for help.
pause
exit /b 1
