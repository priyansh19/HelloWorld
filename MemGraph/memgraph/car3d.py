"""The 3D-baked Mustang sprite: yaw ring + wheel-spin phases from a .glb bake.

``tools/render_glb.py`` renders the model into an atlas of frames indexed by
*(yaw, spin)* — yaw is the car's heading (0 == facing screen right, degrees
counter-clockwise), spin is the wheel-rotation phase. This module loads that
atlas and answers frame lookups for the buddy widget:

* while cruising, yaw sits at 0/180 and the widget advances the spin phase in
  proportion to road speed, so the wheels visibly turn — faster under load,
  exactly like the car is actually driving;
* at a screen edge the widget sweeps yaw through the ring, playing the drift
  turn-around with the wheels still rolling.

The atlas ships in ``memgraph/assets/car3d/`` (or a user override in
``%LOCALAPPDATA%\\MemGraph\\car3d``). Frames are WebP with alpha; a per-width
scaled cache keeps painting cheap.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6 import QtCore, QtGui

# Sizing units the widget multiplies by cfg.llama_scale; the height follows the
# atlas aspect at load time. 97 units puts the car around 390 px wide at the
# default scale (a 2.2x bump from the first cut, per user request).
SPRITE_W = 146
SPRITE_H = 60          # provisional until an atlas is loaded

FRAMES = 8             # legacy shim for frames_for_gait
IS_VECTOR = True       # tells the widget to use the image paint path

# Exhaust anchor in sizing units (recomputed from the atlas).
EXHAUST = (4, 25)

PALETTE: dict[str, str] = {}
PANIC_TINT = "#ff5470"
TINT_EXEMPT: set[str] = set()


def _asset_roots() -> list[Path]:
    roots = []
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        roots.append(Path(base) / "MemGraph" / "car3d")
    roots.append(Path(__file__).resolve().parent / "assets" / "car3d")
    return roots


class _Atlas:
    def __init__(self, root: Path, meta: dict) -> None:
        self.root = root
        self.frames: int = int(meta.get("frames", 24))
        self.spin_counts: dict[int, int] = {
            int(k): int(v) for k, v in (meta.get("spin_counts") or {}).items()}
        self.width: int = int(meta.get("width", 600))
        self.height: int = int(meta.get("height", 250))
        ex = meta.get("exhaust") or {}
        self.exhaust = (float(ex.get("x", 0.05)), float(ex.get("y", 0.84)))
        pat = meta.get("pattern") or "car_{yaw:02d}_{spin:02d}.webp"
        self.pattern = pat
        # raw frame images, loaded lazily; key (yaw_i, spin_i)
        self._raw: dict[tuple[int, int], QtGui.QImage] = {}
        # scaled cache; key (px_w, yaw_i, spin_i)
        self._scaled: dict[tuple[int, int, int], QtGui.QImage] = {}

    def spin_count(self, yaw_i: int) -> int:
        return max(1, self.spin_counts.get(yaw_i % self.frames, 1))

    def _load_raw(self, yaw_i: int, spin_i: int) -> QtGui.QImage | None:
        yaw_i %= self.frames
        spin_i %= self.spin_count(yaw_i)
        key = (yaw_i, spin_i)
        img = self._raw.get(key)
        if img is None:
            name = self.pattern.format(yaw=yaw_i, spin=spin_i)
            img = QtGui.QImage(str(self.root / name))
            if img.isNull():
                return None
            self._raw[key] = img
        return img

    def frame(self, px_w: int, yaw_i: int, spin_i: int) -> QtGui.QImage | None:
        yaw_i %= self.frames
        spin_i %= self.spin_count(yaw_i)
        key = (px_w, yaw_i, spin_i)
        img = self._scaled.get(key)
        if img is None:
            raw = self._load_raw(yaw_i, spin_i)
            if raw is None:
                return None
            out_w = px_w * 2                      # 2x for HiDPI crispness
            out_h = max(1, round(out_w * raw.height() / raw.width()))
            img = raw.scaled(out_w, out_h, QtCore.Qt.IgnoreAspectRatio,
                             QtCore.Qt.SmoothTransformation)
            img.setDevicePixelRatio(2.0)
            # keep the scaled cache bounded (a few sizes x 192 frames adds up)
            if len(self._scaled) > 640:
                self._scaled.clear()
            self._scaled[key] = img
        return img


_atlas: _Atlas | None = None
_atlas_checked = False


def atlas() -> _Atlas | None:
    global _atlas, _atlas_checked
    if not _atlas_checked:
        _atlas_checked = True
        for root in _asset_roots():
            meta_p = root / "atlas.json"
            if meta_p.is_file():
                try:
                    meta = json.loads(meta_p.read_text(encoding="utf-8"))
                    _atlas = _Atlas(root, meta)
                    _apply_atlas_dims(_atlas)
                    break
                except (OSError, ValueError):
                    continue
    return _atlas


def _apply_atlas_dims(a: _Atlas) -> None:
    """Derive sizing units + exhaust anchor from the atlas aspect."""
    global SPRITE_H, EXHAUST
    SPRITE_H = max(1, round(SPRITE_W * a.height / a.width))
    EXHAUST = (max(0, round(a.exhaust[0] * SPRITE_W)),
               max(0, round(a.exhaust[1] * SPRITE_H)))


def reload_asset() -> None:
    global _atlas, _atlas_checked
    _atlas = None
    _atlas_checked = False


def available() -> bool:
    return atlas() is not None


def sprite_units() -> tuple[int, int]:
    a = atlas()
    if a is not None:
        return SPRITE_W, max(1, round(SPRITE_W * a.height / a.width))
    return SPRITE_W, SPRITE_H


# ------------------------------------------------------------------ #
# Frame lookup used by the widget
# ------------------------------------------------------------------ #
def frame_image(px_w: int, yaw_deg: float, spin_phase: float) -> QtGui.QImage | None:
    """The atlas frame nearest ``yaw_deg`` at ``spin_phase`` in [0, 1)."""
    a = atlas()
    if a is None:
        return None
    yaw_i = round((yaw_deg % 360.0) / 360.0 * a.frames) % a.frames
    n = a.spin_count(yaw_i)
    spin_i = int(spin_phase % 1.0 * n) % n
    return a.frame(max(8, int(px_w)), yaw_i, spin_i)


# Legacy shims so LlamaBuddy can treat all sprite modules alike.
def warm(px_w: int, yaws: list[int] | None = None) -> None:
    """Pre-scale frames at ``px_w`` so painting never hits a scale on demand.

    With no ``yaws`` given, warms the two driving headings (all wheel phases);
    pass explicit indices to warm parts of the turn ring incrementally.
    """
    a = atlas()
    if a is None:
        return
    for yi in (yaws if yaws is not None else (0, a.frames // 2)):
        for si in range(a.spin_count(yi)):
            a.frame(px_w, yi, si)


def frames_for_gait(gait: str) -> list[int]:
    return list(range(FRAMES))


def apply_overlays(rows, shades: bool = False, blink: bool = False):
    return rows
