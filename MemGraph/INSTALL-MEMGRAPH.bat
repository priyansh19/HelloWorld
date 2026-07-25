@echo off
setlocal enabledelayedexpansion
title MemGraph - installer
color 0b

echo ==================================================
echo    MemGraph  -  install dependencies and run
echo ==================================================
echo.

REM ---- 1. Ensure Python is available ----------------------------------
where python >nul 2>&1
if errorlevel 1 (
    echo Python is not installed. Installing it with winget...
    winget install -e --id Python.Python.3.11 --accept-source-agreements --accept-package-agreements
    echo.
    echo  ^>^> Python was installed. Please CLOSE this window,
    echo  ^>^> then double-click this file again to finish.
    echo.
    pause
    exit /b 0
)

for /f "delims=" %%V in ('python --version') do echo Using %%V

REM ---- 1b. Enable Windows Long Path support (PySide6 has very deep paths) --
reg query "HKLM\SYSTEM\CurrentControlSet\Control\FileSystem" /v LongPathsEnabled 2>nul | find "0x1" >nul
if errorlevel 1 (
    echo.
    echo Enabling Windows long-path support ^(needed for PySide6^).
    echo A Windows security ^(UAC^) prompt will appear - please click Yes.
    powershell -NoProfile -Command "Start-Process reg -Verb RunAs -Wait -ArgumentList 'add HKLM\SYSTEM\CurrentControlSet\Control\FileSystem /v LongPathsEnabled /t REG_DWORD /d 1 /f'"
)

echo.
echo [1/4] Upgrading pip...
python -m pip install --upgrade pip

echo.
echo [2/4] Downloading MemGraph...
set "ZIP=%TEMP%\memgraph_src.zip"
set "DEST=%TEMP%\memgraph_src"
if exist "%DEST%" rmdir /s /q "%DEST%"
mkdir "%DEST%"
curl -L -o "%ZIP%" "https://codeload.github.com/priyansh19/HelloWorld/zip/refs/heads/claude/windows-memory-widget-kte9g9"
if errorlevel 1 ( echo Download failed - check your internet connection. & pause & exit /b 1 )
tar -xf "%ZIP%" -C "%DEST%"

set "SRC="
for /d %%D in ("%DEST%\HelloWorld-*") do set "SRC=%%D\MemGraph"
if not defined SRC ( echo Could not unpack the download. & pause & exit /b 1 )

echo.
echo [3/4] Installing MemGraph and its dependencies...
echo       ^(PySide6 is large - this can take a few minutes^)
python -m pip install "%SRC%"
if errorlevel 1 ( echo Install failed - see the messages above. & pause & exit /b 1 )
REM Optional: in-process CPU/GPU temperatures (safe to fail).
python -m pip install pythonnet >nul 2>&1

echo.
echo [3b/4] Using the classic card widget (no llama) with GPU tiles...
python -c "from memgraph.config import load_config, save_config; c=load_config(); c.mode='pinned'; c.enabled_metrics=['cpu','ram','gpu','vram','npu']; save_config(c)" 2>nul

echo.
echo [4/4] Launching MemGraph...
start "" pythonw -m memgraph

echo.
echo ==================================================
echo   Done!  The MemGraph card should appear on your
echo   desktop. Right-click it -^> Settings to pick
echo   metrics, or "Enable full temperatures (admin)"
echo   for CPU/GPU temps.
echo.
echo   It will start automatically at every login.
echo   To start it now, run:   pythonw -m memgraph
echo ==================================================
echo.
pause
endlocal
