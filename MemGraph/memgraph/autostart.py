"""Windows autostart management via the per-user ``Run`` registry key.

Registering under ``HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run``
launches MemGraph at login without admin rights and is self-managing (no
stray Startup-folder shortcut to clean up).

All functions no-op safely on non-Windows platforms so the module can be
imported anywhere.
"""

from __future__ import annotations

import sys
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_KEY = "MemGraph"


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def current_launch_command() -> str:
    """Best-effort command that re-launches this app.

    When frozen by PyInstaller, ``sys.executable`` is the widget's own .exe.
    When running from source, we invoke ``python -m memgraph``.
    """
    exe = Path(sys.executable)
    if getattr(sys, "frozen", False):
        return f'"{exe}" --widget'
    # From a pip/source install, prefer the console-less pythonw.exe so no
    # terminal window flashes at login.
    pyw = exe.with_name("pythonw.exe")
    launcher = pyw if pyw.exists() else exe
    return f'"{launcher}" -m memgraph --widget'


def is_enabled() -> bool:
    if not _is_windows():
        return False
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, APP_KEY)
            return True
    except FileNotFoundError:
        return False
    except OSError:
        return False


def enable(command: str | None = None) -> bool:
    """Register the app to start at login. Returns True on success."""
    if not _is_windows():
        return False
    try:
        import winreg  # type: ignore

        cmd = command or current_launch_command()
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, APP_KEY, 0, winreg.REG_SZ, cmd)
        return True
    except OSError:
        return False


def disable() -> bool:
    """Remove the autostart entry. Returns True if now absent."""
    if not _is_windows():
        return False
    try:
        import winreg  # type: ignore

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, APP_KEY)
        return True
    except FileNotFoundError:
        return True  # already gone
    except OSError:
        return False


def apply(desired: bool) -> bool:
    """Make the registry match ``desired``. Returns the resulting state."""
    if desired:
        enable()
    else:
        disable()
    return is_enabled()
