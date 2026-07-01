"""Configuration model, persistence and validation for MemGraph.

This module is deliberately free of any GUI/Qt or platform dependency so it can
be unit-tested on any OS. Settings are stored as JSON under the user's local
app-data directory (``%LOCALAPPDATA%\\MemGraph\\config.json`` on Windows).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

CONFIG_FILENAME = "config.json"

# Sane bounds so a hand-edited or corrupt config can never make the widget
# unusable (e.g. a 0ms refresh that pins a CPU core).
REFRESH_MS_MIN = 250
REFRESH_MS_MAX = 10_000
HISTORY_MIN = 30
HISTORY_MAX = 3_600
OPACITY_MIN = 0.20
OPACITY_MAX = 1.00


def config_dir() -> Path:
    """Return the per-user directory where MemGraph stores its config.

    Uses ``LOCALAPPDATA`` on Windows and falls back to an XDG-style path
    elsewhere so the module is importable and testable off-Windows.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if not base:
        base = os.path.join(Path.home(), ".local", "share")
    return Path(base) / "MemGraph"


def config_path() -> Path:
    return config_dir() / CONFIG_FILENAME


@dataclass
class Config:
    """All user-tunable settings for the widget.

    Every field has a safe default so a fresh install works with no config
    file present.
    """

    # Sampling
    refresh_ms: int = 1000
    history_seconds: int = 120

    # Which metrics to display
    show_ram: bool = True
    show_vram: bool = True
    show_process: bool = True
    process_name: str = "ollama.exe"

    # Appearance
    opacity: float = 0.92
    always_on_top: bool = True
    theme: str = "dark"  # "dark" | "light"
    snap_to_edges: bool = True

    # Color thresholds (percent). At/above amber -> amber, at/above red -> red.
    threshold_amber: int = 70
    threshold_red: int = 88

    # Window placement (remembered across restarts). -1 means "not yet placed".
    pos_x: int = -1
    pos_y: int = -1
    width: int = 300
    height: int = 180

    # Behaviour
    autostart: bool = True
    start_hidden: bool = False

    # ------------------------------------------------------------------ #
    # Validation / normalisation
    # ------------------------------------------------------------------ #
    def clamp(self) -> "Config":
        """Coerce every field into its valid range/type. Returns self."""
        self.refresh_ms = _clamp_int(self.refresh_ms, REFRESH_MS_MIN, REFRESH_MS_MAX, 1000)
        self.history_seconds = _clamp_int(self.history_seconds, HISTORY_MIN, HISTORY_MAX, 120)
        self.opacity = _clamp_float(self.opacity, OPACITY_MIN, OPACITY_MAX, 0.92)

        self.threshold_amber = _clamp_int(self.threshold_amber, 1, 99, 70)
        self.threshold_red = _clamp_int(self.threshold_red, 1, 100, 88)
        # Red must sit above amber to keep the color ramp monotonic.
        if self.threshold_red <= self.threshold_amber:
            self.threshold_red = min(100, self.threshold_amber + 1)

        if self.theme not in ("dark", "light"):
            self.theme = "dark"

        self.width = _clamp_int(self.width, 200, 1200, 300)
        self.height = _clamp_int(self.height, 120, 800, 180)

        self.show_ram = bool(self.show_ram)
        self.show_vram = bool(self.show_vram)
        self.show_process = bool(self.show_process)
        self.always_on_top = bool(self.always_on_top)
        self.snap_to_edges = bool(self.snap_to_edges)
        self.autostart = bool(self.autostart)
        self.start_hidden = bool(self.start_hidden)
        self.process_name = (self.process_name or "").strip()
        return self

    @property
    def history_points(self) -> int:
        """Number of samples retained for the graph at the current settings."""
        per_second = 1000.0 / self.refresh_ms
        return max(2, int(round(self.history_seconds * per_second)))

    # ------------------------------------------------------------------ #
    # Serialisation
    # ------------------------------------------------------------------ #
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        """Build a Config from a dict, ignoring unknown keys and filling in
        missing ones with defaults (forward/backward compatible)."""
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in (data or {}).items() if k in known}
        return cls(**filtered).clamp()


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def _clamp_float(value: Any, lo: float, hi: float, default: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, v))


def load_config(path: Path | None = None) -> Config:
    """Load config from disk, returning defaults if it is missing or corrupt.

    A corrupt file is never fatal: we log-and-default so the widget always
    starts.
    """
    p = path or config_path()
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return Config.from_dict(data)
    except (FileNotFoundError, json.JSONDecodeError, OSError, TypeError):
        return Config()


def save_config(cfg: Config, path: Path | None = None) -> Path:
    """Persist config atomically (write to a temp file, then replace)."""
    p = path or config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg.clamp().to_dict(), fh, indent=2)
    os.replace(tmp, p)
    return p
