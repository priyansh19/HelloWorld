"""Memory sampling and interpretation.

Split into two layers so the interesting parts are testable off-Windows:

* **Pure logic** (``format_bytes``, ``level_for_percent``, ``color_for_level``,
  the ``MetricReading``/``Sample`` dataclasses) has no external dependency.
* **Sampling** (``MetricsSampler``) wraps ``psutil`` (RAM + process) and
  ``pynvml`` (NVIDIA VRAM) with lazy imports and graceful degradation, so a
  machine without a GPU, or without those libraries, still runs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Pure logic (unit-tested)
# ---------------------------------------------------------------------------

Level = str  # "ok" | "warn" | "crit"

_COLORS = {
    "ok": "#38c172",    # green
    "warn": "#f6a609",  # amber
    "crit": "#e3342f",  # red
}


def format_bytes(num: float) -> str:
    """Human-readable size, e.g. ``format_bytes(1610612736) == '1.5 GB'``."""
    num = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num) < 1024.0 or unit == "TB":
            if unit == "B":
                return f"{int(num)} {unit}"
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} TB"  # pragma: no cover - unreachable


def percent(used: float, total: float) -> float:
    """Safe used/total percentage, clamped to 0-100, 0 when total is 0."""
    if not total or total <= 0:
        return 0.0
    return max(0.0, min(100.0, (used / total) * 100.0))


def level_for_percent(pct: float, amber: int, red: int) -> Level:
    """Map a percentage to a severity level using the configured thresholds."""
    if pct >= red:
        return "crit"
    if pct >= amber:
        return "warn"
    return "ok"


def color_for_level(level: Level) -> str:
    return _COLORS.get(level, _COLORS["ok"])


@dataclass
class MetricReading:
    """A single metric (RAM, VRAM or a process) at one point in time."""

    key: str            # "ram" | "vram" | "process"
    label: str          # human label shown in the widget
    used_bytes: float
    total_bytes: float
    available: bool = True   # False -> show a muted "n/a" row
    detail: str = ""         # optional extra text (e.g. process name)

    @property
    def percent(self) -> float:
        return percent(self.used_bytes, self.total_bytes)

    def level(self, amber: int, red: int) -> Level:
        return level_for_percent(self.percent, amber, red)

    def readout(self) -> str:
        """e.g. ``'6.2 / 16.0 GB'`` or ``'n/a'`` when unavailable."""
        if not self.available:
            return "n/a"
        if self.total_bytes > 0:
            return f"{format_bytes(self.used_bytes)} / {format_bytes(self.total_bytes)}"
        return format_bytes(self.used_bytes)


@dataclass
class Sample:
    """A full snapshot: the primary metric plus any secondary rows."""

    primary: MetricReading
    secondary: list[MetricReading] = field(default_factory=list)

    def all_readings(self) -> list[MetricReading]:
        return [self.primary, *self.secondary]


# ---------------------------------------------------------------------------
# Sampling (Windows/runtime; imported lazily so tests don't need the libs)
# ---------------------------------------------------------------------------


class MetricsSampler:
    """Collects live memory metrics with graceful degradation.

    Construct once and call :meth:`sample` on each tick. GPU support is probed
    once and cached; if ``pynvml`` is missing or no NVIDIA GPU is present, VRAM
    simply reports as unavailable instead of raising.
    """

    def __init__(self) -> None:
        self._psutil = None
        self._nvml = None
        self._nvml_ok = False
        self._nvml_handle = None
        self._init_psutil()
        self._init_nvml()

    # -- backend init -------------------------------------------------- #
    def _init_psutil(self) -> None:
        try:
            import psutil  # type: ignore

            self._psutil = psutil
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
            # No GPU, no driver, or library missing -> VRAM disabled.
            self._nvml = None
            self._nvml_ok = False

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

    # -- individual metrics -------------------------------------------- #
    def ram(self) -> MetricReading:
        if not self._psutil:
            return MetricReading("ram", "RAM", 0, 0, available=False)
        vm = self._psutil.virtual_memory()
        return MetricReading("ram", "RAM", vm.used, vm.total, available=True)

    def vram(self) -> MetricReading:
        if not self._nvml_ok:
            return MetricReading("vram", "VRAM", 0, 0, available=False,
                                 detail="no NVIDIA GPU")
        try:
            info = self._nvml.nvmlDeviceGetMemoryInfo(self._nvml_handle)
            return MetricReading("vram", "VRAM", info.used, info.total,
                                 available=True, detail=self.gpu_name())
        except Exception:
            return MetricReading("vram", "VRAM", 0, 0, available=False)

    def process(self, name: str) -> MetricReading:
        """Aggregate RSS of all processes whose name matches ``name``.

        Matching is case-insensitive and tolerant of a missing ``.exe`` so
        "ollama" and "ollama.exe" both work. Total is system RAM, giving a
        meaningful percentage of the machine consumed by the LLM runtime.
        """
        label = "Process"
        if not self._psutil or not name:
            return MetricReading("process", label, 0, 0, available=False,
                                 detail=name or "not set")

        target = name.lower()
        target_base = target[:-4] if target.endswith(".exe") else target
        used = 0
        found = False
        for proc in self._psutil.process_iter(["name", "memory_info"]):
            try:
                pname = (proc.info.get("name") or "").lower()
                pbase = pname[:-4] if pname.endswith(".exe") else pname
                if pbase == target_base:
                    mem = proc.info.get("memory_info")
                    if mem is not None:
                        used += mem.rss
                        found = True
            except Exception:
                # Process died mid-iteration / access denied -> skip.
                continue

        total = self._psutil.virtual_memory().total
        return MetricReading(
            "process", label, used, total,
            available=found, detail=name if found else f"{name} (not running)",
        )

    # -- full snapshot -------------------------------------------------- #
    def sample(self, show_ram: bool, show_vram: bool,
               show_process: bool, process_name: str) -> Optional[Sample]:
        """Return a :class:`Sample`. The primary metric is the first enabled
        one (RAM > VRAM > process); secondary rows follow. Returns ``None`` if
        nothing is enabled."""
        readings: list[MetricReading] = []
        if show_ram:
            readings.append(self.ram())
        if show_vram:
            readings.append(self.vram())
        if show_process:
            readings.append(self.process(process_name))

        if not readings:
            return None
        return Sample(primary=readings[0], secondary=readings[1:])
