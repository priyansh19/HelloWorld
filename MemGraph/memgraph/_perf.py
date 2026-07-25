"""Best-effort Windows performance-counter reader (PDH) for NPU / GPU engines.

There is no portable cross-vendor API for NPU (or per-engine GPU) utilisation.
On Windows 11 these are exposed as PDH performance counters — the same ones
Task Manager reads — e.g. ``\\NPU Engine(*)\\Utilization Percentage``. This
module wraps PDH via ctypes with heavy guarding: any failure (older Windows,
no such counter, non-Windows) degrades to ``None`` so callers show ``n/a``
instead of crashing.

We report the *max* utilisation across engine instances (matching how tools
like Task Manager surface a single headline number), clamped to 0-100.
"""

from __future__ import annotations

import sys
from typing import Optional

_PDH_FMT_DOUBLE = 0x00000200
_PDH_MORE_DATA = 0x800007D2
_PDH_CSTATUS_VALID_DATA = 0x00000000


class PerfCounter:
    """A single kept-open PDH wildcard counter query.

    Construct with a counter path; call :meth:`value` each tick. The first
    call after construction primes the query and may return ``None`` until a
    second sample exists (utilisation counters need two samples).

    ``aggregate`` combines the wildcard instances: ``"max"`` (headline
    utilisation, like Task Manager) or ``"sum"`` (e.g. total memory in use).
    ``clamp_percent`` caps the result to 0-100 for percentage counters; set it
    False for byte counters like GPU dedicated-memory usage.
    """

    def __init__(self, path: str, aggregate: str = "max",
                 clamp_percent: bool = True) -> None:
        self._ok = False
        self._query = None
        self._counter = None
        self._pdh = None
        self._aggregate = aggregate
        self._clamp = clamp_percent
        if not sys.platform.startswith("win"):
            return
        self._init(path)

    def _init(self, path: str) -> None:
        try:
            import ctypes
            from ctypes import wintypes

            pdh = ctypes.windll.pdh

            class PDH_FMT_COUNTERVALUE(ctypes.Structure):
                _fields_ = [("CStatus", wintypes.DWORD),
                            ("doubleValue", ctypes.c_double)]

            class PDH_FMT_COUNTERVALUE_ITEM_W(ctypes.Structure):
                _fields_ = [("szName", wintypes.LPWSTR),
                            ("FmtValue", PDH_FMT_COUNTERVALUE)]

            query = wintypes.HANDLE()
            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(query)) != 0:
                return
            counter = wintypes.HANDLE()
            if pdh.PdhAddEnglishCounterW(query, path, 0,
                                         ctypes.byref(counter)) != 0:
                pdh.PdhCloseQuery(query)
                return
            # Prime the query (first collection establishes a baseline).
            pdh.PdhCollectQueryData(query)

            self._pdh = pdh
            self._ctypes = ctypes
            self._wintypes = wintypes
            self._item_type = PDH_FMT_COUNTERVALUE_ITEM_W
            self._query = query
            self._counter = counter
            self._ok = True
        except Exception:
            self._ok = False

    @property
    def available(self) -> bool:
        return self._ok

    def value(self) -> Optional[float]:
        """Return the max engine utilisation (0-100), or ``None`` if unread."""
        if not self._ok:
            return None
        try:
            ctypes = self._ctypes
            pdh = self._pdh
            if pdh.PdhCollectQueryData(self._query) != 0:
                return None

            size = self._wintypes.DWORD(0)
            count = self._wintypes.DWORD(0)
            ret = pdh.PdhGetFormattedCounterArrayW(
                self._counter, _PDH_FMT_DOUBLE,
                ctypes.byref(size), ctypes.byref(count), None)
            if ret != _PDH_MORE_DATA or size.value == 0:
                return None

            buf = (ctypes.c_byte * size.value)()
            ret = pdh.PdhGetFormattedCounterArrayW(
                self._counter, _PDH_FMT_DOUBLE,
                ctypes.byref(size), ctypes.byref(count), buf)
            if ret != 0:
                return None

            items = ctypes.cast(
                buf, ctypes.POINTER(self._item_type))
            vals = []
            for i in range(count.value):
                fv = items[i].FmtValue
                if fv.CStatus == _PDH_CSTATUS_VALID_DATA:
                    vals.append(float(fv.doubleValue))
            if not vals:
                return None
            agg = sum(vals) if self._aggregate == "sum" else max(vals)
            if self._clamp:
                return max(0.0, min(100.0, agg))
            return max(0.0, agg)
        except Exception:
            return None

    def close(self) -> None:
        try:
            if self._ok and self._pdh is not None:
                self._pdh.PdhCloseQuery(self._query)
        except Exception:
            pass
        self._ok = False


# Display-adapter class GUID under HKLM\SYSTEM\...\Control\Class.
_DISPLAY_CLASS = r"SYSTEM\CurrentControlSet\Control\Class" \
    r"\{4d36e968-e325-11ce-bfc1-08002be10318}"


def gpu_total_vram_bytes() -> Optional[int]:
    """Total dedicated VRAM (bytes) of the largest GPU, from the driver's
    registry entry (``HardwareInformation.qwMemorySize``). No admin needed.

    This is where Task Manager gets the "Dedicated GPU memory" total for any
    vendor. Returns ``None`` off-Windows or if unreadable.
    """
    if not sys.platform.startswith("win"):
        return None
    try:
        import winreg
        best = None
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, _DISPLAY_CLASS) as base:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(base, i)
                except OSError:
                    break
                i += 1
                if not sub.isdigit():
                    continue
                try:
                    with winreg.OpenKey(base, sub) as k:
                        raw, _ = winreg.QueryValueEx(
                            k, "HardwareInformation.qwMemorySize")
                    v = int.from_bytes(raw, "little") if isinstance(raw, bytes) \
                        else int(raw)
                    if v > 0 and (best is None or v > best):
                        best = v
                except OSError:
                    continue
        return best
    except Exception:
        return None
