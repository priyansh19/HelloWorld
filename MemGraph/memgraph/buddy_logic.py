"""Pure logic for the taskbar buddy: a pixel tortoise, animation and moods.

Qt-free so the buddy's personality is unit-testable. The tortoise sprite is
generated procedurally (smooth domed shell + scute pattern + head/legs/tail) at
import time into character grids the widget rasterises with QPainter — higher
resolution than a hand-drawn grid, so the silhouette clearly reads as a tortoise.

Palette legend:
``G`` shell · ``g`` shell highlight · ``s`` shell pattern/outline · ``h`` skin ·
``k`` foot/beak · ``o`` eye · ``S`` sunglasses · ``W`` lens glint · ``.`` clear
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PALETTE = {
    "G": "#6ea25a", "g": "#8dc271", "s": "#3f6a34",
    "h": "#b49a63", "k": "#7c6438", "o": "#20232a",
    "S": "#14161c", "W": "#9fd8ff",
}

PANIC_TINT = "#ff5470"
TINT_EXEMPT = set("SoWk")   # eye/beak/shades keep their colour under panic tint

_W, _H = 54, 34


def _build(phase: int) -> list[str]:
    """Generate one tortoise frame; ``phase`` shuffles the legs for walking."""
    g = [["."] * _W for _ in range(_H)]

    def put(x, y, ch):
        if 0 <= x < _W and 0 <= y < _H:
            g[y][x] = ch

    cx, cy, rx, ry = 24.0, 19.0, 19.0, 14.0
    for y in range(_H):
        for x in range(_W):
            dx, dy = (x - cx) / rx, (y - cy) / ry
            if dx * dx + dy * dy <= 1.0 and y <= cy + 2:
                g[y][x] = "G"

    def leg(x0):
        for y in range(21, 31):
            for x in range(x0, x0 + 6):
                if g[y][x] == ".":
                    put(x, y, "h")
        for x in range(x0, x0 + 6):
            put(x, 30, "k")
            put(x, 31, "k")
        put(x0 + 1, 32, "k")
        put(x0 + 4, 32, "k")

    leg(8 + phase)
    leg(20 - phase)
    leg(34 + phase)
    leg(43 - phase)

    for y in range(17, 24):          # neck
        for x in range(36, 45):
            if g[y][x] == ".":
                put(x, y, "h")
    hx, hy, hrx, hry = 47.0, 19.0, 7.0, 6.0
    for y in range(_H):              # head
        for x in range(_W):
            dx, dy = (x - hx) / hrx, (y - hy) / hry
            if dx * dx + dy * dy <= 1.0:
                put(x, y, "h")
    put(49, 16, "o")
    put(50, 16, "o")
    put(53, 20, "k")                 # beak

    for i, y in enumerate(range(18, 23)):   # tail
        for x in range(3, 3 + (5 - i)):
            if g[y][x] == ".":
                put(x, y, "h")

    src = [row[:] for row in g]      # shell outline
    for y in range(_H):
        for x in range(_W):
            if src[y][x] == "G" and any(
                    not (0 <= x + ox < _W and 0 <= y + oy < _H)
                    or src[y + oy][x + ox] == "."
                    for ox, oy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                g[y][x] = "s"

    scx, scy, scrx, scry = 24.0, 15.0, 7.0, 4.5    # central scute ring
    for y in range(_H):
        for x in range(_W):
            if g[y][x] == "G":
                dx, dy = (x - scx) / scrx, (y - scy) / scry
                if 0.85 <= dx * dx + dy * dy <= 1.15:
                    g[y][x] = "s"
    for ang in (-62, -33, 0, 33, 62):              # scute dividers
        a = math.radians(ang)
        for r in range(5, 20):
            x = int(round(cx + r * math.sin(a)))
            y = int(round(cy - r * math.cos(a) * 0.72 - 2))
            if 0 <= x < _W and 0 <= y < _H and g[y][x] == "G":
                g[y][x] = "s"

    for x in range(_W):                            # top highlight
        for y in range(_H):
            if g[y][x] == "G":
                if y > 2 and g[y - 1][x] == ".":
                    g[y][x] = "g"
                break

    return ["".join(r) for r in g]


WALK_FRAMES = [_build(0), _build(1)]
GALLOP_FRAMES = [_build(2), _build(0), _build(1)]
SPRITE_H = len(WALK_FRAMES[0])
SPRITE_W = len(WALK_FRAMES[0][0])


def frames_for_gait(gait: str) -> list[list[str]]:
    return GALLOP_FRAMES if gait == "gallop" else WALK_FRAMES


def _find_eye(rows: list[str]) -> tuple[int, int] | None:
    for r, row in enumerate(rows):
        c = row.find("o")
        if c != -1:
            return r, c
    return None


def apply_overlays(rows: list[str], shades: bool = False,
                   blink: bool = False) -> list[str]:
    """Stamp sunglasses / blink onto a copy of the frame."""
    rows = list(rows)
    eye = _find_eye(rows)
    if eye is None:
        return rows
    r, c = eye
    if shades:
        row = rows[r]
        seg = "SSSW"
        lo = max(0, c - 2)
        rows[r] = row[:lo] + seg[:len(row) - lo] + row[lo + len(seg):]
    elif blink and c > 0:
        rows[r] = rows[r][:c] + rows[r][c - 1] + rows[r][c + 1:]
    return rows


@dataclass(frozen=True)
class Mood:
    gait: str            # "idle" | "walk" | "gallop"
    pack: str            # kept for compatibility (unused visually)
    shades: bool         # tracked LLM process is running
    panic: bool          # RAM past the red threshold
    frame_ms: int        # animation frame interval

    @property
    def wander_ok(self) -> bool:
        return self.gait != "gallop" and not self.panic


def mood_for(cpu_pct: float, ram_pct: float, amber: float, red: float,
             model_loaded: bool) -> Mood:
    """Map live metrics to behaviour. CPU sets the gait (leg-shuffle speed); RAM
    past red triggers panic; a running tracked process puts sunglasses on.
    Traversal *speed* is driven by RAM in the widget itself."""
    panic = ram_pct >= red
    if panic:
        gait = "gallop"
    elif cpu_pct < 12:
        gait = "idle"
    elif cpu_pct < 50:
        gait = "walk"
    else:
        gait = "gallop"
    pack = "full" if ram_pct >= amber else "normal"
    if gait == "idle":
        frame_ms = 340
    elif gait == "walk":
        frame_ms = int(220 - 1.2 * cpu_pct)
    else:
        frame_ms = max(60, int(130 - 0.7 * cpu_pct))
    return Mood(gait=gait, pack=pack, shades=model_loaded,
                panic=panic, frame_ms=frame_ms)
