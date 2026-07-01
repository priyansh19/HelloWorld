"""Windows temperature sensing.

``psutil.sensors_temperatures()`` is not implemented on Windows, so temps need a
native path. In order of quality this module reads:

1. **LibreHardwareMonitor** — WMI namespace ``root\\LibreHardwareMonitor``
   (class ``Sensor``). Best coverage: CPU, GPU (any vendor), motherboard, memory.
2. **OpenHardwareMonitor** — WMI namespace ``root\\OpenHardwareMonitor``.
3. **ACPI thermal zone** — ``root\\WMI`` class ``MSAcpi_ThermalZoneTemperature``.
   No extra software required, but usually only exposes a single CPU/system zone.

Options 1-2 require the (free) tool to be running; option 3 is built into Windows.
Sensors are collected on a background thread (a PowerShell/CIM query is slow) and
cached, so the UI never blocks. Everything is guarded and Windows-only.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from typing import Optional

# One PowerShell pass tries LHM, then OHM, then the ACPI thermal zone, and emits
# a compact JSON blob we parse in Python.
_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
function T($ns) {
  Get-CimInstance -Namespace $ns -ClassName Sensor 2>$null |
    Where-Object { $_.SensorType -eq 'Temperature' -and $_.Value -ne $null } |
    ForEach-Object { [pscustomobject]@{ name=$_.Name; value=[double]$_.Value; parent=[string]$_.Parent } }
}
$sensors = @(T 'root/LibreHardwareMonitor')
$source = 'LibreHardwareMonitor'
if ($sensors.Count -eq 0) { $sensors = @(T 'root/OpenHardwareMonitor'); $source = 'OpenHardwareMonitor' }
$acpi = @()
$tz = Get-CimInstance -Namespace root/WMI -ClassName MSAcpi_ThermalZoneTemperature 2>$null
foreach ($z in $tz) { if ($z.CurrentTemperature) { $acpi += [double]$z.CurrentTemperature } }
[pscustomobject]@{ source=$source; sensors=@($sensors); acpi=@($acpi) } | ConvertTo-Json -Depth 5 -Compress
"""


def _as_list(v) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _classify(name: str, parent: str) -> str:
    """Bucket a sensor into 'cpu' | 'gpu' | 'mem' | '' using name/parent hints."""
    n, p = (name or "").lower(), (parent or "").lower()
    hay = n + " " + p
    if "gpu" in hay:
        return "gpu"
    if any(k in hay for k in ("dimm", "dram", "/ram", "memory")):
        return "mem"
    if any(k in hay for k in ("cpu", "core", "tctl", "tdie", "package", "processor")):
        return "cpu"
    return ""


def parse_temps(payload: dict) -> dict:
    """Pure mapping from the PowerShell payload to {cpu,gpu,mem,source}.

    Prefers a representative sensor per bucket (package/Tctl/Tdie for CPU,
    core/hot-spot for GPU) and otherwise the hottest reading in the bucket.
    Falls back to the ACPI thermal zone for CPU when nothing else is present.
    """
    result: dict[str, Optional[float]] = {"cpu": None, "gpu": None, "mem": None}
    source = ""
    buckets: dict[str, list[tuple[str, float]]] = {"cpu": [], "gpu": [], "mem": []}

    for s in _as_list((payload or {}).get("sensors")):
        try:
            name = str(s.get("name", ""))
            value = float(s.get("value"))
            parent = str(s.get("parent", ""))
        except (TypeError, ValueError, AttributeError):
            continue
        if value <= 0 or value > 150:  # ignore clearly bogus readings
            continue
        bucket = _classify(name, parent)
        if bucket:
            buckets[bucket].append((name.lower(), value))

    if any(buckets.values()):
        source = str((payload or {}).get("source") or "")

    _preferred = {
        "cpu": ("package", "tctl", "tdie", "cpu"),
        "gpu": ("core", "hot spot", "hotspot", "gpu"),
        "mem": ("dimm", "memory", "dram"),
    }
    for bucket, entries in buckets.items():
        if not entries:
            continue
        chosen = None
        for key in _preferred[bucket]:
            for nm, val in entries:
                if key in nm:
                    chosen = val
                    break
            if chosen is not None:
                break
        result[bucket] = chosen if chosen is not None else max(v for _, v in entries)

    # ACPI fallback for CPU (tenths of Kelvin -> °C).
    if result["cpu"] is None:
        acpi = _as_list((payload or {}).get("acpi"))
        vals = []
        for a in acpi:
            try:
                c = float(a) / 10.0 - 273.15
            except (TypeError, ValueError):
                continue
            if 0 < c < 150:
                vals.append(c)
        if vals:
            result["cpu"] = max(vals)
            if not source:
                source = "ACPI"

    result["source"] = source
    return result


class WinTemps:
    """Background poller that keeps the latest Windows temperatures cached."""

    def __init__(self, interval: float = 4.0) -> None:
        self._interval = interval
        self._lock = threading.Lock()
        self._data: dict = {"cpu": None, "gpu": None, "mem": None, "source": ""}
        self._enabled = sys.platform.startswith("win")
        self._stop = threading.Event()
        if self._enabled:
            t = threading.Thread(target=self._loop, name="MemGraphTemps",
                                 daemon=True)
            t.start()

    def _query(self) -> dict:
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000)  # CREATE_NO_WINDOW
            out = (proc.stdout or "").strip()
            if not out:
                return {"cpu": None, "gpu": None, "mem": None, "source": ""}
            return parse_temps(json.loads(out))
        except Exception:
            return {"cpu": None, "gpu": None, "mem": None, "source": ""}

    def _loop(self) -> None:
        while not self._stop.is_set():
            data = self._query()
            # Keep the last non-empty source but always publish latest values.
            with self._lock:
                self._data = data
            self._stop.wait(self._interval)

    def get(self) -> dict:
        with self._lock:
            return dict(self._data)

    @property
    def source(self) -> str:
        return self.get().get("source", "")

    def stop(self) -> None:
        self._stop.set()
