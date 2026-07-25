"""Pure logic for the taskbar buddy: a pixel tortoise with a real walk cycle.

Qt-free so the buddy's personality is unit-testable. The tortoise is generated
procedurally (smooth domed shell + scute pattern + head/eye/beak + four legs)
into an 8-frame walk cycle where the legs lift, swing forward and plant — the
widget just rasterises the character grids with QPainter (no image assets).

Palette legend:
``G`` shell · ``g`` shell highlight · ``s`` shell pattern/outline · ``h`` near
skin · ``f`` far-leg skin · ``k`` foot/beak · ``e`` eye-white · ``o`` pupil ·
``S`` sunglasses · ``W`` lens glint · ``.`` transparent
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PALETTE = {
    "G": "#5f9e4f", "g": "#93d071", "s": "#375e2c",
    "h": "#c7ab72", "f": "#6f5730", "k": "#8a6f3e",
    "e": "#f4f0e6", "o": "#1c1f26", "S": "#14161c", "W": "#9fd8ff",
}

PANIC_TINT = "#ff5470"
TINT_EXEMPT = set("SoWke")   # eye/beak/shades keep colour under the panic tint

_W, _H = 58, 36
_FRAMES = 8


def _leg_phase(p: float) -> tuple[float, float]:
    """(lift 0..1, dx) for a leg at cycle phase ``p`` in [0,1).

    Stance (foot planted) slides the foot backward; swing lifts it and carries
    it forward — a natural walking gait.
    """
    if p < 0.62:
        return 0.0, 2.4 * (1 - 2 * (p / 0.62))
    q = (p - 0.62) / 0.38
    return math.sin(q * math.pi), 2.4 * (2 * q - 1)


def _build(t: int) -> list[str]:
    g = [["."] * _W for _ in range(_H)]

    def put(x, y, ch):
        if 0 <= x < _W and 0 <= y < _H:
            g[y][x] = ch

    cx, cy, rx, ry = 25.0, 20.0, 20.0, 15.0

    # Legs first, so the shell draws over their tops (a lifted leg tucks under).
    # (base x, phase offset, near/far) — diagonal gait via the 0.0/0.5 offsets.
    for x0, off, near in ((10, 0.0, False), (20, 0.5, True),
                          (34, 0.5, True), (45, 0.0, False)):
        lift, dx = _leg_phase((t / _FRAMES + off) % 1.0)
        x = x0 + int(round(dx))
        bottom = 32 - int(round(lift * 6))
        skin = "h" if near else "f"
        foot = "k" if near else "f"
        for yy in range(20, bottom):
            for xx in range(x, x + 5):
                put(xx, yy, skin)
        for xx in range(x, x + 5):
            put(xx, bottom, foot)
        for tx in (x, x + 2, x + 4):
            put(tx, bottom + 1, foot)

    for y in range(_H):                      # shell dome
        for x in range(_W):
            if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0 and y <= cy + 3:
                g[y][x] = "G"

    for y in range(18, 25):                  # neck
        for x in range(38, 47):
            if g[y][x] == ".":
                put(x, y, "h")
    hx, hy, hrx, hry = 49.0, 20.0, 7.5, 6.5  # head
    for y in range(_H):
        for x in range(_W):
            if ((x - hx) / hrx) ** 2 + ((y - hy) / hry) ** 2 <= 1.0:
                put(x, y, "h")
    put(51, 17, "e")
    put(52, 17, "o")
    put(55, 21, "k")                         # beak

    for i, y in enumerate(range(19, 24)):    # tail
        for x in range(3, 3 + (5 - i)):
            if g[y][x] == ".":
                put(x, y, "h")

    src = [r[:] for r in g]                  # shell outline
    for y in range(_H):
        for x in range(_W):
            if src[y][x] == "G" and any(
                    not (0 <= x + a < _W and 0 <= y + b < _H)
                    or src[y + b][x + a] == "."
                    for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                g[y][x] = "s"

    for y in range(_H):                      # central scute plate
        for x in range(_W):
            if g[y][x] == "G":
                d = ((x - cx) / 6.5) ** 2 + ((y - (cy - 4)) / 4.0) ** 2
                if 0.8 <= d <= 1.2:
                    g[y][x] = "s"
    for ang in (-58, -30, 0, 30, 58):        # scute dividers
        a = math.radians(ang)
        for r in range(6, 21):
            x = int(round(cx + r * math.sin(a)))
            y = int(round((cy - 2) - r * math.cos(a) * 0.74))
            if 0 <= x < _W and 0 <= y < _H and g[y][x] == "G":
                g[y][x] = "s"

    for x in range(_W):                      # top highlight (dome volume)
        col = [y for y in range(_H) if g[y][x] in ("G", "s")]
        if col:
            top = min(col)
            if g[top][x] == "G":
                g[top][x] = "g"
            if top + 1 < _H and g[top + 1][x] == "G":
                g[top + 1][x] = "g"

    return ["".join(r) for r in g]


WALK_FRAMES = [_build(t) for t in range(_FRAMES)]
GALLOP_FRAMES = WALK_FRAMES            # tortoises don't gallop; just steps faster
SPRITE_H = len(WALK_FRAMES[0])
SPRITE_W = len(WALK_FRAMES[0][0])


def frames_for_gait(gait: str) -> list[list[str]]:
    return WALK_FRAMES


def _find_eye(rows: list[str]) -> tuple[int, int] | None:
    for r, row in enumerate(rows):
        c = row.find("o")
        if c != -1:
            return r, c
    return None


def apply_overlays(rows: list[str], shades: bool = False,
                   blink: bool = False) -> list[str]:
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
        rows[r] = rows[r][:c] + "e" + rows[r][c + 1:]
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
    """CPU sets leg-shuffle speed via frame_ms; RAM past red = panic; a running
    tracked process puts sunglasses on. Traversal speed is RAM-driven in the
    widget."""
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
        frame_ms = 200
    elif gait == "walk":
        frame_ms = int(150 - 1.0 * cpu_pct)
    else:
        frame_ms = max(55, int(110 - 0.5 * cpu_pct))
    return Mood(gait=gait, pack=pack, shades=model_loaded,
                panic=panic, frame_ms=max(45, frame_ms))
