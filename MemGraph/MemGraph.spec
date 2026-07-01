# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MemGraph.

Produces a single windowed installer/app: MemGraph-Setup.exe. Run with no args
it shows the setup UI; once installed, the copied MemGraph.exe runs the widget.

Build with:  pyinstaller --noconfirm MemGraph.spec
"""

import glob
import os

from PyInstaller.utils.hooks import collect_all

hiddenimports = ["pynvml", "PySide6.QtNetwork"]
datas = []
binaries = []

# Bundle the LibreHardwareMonitor DLLs (fetched by CI into lhm/) so the app can
# read CPU/GPU/memory temperatures in-process. If absent, the app falls back to
# the WMI/ACPI reader.
for dll in glob.glob("lhm/*.dll"):
    datas.append((dll, "lhm"))

# pythonnet / clr_loader must be fully collected for the frozen build.
for pkg in ("pythonnet", "clr_loader"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ["run.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "pyqtgraph", "numpy"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="MemGraph-Setup",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico" if os.path.exists("assets/icon.ico") else None,
)
