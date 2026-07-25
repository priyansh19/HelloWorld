"""Pure logic for the taskbar buddy: a realistic Galapagos-tortoise pixel sprite.

Qt-free so the buddy's personality is unit-testable. The tortoise is generated
procedurally into an 8-frame walk cycle modelled on a real Galapagos giant
tortoise:

* a high, rounded olive/khaki carapace shaded with a five-step highlight ->
  core-shadow ramp (a lit dome, not flat facets) plus a specular glint;
* large, beveled scute plates — a central vertebral column flanked by costal
  rows, each plate raised with an ambient-occlusion groove around it;
* the shell overhangs and casts a contact shadow onto the body/legs;
* a long grey scaly neck (with skin wrinkles) ending in a wedge head — brow
  ridge, nostril and a pronounced hooked beak;
* four thick elephantine grey legs that *taper* from shoulder to foot, each a
  shaded column with stubby toe-nails, lifting/swinging/planting in the cycle.

The widget rasterises the character grids with QPainter (no image assets).

Palette legend:
``r`` shell specular · ``g/G/d/D`` carapace ramp (lit->core shadow) · ``s``
scute groove · ``o`` shell outline · ``n/N`` neck+head skin (lit/shadow) · ``b``
beak · ``L/l`` legs (lit/shadow) · ``k`` toe/contact shadow · ``y`` plastron ·
``e`` eye-white · ``p`` pupil · ``S`` sunglasses · ``W`` lens glint · ``.`` clear
"""

from __future__ import annotations

import math
from dataclasses import dataclass

PALETTE = {
    # Carapace: olive/khaki, five-step lit-dome ramp + specular highlight.
    "r": "#b7c179", "g": "#8f9a54", "G": "#6f7a3e", "d": "#515a2b",
    "D": "#3b4320", "s": "#333a1c", "o": "#232811",
    # Neck & head: grey scaly reptilian skin (lit / shadow) + horny beak.
    "n": "#a2a49d", "N": "#6f716b", "b": "#45463f",
    # Legs: grey tapered columns; toe-nails / contact shadow in deep grey.
    "L": "#8b8d86", "l": "#5f615b", "k": "#33342f",
    # Plastron (belly) peeking below the shell.
    "y": "#c7b56e",
    # Face + accessories.
    "e": "#f2eee2", "p": "#141418", "S": "#14161c", "W": "#9fd8ff",
}

