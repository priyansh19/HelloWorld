"""Detect whether a fullscreen app (video, game, presentation) is in front.

Used to auto-hide the taskbar buddy so it never covers fullscreen content. A
window counts as fullscreen when it covers its entire monitor and is not the
desktop/shell. Windows-only and fully guarded; returns False elsewhere.
"""

from __future__ import annotations

import sys

# Window classes that are the desktop/shell, not a real fullscreen app.
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Windows.UI.Core.CoreWindow"}


def fullscreen_app_active() -> bool:
    if not sys.platform.startswith("win"):
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32

        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False

        buf = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(hwnd, buf, 256)
        if buf.value in _SHELL_CLASSES:
            return False

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD),
                        ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT),
                        ("dwFlags", wintypes.DWORD)]

        wr = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(wr)):
            return False

        hmon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return False
        m = mi.rcMonitor

        # Fullscreen if the window covers the whole monitor (small slack).
        return (wr.left <= m.left + 1 and wr.top <= m.top + 1
                and wr.right >= m.right - 1 and wr.bottom >= m.bottom - 1)
    except Exception:
        return False
