"""Metric definitions, sampling and interpretation.

Design goals:
* One generic :class:`Metric` model covers usage (%), memory (bytes) and
  temperature (°C) so the UI can render any mix the user enables.
* Pure interpretation logic (``format_bytes``, ``severity``, ``color_for_level``,
  ``Metric`` helpers) has no external dependency and is unit-tested off-Windows.
* Sampling (``MetricsSampler``) wraps ``psutil`` (RAM/CPU/process/temps),
  ``pynvml`` (NVIDIA VRAM/GPU util/GPU temp) and PDH perf-counters (NPU / GPU
  engine) with lazy imports and graceful degradation — anything unreadable
  reports ``available=False`` and shows as ``n/a``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Metric registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    kind: str          # "bytes" | "percent" | "temp"
    description: str


METRIC_DEFS: tuple[MetricDef, ...] = (
    MetricDef("ram", "RAM", "bytes", "System memory usage"),
    MetricDef("cpu", "CPU", "percent", "Processor utilisation"),
    MetricDef("vram", "VRAM", "bytes", "NVIDIA GPU memory usage"),
    MetricDef("gpu", "GPU", "percent", "GPU utilisation"),
    MetricDef("npu", "NPU", "percent", "NPU / AI-accelerator utilisation"),
    MetricDef("process", "Process", "bytes", "Memory of a chosen process"),
    MetricDef("cpu_temp", "CPU Temp", "temp", "CPU temperature (if sensed)"),
    MetricDef("gpu_temp", "GPU Temp", "temp", "GPU temperature (NVIDIA)"),
    MetricDef("mem_temp", "Mem Temp", "temp", "Memory temperature (if sensed)"),
)

METRIC_BY_KEY = {d.key: d for d in METRIC_DEFS}
ALL_METRIC_KEYS = [d.key for d in METRIC_DEFS]
DEFAULT_METRICS = ["ram", "cpu", "vram", "process"]

Level = str  # "ok" | "warn" | "crit"

_COLORS = {
    "ok": "#3ddc84",    # green
    "warn": "#ffb020",  # amber
    "crit": "#ff5470",  # red/pink
}


# ---------------------------------------------------------------------------
# Pure logic (unit-tested)
# ---------------------------------------------------------------------------

def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def format_bytes(num: float) -> str:
    """Human-readable size, e.g. ``format_bytes(1610612736) == '1.5 GB'``."""
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0 or unit == "TB":
            return f"{int(num)} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"  # pragma: no cover


def percent(used: float, total: float) -> float:
    """Safe used/total percentage, clamped 0-100, 0 when total <= 0."""
    if not total or total <= 0:
        return 0.0
    return _clamp((used / total) * 100.0, 0.0, 100.0)


def severity(value: float, amber: float, red: float) -> Level:
    """Map a value to a severity level using two ascending thresholds."""
    if value >= red:
        return "crit"
    if value >= amber:
        return "warn"
    return "ok"


def color_for_level(level: Level) -> str:
    return _COLORS.get(level, _COLORS["ok"])


@dataclass
class Metric:
    """A single metric reading at one point in time (any kind)."""

    key: str
    label: str
    kind: str               # "bytes" | "percent" | "temp"
    value: float = 0.0      # bytes: used; percent: 0-100; temp: °C
    total: float = 0.0      # bytes: total; else unused
    available: bool = True
    detail: str = ""        # muted secondary text (e.g. process name)

    @property
    def pct(self) -> float:
        """A 0-100 figure suitable for the graph/bars for any kind."""
        if self.kind == "bytes":
            return percent(self.value, self.total)
        return _clamp(self.value, 0.0, 100.0)

    def graph_value(self) -> float:
        return self.pct

    def level(self, amber: float, red: float,
              temp_amber: float, temp_red: float) -> Level:
        if not self.available:
            return "ok"
        if self.kind == "temp":
            return severity(self.value, temp_amber, temp_red)
        return severity(self.pct, amber, red)

    def value_text(self) -> str:
        """The bold headline value, e.g. '58%', '72°C', or 'n/a'."""
        if not self.available:
            return "n/a"
        if self.kind == "temp":
            return f"{self.value:.0f}°C"
        return f"{self.pct:.0f}%"

    def sub_text(self) -> str:
        """Muted secondary text, e.g. '18.3 / 31.4 GB' for memory metrics."""
        if not self.available:
            return self.detail
        if self.kind == "bytes":
            return f"{format_bytes(self.value)} / {format_bytes(self.total)}"
        return self.detail


# ---------------------------------------------------------------------------
# Sampling (runtime; libs imported lazily so tests don't need them)
# ---------------------------------------------------------------------------

class MetricsSampler:
    """Collects live metrics with graceful degradation across backends."""

    def __init__(self) -> None:
        self._psutil = None
        self._nvml = None
        self._nvml_ok = False
        self._nvml_handle = None
        self._npu = None            # PerfCounter | None
        self._gpu_engine = None     # PerfCounter fallback | None
        self._wtemps = None         # WinTemps | None (lazy)
        self._init_psutil()
        self._init_nvml()

    def _win_temps(self):
        """Lazily start the Windows temperature poller (no-op off Windows)."""
        if self._wtemps is None:
            from ._wintemp import WinTemps
            self._wtemps = WinTemps()
        return self._wtemps

    # -- backend init -------------------------------------------------- #
    def _init_psutil(self) -> None:
        try:
            import psutil  # type: ignore
            self._psutil = psutil
            # Prime cpu_percent so the first real reading isn't 0.0.
            psutil.cpu_percent(interval=None)
        except ImportError:
            self._psutil = None

    def _init_nvml(self) -> None:
        try:
            import pynvml  # type: ignore
            pynvml.nvmlInit()
            if pynvml.nvmlDeviceGetCount() > 0:
                self._nvml_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self._nvml = pynvml
                self._nvml_ok = True
        except Exception:
            self._nvml = None
            self._nvml_ok = False

    def _npu_counter(self):
        if self._npu is None:
            from ._perf import PerfCounter
            self._npu = PerfCounter(r"\NPU Engine(*)\Utilization Percentage")
        return self._npu

    def _gpu_engine_counter(self):
        if self._gpu_engine is None:
            from ._perf import PerfCounter
            self._gpu_engine = PerfCounter(
                r"\GPU Engine(*)\Utilization Percentage")
        return self._gpu_engine

    @property
    def gpu_available(self) -> bool:
        return self._nvml_ok

    def gpu_name(self) -> str:
        if not self._nvml_ok:
            return ""
        try:
            name = self._nvml.nvmlDeviceGetName(self._nvml_handle)
            return name.decode() if isinstance(name, bytes) else str(name)
        except Exception:
            return "NVIDIA GPU"

    # -- individual providers ------------------------------------------ #
    def ram(self) -> Metric:
        if not self._psutil:
            return Metric("ram", "RAM", "bytes", available=False)
        vm = self._psutil.virtual_memory()
        return Metric("ram", "RAM", "bytes", vm.used, vm.total)

    def cpu(self) -> Metric:
        if not self._psutil:
            return Metric("cpu", "CPU", "percent", available=False)
        pct = self._psutil.cpu_percent(interval=None)
        cores = self._psutil.cpu_count(logical=True) or 0
        return Metric("cpu", "CPU", "percent", pct, detail=f"{cores} threads")

    def vram(self) -> Metric:
        if not self._nvml_ok:
            return Metric("vram", "VRAM", "bytes", available=False,
                          detail="no NVIDIA GPU")
        try:
            info = self._nvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
            return Metric("vram", "VRAM", "bytes", info.used, info.total,
                          detail=self.gpu_name())
        except Exception:
            return Metric("vram", "VRAM", "bytes", available=False)

    def gpu(self) -> Metric:
        if self._nvml_ok:
            try:
                u = self._nvml.nvmlDeviceGetUtilizationRates(self._nvml_handle)
                return Metric("gpu", "GPU", "percent", float(u.gpu),
                              detail=self.gpu_name())
            except Exception:
                pass
        # Fallback: Windows GPU-engine perf counter (any vendor).
        val = self._gpu_engine_counter().value()
        if val is not None:
            return Metric("gpu", "GPU", "percent", val)
        return Metric("gpu", "GPU", "percent", available=False,
                      detail="no GPU counter")

    def npu(self) -> Metric:
        val = self._npu_counter().value()
        if val is not None:
            return Metric("npu", "NPU", "percent", val)
        return Metric("npu", "NPU", "percent", available=False,
                      detail="no NPU detected")

    def process(self, name: str) -> Metric:
        """Aggregate RSS of processes matching ``name`` (case-insensitive,
        tolerant of a missing ``.exe``). Percentage is of total system RAM."""
        if not self._psutil or not name:
            return Metric("process", "Process", "bytes", available=False,
                          detail=name or "not set")
        target = name.lower()
        base = target[:-4] if target.endswith(".exe") else target
        used, found = 0, False
        for proc in self._psutil.process_iter(["name", "memory_info"]):
            try:
                pname = (proc.info.get("name") or "").lower()
                pbase = pname[:-4] if pname.endswith(".exe") else pname
                if pbase == base:
                    mem = proc.info.get("memory_info")
                    if mem is not None:
                        used += mem.rss
                        found = True
            except Exception:
                continue
        total = self._psutil.virtual_memory().total
        return Metric("process", "Process", "bytes", used, total,
                      available=found,
                      detail=name if found else f"{name} (not running)")

    # -- temperatures --------------------------------------------------- #
    def _sensor_temp(self, *needles: str) -> Optional[float]:
        """Return a temperature (°C) from psutil sensors matching any needle."""
        if not self._psutil or not hasattr(self._psutil, "sensors_temperatures"):
            return None
        try:
            temps = self._psutil.sensors_temperatures()
        except Exception:
            return None
        if not temps:
            return None
        # Prefer a name/label matching a needle; else fall back to first entry.
        for name, entries in temps.items():
            if any(n in name.lower() for n in needles):
                for e in entries:
                    if e.current:
                        return float(e.current)
        if not needles:
            for entries in temps.values():
                for e in entries:
                    if e.current:
                        return float(e.current)
        return None

    def cpu_temp(self) -> Metric:
        t = self._sensor_temp("coretemp", "k10temp", "cpu", "acpitz", "zenpower")
        source = ""
        if t is None:
            wt = self._win_temps().get()
            t, source = wt.get("cpu"), wt.get("source", "")
        if t is None:
            return Metric("cpu_temp", "CPU Temp", "temp", available=False,
                          detail="no sensor")
        return Metric("cpu_temp", "CPU Temp", "temp", float(t), detail=source)

    def gpu_temp(self) -> Metric:
        if self._nvml_ok:
            try:
                t = self._nvml.nvmlDeviceGetTemperature(
                    self._nvml_handle, 0)  # 0 = NVML_TEMPERATURE_GPU
                return Metric("gpu_temp", "GPU Temp", "temp", float(t),
                              detail=self.gpu_name())
            except Exception:
                pass
        wt = self._win_temps().get()
        if wt.get("gpu") is not None:
            return Metric("gpu_temp", "GPU Temp", "temp", float(wt["gpu"]),
                          detail=wt.get("source", ""))
        return Metric("gpu_temp", "GPU Temp", "temp", available=False,
                      detail="no sensor")

    def mem_temp(self) -> Metric:
        t = self._sensor_temp("dimm", "spd", "mem", "ddr")
        source = ""
        if t is None:
            wt = self._win_temps().get()
            t, source = wt.get("mem"), wt.get("source", "")
        if t is None:
            return Metric("mem_temp", "Mem Temp", "temp", available=False,
                          detail="no sensor")
        return Metric("mem_temp", "Mem Temp", "temp", float(t), detail=source)

    # -- dispatch ------------------------------------------------------- #
    def read(self, key: str, process_name: str = "") -> Metric:
        if key == "ram":
            return self.ram()
        if key == "cpu":
            return self.cpu()
        if key == "vram":
            return self.vram()
        if key == "gpu":
            return self.gpu()
        if key == "npu":
            return self.npu()
        if key == "process":
            return self.process(process_name)
        if key == "cpu_temp":
            return self.cpu_temp()
        if key == "gpu_temp":
            return self.gpu_temp()
        if key == "mem_temp":
            return self.mem_temp()
        d = METRIC_BY_KEY.get(key)
        label = d.label if d else key
        kind = d.kind if d else "percent"
        return Metric(key, label, kind, available=False, detail="unknown")

    def sample(self, keys: list[str], process_name: str = "") -> list[Metric]:
        """Read every enabled metric, in order. First entry is the primary."""
        return [self.read(k, process_name) for k in keys]
