@echo off
REM ===================================================================
REM  MemGraph - local Windows build script
REM  Produces dist\MemGraph.exe (single-file, windowed).
REM ===================================================================
setlocal

echo [1/4] Creating virtual environment...
if not exist .venv (
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo [2/4] Installing dependencies...
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

echo [3/4] Running tests...
python -m pytest -q
if errorlevel 1 (
    echo Tests failed - aborting build.
    exit /b 1
)

echo [4/4] Building executable with PyInstaller...
pyinstaller --noconfirm MemGraph.spec

echo.
echo Done. Your installer is at: dist\MemGraph-Setup.exe
echo Double-click it to open the setup UI and install the widget.
endlocal
