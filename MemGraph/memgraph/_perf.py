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
    """

    def __init__(self, path: str) -> None:
        self._ok = False
        self._query = None
        self._counter = None
        self._pdh = None
        self._structs = None
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
            best = None
            for i in range(count.value):
                fv = items[i].FmtValue
                if fv.CStatus == _PDH_CSTATUS_VALID_DATA:
                    v = float(fv.doubleValue)
                    if best is None or v > best:
                        best = v
            if best is None:
                return None
            return max(0.0, min(100.0, best))
        except Exception:
            return None

    def close(self) -> None:
        try:
            if self._ok and self._pdh is not None:
                self._pdh.PdhCloseQuery(self._query)
        except Exception:
            pass
        self._ok = False
