"""In-process temperature reader using LibreHardwareMonitorLib (bundled).

This lets MemGraph read CPU / GPU / memory temperatures itself, with no separate
app for the user to run. It loads the bundled ``LibreHardwareMonitorLib.dll`` via
pythonnet (``clr``) on a background thread and polls sensors.

Notes / limits (Windows reality, not a bug):
* GPU temperature usually reads **without** admin (vendor APIs).
* CPU and motherboard/memory temps need a kernel driver that only loads with
  **administrator** rights, so those appear only when MemGraph runs elevated.
* Many systems simply have no memory-temperature sensor in hardware.

Everything is guarded: if pythonnet/the DLL/.NET is unavailable, this degrades to
returning empty and the sampler falls back to the WMI/ACPI reader.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from typing import Optional


def _dll_dir_candidates() -> list[str]:
    dirs = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        dirs.append(meipass)
        dirs.append(os.path.join(meipass, "lhm"))
    here = os.path.dirname(os.path.abspath(__file__))
    dirs.append(here)
    dirs.append(os.path.join(here, "lhm"))
    dirs.append(os.path.dirname(os.path.abspath(sys.executable)))
    return dirs


def _find_dll() -> Optional[str]:
    for d in _dll_dir_candidates():
        p = os.path.join(d, "LibreHardwareMonitorLib.dll")
        if os.path.exists(p):
            return p
    return None


class LhmReader:
    """Background poller that keeps CPU/GPU/memory temps cached (Windows only)."""

    def __init__(self, interval: float = 3.0) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._data: dict = {"cpu": None, "gpu": None, "mem": None, "source": ""}
        self._computer = None
        self._ok = False
        self._enabled = sys.platform.startswith("win") and _find_dll() is not None
        self._stop = threading.Event()
        if self._enabled:
            threading.Thread(target=self._loop, name="MemGraphLHM",
                             daemon=True).start()

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------ #
    def _init_clr(self) -> bool:
        try:
            dll = _find_dll()
            if not dll:
                return False
            # Make dependencies (HidSharp.dll, etc.) resolvable.
            os.environ["PATH"] = os.path.dirname(dll) + os.pathsep + \
                os.environ.get("PATH", "")
            import clr  # pythonnet
            clr.AddReference(dll)
            from LibreHardwareMonitor.Hardware import Computer  # type: ignore

            comp = Computer()
            comp.IsCpuEnabled = True
            comp.IsGpuEnabled = True
            comp.IsMemoryEnabled = True
            comp.IsMotherboardEnabled = True
            comp.Open()
            self._computer = comp
            return True
        except Exception:
            return False

    def _loop(self) -> None:
        if not self._init_clr():
            self._enabled = False
            return
        self._ok = True
        while not self._stop.is_set():
            try:
                self._sample()
            except Exception:
                pass
            self._stop.wait(self._interval)

    def _sample(self) -> None:
        from ._wintemp import parse_temps
        sensors = []
        for hw in self._computer.Hardware:
            try:
                hw.Update()
                for sub in hw.SubHardware:
                    sub.Update()
                htype = str(hw.HardwareType)
                for s in hw.Sensors:
                    if str(s.SensorType) != "Temperature" or s.Value is None:
                        continue
                    sensors.append({"name": str(s.Name),
                                    "value": float(s.Value),
                                    "parent": htype})
                for sub in hw.SubHardware:
                    for s in sub.Sensors:
                        if str(s.SensorType) != "Temperature" or s.Value is None:
                            continue
                        sensors.append({"name": str(s.Name),
                                        "value": float(s.Value),
                                        "parent": str(hw.HardwareType)})
            except Exception:
                continue
        data = parse_temps({"source": "LibreHardwareMonitor (built-in)",
                            "sensors": sensors, "acpi": []})
        with self._lock:
            self._data = data

    # ------------------------------------------------------------------ #
    def get(self) -> dict:
        with self._lock:
            return dict(self._data)

    def stop(self) -> None:
        self._stop.set()
