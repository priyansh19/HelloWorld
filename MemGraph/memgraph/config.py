"""Configuration model, persistence and validation for MemGraph.

GUI/Qt-free so it can be unit-tested on any OS. Settings are stored as JSON in
the user's local app-data directory (``%LOCALAPPDATA%\\MemGraph\\config.json``
on Windows).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

from .metrics import ALL_METRIC_KEYS, DEFAULT_METRICS

CONFIG_FILENAME = "config.json"

REFRESH_MS_MIN = 250
REFRESH_MS_MAX = 10_000
HISTORY_MIN = 30
HISTORY_MAX = 3_600
OPACITY_MIN = 0.20
OPACITY_MAX = 1.00


def config_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        base = os.path.join(Path.home(), ".local", "share")
    return Path(base) / "MemGraph"


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


@dataclass
class Config:
    """All user-tunable settings. Every field has a safe default."""

    # Sampling
    refresh_ms: int = 1000
    history_seconds: int = 120

    # Which metrics to display, in order. First enabled = primary (big graph).
    enabled_metrics: list[str] = field(default_factory=lambda: list(DEFAULT_METRICS))
    process_name: str = "ollama.exe"

    # Appearance
    opacity: float = 0.96
    always_on_top: bool = True
    theme: str = "midnight"        # "midnight" | "graphite" | "light"
    accent: str = "auto"           # "auto" (level colour) | hex string
    snap_to_edges: bool = True
    show_sparkline: bool = True
    compact: bool = True           # tighter paddings/fonts

    # Display mode: "pinned" stays on screen; "peek" hides at the right edge as
    # a slim tab that slides out on click and auto-hides after peek_seconds;
    # "llama" is the taskbar buddy — a pixel llama whose gait/pack/mood show
    # CPU/RAM live, with the stat card one click away.
    mode: str = "llama"            # "pinned" | "peek" | "llama"
    peek_seconds: int = 120
    llama_x: int = -1              # remembered taskbar position
    llama_wander: bool = True      # walk back and forth across the screen
    llama_cross_seconds: int = 300  # time for one full screen crossing (~5 min)
    llama_scale: float = 1.5       # size multiplier for the buddy sprite

    # Colour thresholds (percent) for usage/memory metrics.
    threshold_amber: int = 70
    threshold_red: int = 88
    # Colour thresholds (°C) for temperature metrics.
    temp_amber: int = 75
    temp_red: int = 88

    # Window placement (remembered). -1 => not yet placed.
    pos_x: int = -1
    pos_y: int = -1
    width: int = 288
    height: int = 220

    # Behaviour
    autostart: bool = True
    start_hidden: bool = False

    # ------------------------------------------------------------------ #
    def clamp(self) -> "Config":
        self.refresh_ms = _clamp_int(self.refresh_ms, REFRESH_MS_MIN, REFRESH_MS_MAX, 1000)
        self.history_seconds = _clamp_int(self.history_seconds, HISTORY_MIN, HISTORY_MAX, 120)
        self.opacity = _clamp_float(self.opacity, OPACITY_MIN, OPACITY_MAX, 0.96)

        self.threshold_amber = _clamp_int(self.threshold_amber, 1, 99, 70)
        self.threshold_red = _clamp_int(self.threshold_red, 1, 100, 88)
        if self.threshold_red <= self.threshold_amber:
            self.threshold_red = min(100, self.threshold_amber + 1)

        self.temp_amber = _clamp_int(self.temp_amber, 20, 110, 75)
        self.temp_red = _clamp_int(self.temp_red, 21, 120, 88)
        if self.temp_red <= self.temp_amber:
            self.temp_red = min(120, self.temp_amber + 1)

        if self.theme not in ("midnight", "graphite", "light"):
            self.theme = "midnight"
        if self.mode not in ("pinned", "peek", "llama"):
            self.mode = "llama"
        self.peek_seconds = _clamp_int(self.peek_seconds, 10, 600, 120)
        self.llama_x = _clamp_int(self.llama_x, -1, 20000, -1)
        self.llama_cross_seconds = _clamp_int(self.llama_cross_seconds, 20, 3600, 300)
        self.llama_scale = _clamp_float(self.llama_scale, 0.8, 3.0, 1.5)

        self.width = _clamp_int(self.width, 220, 1200, 288)
        self.height = _clamp_int(self.height, 140, 800, 220)

        # Metrics: keep only known keys, preserve order, dedupe, never empty.
        seen: set[str] = set()
        cleaned: list[str] = []
        for k in (self.enabled_metrics or []):
            if k in ALL_METRIC_KEYS and k not in seen:
                seen.add(k)
                cleaned.append(k)
        self.enabled_metrics = cleaned or ["ram"]

        for b in ("always_on_top", "snap_to_edges", "autostart",
                  "start_hidden", "show_sparkline", "compact", "llama_wander"):
            setattr(self, b, bool(getattr(self, b)))
        self.process_name = (self.process_name or "").strip()
        return self

    @property
    def history_points(self) -> int:
        per_second = 1000.0 / self.refresh_ms
        return max(2, int(round(self.history_seconds * per_second)))

    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        data = dict(data or {})
        # Migrate legacy boolean flags -> enabled_metrics list.
        if "enabled_metrics" not in data and any(
                k in data for k in ("show_ram", "show_vram", "show_process")):
            legacy = []
            if data.get("show_ram", True):
                legacy.append("ram")
            if data.get("show_vram", True):
                legacy.append("vram")
            if data.get("show_process", True):
                legacy.append("process")
            data["enabled_metrics"] = legacy or ["ram"]

        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered).clamp()


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        return max(lo, min(hi, int(value)))
    except (TypeError, ValueError):
        return default


def _clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        return max(lo, min(hi, float(value)))
    except (TypeError, ValueError):
        return default


def load_config(path: Path | None = None) -> Config:
    p = path or config_path()
    try:
        with open(p, "r", encoding="utf-8") as fh:
            return Config.from_dict(json.load(fh))
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        return Config()


def save_config(cfg: Config, path: Path | None = None) -> Path:
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg.clamp().to_dict(), fh, indent=2)
    os.replace(tmp, p)
    return p
