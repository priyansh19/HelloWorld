"""Runtime for a baked 3D animal buddy — a walk-cycle atlas from a rigged .glb.

``tools/render_animal.py`` bakes an animated animal (the Fox) into transparent
WebP frames: one row per animation clip (Walk, Run) sampled across the cycle,
all cropped to a shared box so nothing jitters. This module loads that atlas
and serves scaled frames to the buddy widget:

* the animal walks the taskbar like the old tortoise — the widget advances the
  Walk cycle in proportion to travel speed, mirroring the frame to face left;
* when RAM runs hot it switches to the Run clip and moves faster.

Frames are looked up per (width, clip, frame) and cached at 2x display size for
HiDPI. If the atlas is absent (a source build with no baked assets) the buddy
falls back to the pixel tortoise in :mod:`~memgraph.buddy_logic`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6 import QtCore, QtGui

# Sizing units the widget multiplies by cfg.llama_scale. Height follows the
# atlas aspect at load; ~66 keeps the fox a friendly taskbar size.
SPRITE_W = 66
SPRITE_H = 40           # provisional until an atlas is loaded

# Baked clip names. The RAM-band behaviour lives in fox_logic.FoxDriver; these
# just name the clips this atlas is expected to carry.
WALK_CLIP = "Walk"
RUN_CLIP = "Run"
SLEEP_CLIP = "Survey"    # gentle idle used while the fox is curled up asleep


def _asset_roots() -> list[Path]:
    roots = []
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        roots.append(Path(base) / "MemGraph" / "fox")
    roots.append(Path(__file__).resolve().parent / "assets" / "fox")
    return roots


class _Atlas:
    def __init__(self, root: Path, meta: dict) -> None:
        self.root = root
        self.clips: dict[str, int] = {str(k): int(v)
                                      for k, v in (meta.get("clips") or {}).items()}
        self.pattern = meta.get("pattern") or "{clip}_{frame:02d}.webp"
        self._raw: dict[tuple[str, int], QtGui.QImage] = {}
        self._scaled: dict[tuple[int, str, int], QtGui.QImage] = {}
        self._aspect = 1.0
        first = self._load_raw(next(iter(self.clips), WALK_CLIP), 0)
        if first is not None and first.height():
            self._aspect = first.width() / first.height()

    def frame_count(self, clip: str) -> int:
        return max(1, self.clips.get(clip, 1))

    def has(self, clip: str) -> bool:
        return clip in self.clips

    def _load_raw(self, clip: str, i: int) -> QtGui.QImage | None:
        n = self.frame_count(clip)
        key = (clip, i % n)
        img = self._raw.get(key)
        if img is None:
            name = self.pattern.format(clip=clip, frame=i % n)
            img = QtGui.QImage(str(self.root / name))
            if img.isNull():
                return None
            self._raw[key] = img
        return img

    def frame(self, px_w: int, clip: str, i: int) -> QtGui.QImage | None:
        n = self.frame_count(clip)
        key = (px_w, clip, i % n)
        img = self._scaled.get(key)
        if img is None:
            raw = self._load_raw(clip, i)
            if raw is None:
                return None
            out_w = px_w * 2                      # 2x for HiDPI crispness
            out_h = max(1, round(out_w * raw.height() / raw.width()))
            img = raw.scaled(out_w, out_h, QtCore.Qt.IgnoreAspectRatio,
                             QtCore.Qt.SmoothTransformation)
            img.setDevicePixelRatio(2.0)
            if len(self._scaled) > 400:
                self._scaled.clear()
            self._scaled[key] = img
        return img


_atlas: _Atlas | None = None
_checked = False


def atlas() -> _Atlas | None:
    global _atlas, _checked
    if not _checked:
        _checked = True
        for root in _asset_roots():
            meta_p = root / "atlas.json"
            if meta_p.is_file():
                try:
                    meta = json.loads(meta_p.read_text(encoding="utf-8"))
                    a = _Atlas(root, meta)
                    if a.clips and a._load_raw(next(iter(a.clips)), 0) is not None:
                        _atlas = a
                        _apply_dims(a)
                        break
                except (OSError, ValueError):
                    continue
    return _atlas


def _apply_dims(a: _Atlas) -> None:
    global SPRITE_H
    SPRITE_H = max(1, round(SPRITE_W / max(0.01, a._aspect)))


def available() -> bool:
    return atlas() is not None


def reload_asset() -> None:
    global _atlas, _checked
    _atlas = None
    _checked = False


def sprite_units() -> tuple[int, int]:
    a = atlas()
    if a is not None:
        return SPRITE_W, max(1, round(SPRITE_W / max(0.01, a._aspect)))
    return SPRITE_W, SPRITE_H


def resolve_clip(clip: str) -> str:
    """Map a requested clip to one this atlas actually has (Walk fallback)."""
    a = atlas()
    if a is not None and a.has(clip):
        return clip
    return WALK_CLIP


def frame_image(px_w: int, clip: str, phase: float) -> QtGui.QImage | None:
    """The atlas frame for ``clip`` at ``phase`` in [0, 1)."""
    a = atlas()
    if a is None:
        return None
    n = a.frame_count(clip if a.has(clip) else WALK_CLIP)
    i = int(phase % 1.0 * n) % n
    return a.frame(max(8, int(px_w)), clip if a.has(clip) else WALK_CLIP, i)


# Legacy shims so LlamaBuddy can treat every sprite module alike.
IS_ANIMAL = True
FRAMES = 8


def frames_for_gait(gait: str) -> list[int]:
    return list(range(FRAMES))


def apply_overlays(rows, shades: bool = False, blink: bool = False):
    return rows
