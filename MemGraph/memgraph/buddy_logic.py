"""Pure logic for the taskbar buddy: a realistic Galapagos-tortoise pixel sprite.

Qt-free so the buddy's personality is unit-testable. The tortoise is generated
procedurally into an 8-frame walk cycle modelled on a real Galapagos giant
tortoise: a high, rounded olive/khaki-green carapace divided into rectangular
scute plates (raised centres, dark grooves), a long grey scaly neck ending in a
hooked beak, and four thick elephantine grey legs with stubby toes that lift,
swing and plant. The widget rasterises the character grids with QPainter (no
image assets).

Palette legend:
``g/G/d`` shell scute facets (lit/mid/shadow olive-green) · ``r`` raised scute
highlight · ``s`` scute groove/seam · ``o`` shell outline · ``n/N`` neck/head
skin (grey, lit/shadow) · ``b`` beak · ``L/l`` legs (grey, lit/shadow) · ``k``
foot/toe shadow · ``y`` plastron (yellow-tan belly) · ``e`` eye-white · ``p``
pupil · ``S`` sunglasses · ``W`` lens glint · ``.`` transparent
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PALETTE = {
    # Carapace: olive / khaki green, faceted by the dome's curvature.
    "g": "#8f9a54", "G": "#6f7a3e", "d": "#515a2b", "r": "#a7b167",
    "s": "#39401f", "o": "#2a2f16",
    # Neck & head: grey, scaly reptilian skin.
    "n": "#9a9c96", "N": "#6f716c", "b": "#4a4b46",
    # Legs: grey, a touch darker/warmer than the neck; toes in deep shadow.
    "L": "#8b8d86", "l": "#63655f", "k": "#3b3c37",
    # Plastron (belly) peeking below the shell.
    "y": "#c7b56e",
    # Face + accessories.
    "e": "#f2eee2", "p": "#141418", "S": "#14161c", "W": "#9fd8ff",
}

PANIC_TINT = "#ff5470"
# Under the RAM alarm only the soft body flushes red — the head/face, tail and
# legs. The shell keeps its olive colour, and eyes/shades stay as-is. So every
# shell glyph (g/G/d/r/s/o) plus the eye/shade glyphs are exempt from the tint.
TINT_EXEMPT = set("epSW") | set("gGdrso")

_W, _H = 60, 38
_FRAMES = 8


def _leg_phase(p: float) -> tuple[float, float]:
    """Return (lift, dx) for a leg at walk-cycle phase ``p`` in [0, 1).

    Stance (p < 0.62): foot planted, sliding backward under the body.
    Swing  (p >= 0.62): foot lifts on a sine arc and reaches forward.
    """
    if p < 0.62:
        return 0.0, 2.4 * (1 - 2 * (p / 0.62))
    q = (p - 0.62) / 0.38
    return math.sin(q * math.pi), 2.4 * (2 * q - 1)


def _build(t: int) -> list[str]:
    g = [["."] * _W for _ in range(_H)]

    def put(x, y, c):
        if 0 <= x < _W and 0 <= y < _H:
            g[y][x] = c

    # Carapace geometry: a tall rounded dome sitting high on the legs.
    cx, cy, rx, ry = 25.0, 17.0, 20.0, 13.5

    # ---- Legs: four thick elephantine columns with stubby toes -----------
    # (x0, near?) — near legs (front-right, back-right to viewer) are lighter.
    for x0, off, near in ((9, 0.0, False), (18, 0.5, True),
                          (31, 0.5, True), (40, 0.0, False)):
        lift, dx = _leg_phase((t / _FRAMES + off) % 1.0)
        x = x0 + int(round(dx))
        bottom = 34 - int(round(lift * 5))
        body, shad = ("L", "l") if near else ("l", "k")
        for yy in range(24, bottom):
            for xx in range(x, x + 7):
                # round the outer edge of the column slightly
                edge = xx == x or xx == x + 6
                put(xx, yy, shad if edge else body)
        # foot + three stubby toes
        for xx in range(x, x + 7):
            put(xx, bottom, "k")
        for tx in (x + 1, x + 3, x + 5):
            put(tx, bottom + 1, "k")

    # ---- Plastron: a sliver of yellow-tan belly below the shell ----------
    for y in range(24, 28):
        for x in range(18, 34):
            if ((x - 26) / 9) ** 2 + ((y - 25) / 3) ** 2 <= 1.0:
                put(x, y, "y")

    # ---- Neck + head: long grey scaly neck, hooked beak ------------------
    for y in range(15, 24):                      # neck, thickening downward
        for x in range(38, 48):
            t2 = (x - 38) / 10.0
            half = 2.5 + 2.5 * t2
            if abs(y - (19 + 1.5 * t2)) <= half:
                if g[y][x] == ".":
                    put(x, y, "n")
    hx, hy, hrx, hry = 50.0, 17.0, 7.0, 5.5      # head
    for y in range(_H):
        for x in range(_W):
            if ((x - hx) / hrx) ** 2 + ((y - hy) / hry) ** 2 <= 1.0:
                put(x, y, "n")
    # shade the underside of neck/head for volume
    for y in range(_H):
        for x in range(_W):
            if g[y][x] == "n" and (y >= 20 or (y > hy and (x - hx) ** 2
                                    + ((y - hy) * 1.3) ** 2 > 20)):
                g[y][x] = "N"
    # hooked beak jutting forward, mouth line
    put(57, 16, "b"); put(58, 17, "b"); put(57, 18, "b")
    put(56, 18, "b"); put(55, 19, "N")
    # eye
    put(53, 15, "e"); put(54, 15, "p")

    # ---- Short tail on the left -----------------------------------------
    for i, y in enumerate(range(19, 22)):
        for x in range(4, 4 + (4 - i)):
            if g[y][x] == ".":
                put(x, y, "N")

    # ---- Carapace: faceted olive dome ------------------------------------
    lx, ly, lz = -0.5, -0.82, 0.72               # light direction
    for y in range(_H):
        for x in range(_W):
            nx, ny = (x - cx) / rx, (y - cy) / ry
            if nx * nx + ny * ny <= 1.0 and y <= cy + 3:
                nz = math.sqrt(max(0.0, 1 - nx * nx - ny * ny))
                l = nx * lx + ny * ly + nz * lz
                g[y][x] = "g" if l > 0.6 else ("G" if l > 0.3 else "d")

    # ---- Scute plates: a grid of grooves carving the shell into tiles ----
    # Vertical grooves (radiating) + horizontal growth rings give the giant
    # tortoise's characteristic rectangular scutes.
    for ang in (-62, -34, -10, 12, 36, 62):      # radial grooves
        a = math.radians(ang)
        for r in range(2, 22):
            x = int(round(cx + r * math.sin(a)))
            y = int(round((cy - 1) - r * math.cos(a) * 0.7))
            if 0 <= x < _W and 0 <= y < _H and g[y][x] in ("g", "G", "d"):
                g[y][x] = "s"
    for rr in (6.0, 11.0):                        # concentric growth rings
        for x in range(_W):
            nx = (x - cx) / rx
            if abs(nx) < 1.0:
                y = int(round((cy - 1) - rr * math.cos(math.asin(nx)) * 0.7))
                if 0 <= y < _H and g[y][x] in ("g", "G", "d"):
                    g[y][x] = "s"
    # Raised scute centres: brighten cells ringed by grooves near the top.
    src = [r[:] for r in g]
    for y in range(_H):
        for x in range(_W):
            if src[y][x] == "g" and y < cy:
                near_seam = any(
                    0 <= x + a < _W and 0 <= y + b < _H
                    and src[y + b][x + a] == "s"
                    for a, b in ((0, -1), (0, 1), (-1, 0), (1, 0)))
                if not near_seam:
                    g[y][x] = "r"

    # ---- Shell outline ---------------------------------------------------
    src = [r[:] for r in g]
    shell = ("g", "G", "d", "r", "s")
    for y in range(_H):
        for x in range(_W):
            if src[y][x] in shell and any(
                    not (0 <= x + a < _W and 0 <= y + b < _H)
                    or src[y + b][x + a] == "."
                    for a, b in ((0, 1), (1, 0), (-1, 0), (0, -1))):
                g[y][x] = "o"

    return ["".join(r) for r in g]


WALK_FRAMES = [_build(t) for t in range(_FRAMES)]
GALLOP_FRAMES = WALK_FRAMES
SPRITE_H = len(WALK_FRAMES[0])
SPRITE_W = len(WALK_FRAMES[0][0])


def frames_for_gait(gait: str) -> list[list[str]]:
    return WALK_FRAMES


def _find_eye(rows: list[str]) -> tuple[int, int] | None:
    for r, row in enumerate(rows):
        c = row.find("p")
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
        rows[r] = rows[r][:c] + "N" + rows[r][c + 1:]
    return rows


@dataclass(frozen=True)
class Mood:
    gait: str            # "idle" | "walk" | "gallop"
    pack: str            # kept for compatibility (unused visually)
    shades: bool         # tracked LLM process is running
    panic: bool          # RAM past the red threshold
    frame_ms: int        # animation frame interval
    stress: float = 0.0  # 0..1 RAM alarm level -> how red the buddy turns

    @property
    def wander_ok(self) -> bool:
        return self.gait != "gallop" and not self.panic


def mood_for(cpu_pct: float, ram_pct: float, amber: float, red: float,
             model_loaded: bool) -> Mood:
    """RAM drives the alarm: once memory passes amber the tortoise turns
    progressively red and runs (gallop), full red at the red threshold. Below
    amber, CPU sets a calm idle/walk/gallop gait. A running tracked process puts
    sunglasses on."""
    stress = 0.0
    if ram_pct >= amber:
        frac = min(1.0, (ram_pct - amber) / max(1.0, red - amber))
        stress = 0.25 + 0.75 * frac
        gait = "gallop"
    elif cpu_pct < 12:
        gait = "idle"
    elif cpu_pct < 50:
        gait = "walk"
    else:
        gait = "gallop"

    panic = ram_pct >= red
    pack = "full" if ram_pct >= amber else "normal"
    if gait == "idle":
        frame_ms = 200
    elif gait == "walk":
        frame_ms = int(150 - 1.0 * cpu_pct)
    else:
        frame_ms = int(110 - 0.5 * cpu_pct - 35 * stress)
    return Mood(gait=gait, pack=pack, shades=model_loaded,
                panic=panic, frame_ms=max(45, frame_ms), stress=stress)