PANIC_TINT = "#ff5470"
# Under the RAM alarm only the soft body flushes red — the head/face, tail and
# legs. The shell keeps its olive colour, and eyes/shades stay as-is. Every
# shell glyph plus the eye/shade glyphs are exempt from the tint.
TINT_EXEMPT = set("epSW") | set("rgGdDso")

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
    cx, cy, rx, ry = 24.0, 16.0, 20.0, 13.5

    # ---- Legs: four tapered elephantine columns with toe-nails -----------
    # (x0, phase-offset, near?) — near legs are the lighter grey.
    def draw_leg(x0, off, near):
        lift, dx = _leg_phase((t / _FRAMES + off) % 1.0)
        x = x0 + int(round(dx))
        top, bottom = 25, 34 - int(round(lift * 5))
        span = max(1, bottom - top)
        body = "L" if near else "l"
        for i, yy in enumerate(range(top, bottom)):
            frac = i / span
            w = int(round(8 - 3 * frac))          # 8 wide at shoulder -> 5 foot
            lx = x + (8 - w) // 2
            for j in range(w):
                xx = lx + j
                edge = j == 0 or j == w - 1
                put(xx, yy, "l" if (edge or not near) and j != w // 2 else body)
        # foot pad + three stubby toe-nails
        for xx in range(x + 1, x + 7):
            put(xx, bottom, "k")
        for tx in (x + 1, x + 3, x + 5):
            put(tx, bottom + 1, "k")

    for x0, off, near in ((8, 0.0, False), (16, 0.5, True),
                          (30, 0.0, True), (39, 0.5, False)):
        draw_leg(x0, off, near)

    # ---- Plastron: a sliver of yellow-tan belly below the shell ----------
    for y in range(24, 28):
        for x in range(16, 34):
            if ((x - 25) / 10) ** 2 + ((y - 25) / 3) ** 2 <= 1.0:
                put(x, y, "y")

    # ---- Neck + head: long grey scaly neck, wedge head, hooked beak ------
    for y in range(14, 24):                      # neck, thickening downward
        for x in range(37, 48):
            t2 = (x - 37) / 11.0
            half = 2.0 + 3.0 * t2
            if abs(y - (18 + 2.0 * t2)) <= half:
                if g[y][x] == ".":
                    put(x, y, "n")
    hx, hy, hrx, hry = 51.0, 16.0, 7.5, 5.5      # head (wedge — flatter top)
    for y in range(_H):
        for x in range(_W):
            ny = (y - hy) / (hry * (0.8 if y < hy else 1.0))
            if ((x - hx) / hrx) ** 2 + ny ** 2 <= 1.0:
                put(x, y, "n")
    # volume shading: underside of neck & head to shadow grey
    for y in range(_H):
        for x in range(_W):
            if g[y][x] == "n" and (y >= 20 or (y > hy + 1)
                                   or (x < 40 and y > 19)):
                g[y][x] = "N"
    for wy in (16, 19, 22):                        # a few neck skin-wrinkles
        for x in range(38, 46, 2):
            if g[wy][x] == "n":
                put(x, wy, "N")
    # brow ridge, eye, nostril, hooked beak
    for x in range(50, 55):
        if g[13][x] == "n":
            put(x, 13, "N")
    put(53, 15, "e"); put(54, 15, "p")            # round eye
    put(56, 15, "N")                              # nostril
    put(57, 15, "b"); put(58, 16, "b"); put(58, 17, "b")   # hook
    put(57, 18, "b"); put(56, 18, "N")            # mouth line

    # ---- Short tail on the left -----------------------------------------
    for i, y in enumerate(range(18, 21)):
        for x in range(3, 3 + (4 - i)):
            if g[y][x] == ".":
                put(x, y, "N")

    # ---- Carapace: five-step lit dome (highlight -> core shadow) ---------
    lx, ly, lz = -0.48, -0.80, 0.75              # light from upper-left
    for y in range(_H):
        for x in range(_W):
            nx, ny = (x - cx) / rx, (y - cy) / ry
            if nx * nx + ny * ny <= 1.0 and y <= cy + 4:
                nz = math.sqrt(max(0.0, 1 - nx * nx - ny * ny))
                l = nx * lx + ny * ly + nz * lz
                g[y][x] = ("r" if l > 0.80 else "g" if l > 0.55
                           else "G" if l > 0.30 else "d" if l > 0.08 else "D")

    # ---- Scute plates: central vertebral column + costal rows ------------
    shell = ("r", "g", "G", "d", "D")
    for ang in (-52, -26, 0, 26, 52):            # radial grooves (vertebrae)
        a = math.radians(ang)
        for rr in range(2, 22):
            x = int(round(cx + rr * math.sin(a)))
            y = int(round((cy - 1) - rr * math.cos(a) * 0.7))
            if 0 <= x < _W and 0 <= y < _H and g[y][x] in shell:
                g[y][x] = "s"
    for ring in (6.5, 12.0):                      # two concentric growth rings
        for x in range(_W):
            nx = (x - cx) / rx
            if abs(nx) < 1.0:
                y = int(round((cy - 1) - ring * math.cos(math.asin(nx)) * 0.7))
                if 0 <= y < _H and g[y][x] in shell:
                    g[y][x] = "s"

    # ---- Bevel each scute: darken shell pixels touching a groove (AO) ----
    darker = {"r": "g", "g": "G", "G": "d", "d": "D", "D": "D"}
    src = [row[:] for row in g]
    for y in range(_H):
        for x in range(_W):
            if src[y][x] in shell and any(
                    0 <= x + a < _W and 0 <= y + b < _H
                    and src[y + b][x + a] in ("s", "o")
                    for a, b in ((0, -1), (0, 1), (-1, 0), (1, 0))):
                g[y][x] = darker[src[y][x]]

    # ---- Shell outline + contact shadow onto body/legs -------------------
    src = [row[:] for row in g]
    for y in range(_H):
        for x in range(_W):
            if src[y][x] in shell and any(
                    not (0 <= x + a < _W and 0 <= y + b < _H)
                    or src[y + b][x + a] == "."
                    for a, b in ((0, 1), (1, 0), (-1, 0), (0, -1))):
                g[y][x] = "o"
    # the shell's lower lip drops a shadow onto whatever sits just beneath it
    for x in range(_W):
        for y in range(_H - 1):
            if g[y][x] == "o" and g[y + 1][x] in ("L", "l", "y", "n", "N"):
                put(x, y + 1, "k")

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
