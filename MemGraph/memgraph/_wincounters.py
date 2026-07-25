r"""Windows GPU / NPU / VRAM readings via PowerShell ``Get-Counter``.

The earlier ctypes/PDH reader proved unreliable on some machines (notably Intel
Arc). ``Get-Counter`` is the battle-tested way to read the very same performance
counters Task Manager shows — it handles the two-sample rate cooking for us — so
we shell out to it on a background thread and cache the results.

Counters used (all any-vendor, no driver/admin):
* ``\GPU Engine(*)\Utilization Percentage``      -> GPU compute %  (max engine)
* ``\GPU Adapter Memory(*)\Dedicated Usage``     -> dedicated VRAM in use (bytes)
* ``\NPU Engine(*)\Utilization Percentage``      -> NPU %          (max engine)

Everything is guarded and Windows-only; off-Windows (or on failure) values are
``None`` and callers fall back / show ``n/a``.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from typing import Optional

_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
function MaxC($path) {
    $s = (Get-Counter $path -ErrorAction SilentlyContinue).CounterSamples
    if ($s) { return ($s | Measure-Object -Property CookedValue -Maximum).Maximum }
    return $null
}
$ded = MaxC '\GPU Adapter Memory(*)\Dedicated Usage'
$shr = MaxC '\GPU Adapter Memory(*)\Shared Usage'
# Dedicated for discrete GPUs; shared for integrated GPUs (Intel/AMD iGPU).
$vram = if ($ded -ne $null -and $ded -gt 0) { $ded } else { $shr }
$o = [pscustomobject]@{
    gpu  = MaxC '\GPU Engine(*)\Utilization Percentage'
    vram = $vram
    npu  = MaxC '\NPU Engine(*)\Utilization Percentage'
}
$o | ConvertTo-Json -Compress
"""


def _clean(v, lo=0.0, hi=None) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f < lo:
        return None
    if hi is not None and f > hi:
        f = hi
    return f


def parse_counters(payload: dict) -> dict:
    """Pure mapping from the PowerShell payload to {gpu, vram, npu}."""
    payload = payload or {}
    return {
        "gpu": _clean(payload.get("gpu"), 0.0, 100.0),
        "vram": _clean(payload.get("vram"), 0.0),
        "npu": _clean(payload.get("npu"), 0.0, 100.0),
    }


class WinCounters:
    """Background poller caching GPU/NPU/VRAM counter values (Windows only)."""

    def __init__(self, interval: float = 2.0) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._data: dict = {"gpu": None, "vram": None, "npu": None}
        self._enabled = sys.platform.startswith("win")
        self._stop = threading.Event()
        if self._enabled:
            threading.Thread(target=self._loop, name="MemGraphCounters",
                             daemon=True).start()

    def _query(self) -> dict:
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
                capture_output=True, text=True, timeout=12,
                creationflags=0x08000000)  # CREATE_NO_WINDOW
            out = (proc.stdout or "").strip()
            if not out:
                return {"gpu": None, "vram": None, "npu": None}
            return parse_counters(json.loads(out))
        except Exception:
            return {"gpu": None, "vram": None, "npu": None}

    def _loop(self) -> None:
        while not self._stop.is_set():
            data = self._query()
            with self._lock:
                self._data = data
            self._stop.wait(self._interval)

    def get(self) -> dict:
        with self._lock:
            return dict(self._data)

    def stop(self) -> None:
        self._stop.set()
