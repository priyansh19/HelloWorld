"""Pure logic for the taskbar buddy's *car* form: a side-view Mustang sprite.

Qt-free so it can be unit-tested. Generates an 8-frame loop of a fastback
muscle-car with spinning wheels (the rim spokes rotate frame to frame). RAM
pressure is expressed by the separate translucent smoke overlay (see
:mod:`~memgraph.smoke`), not by reddening the body — so the whole car is exempt
from the panic tint.

The exhaust tip (:data:`EXHAUST`) is where the smoke plume is emitted from.

Palette legend:
``H/B/b`` body (highlight/mid/shadow) · ``W/w`` glass · ``T`` tyre · ``R/r/u``
rim (bright/spoke/hub) · ``C`` chrome bumper · ``L`` headlight · ``X`` tail-light
· ``S`` racing stripe · ``x`` exhaust pipe · ``k`` outline · ``.`` transparent
"""

from __future__ import annotations

import math

# Reuse the mood model + RAM->alarm mapping from the tortoise module.
from .buddy_logic import Mood, mood_for  # noqa: F401  (re-exported)

PALETTE = {
    # Matte black body: flat, closely-spaced greys with no glossy highlight,
    # so the panels read as satin/matte rather than reflective paint.
    "H": "#3a3c40", "B": "#2b2d31", "b": "#1e2023",
    # Glass — kept dark and low-contrast to match the murdered-out look.
    "W": "#5b6470", "w": "#434b55",
    # Wheels.
    "T": "#161618", "R": "#d2d6dc", "r": "#80858f", "u": "#33363c",
    # Trim / lights / stripe / exhaust / outline. Gunmetal trim and a dark
    # graphite stripe keep the matte-black car from looking chromed.
    "C": "#6e747c", "L": "#ffe9a8", "X": "#ff4d62", "S": "#4c4f55",
    "x": "#4a4e55", "k": "#0b0c0e",
}

PANIC_TINT = "#ff5470"
# The car never reddens — the smoke conveys RAM stress — so exempt every glyph.
TINT_EXEMPT = set(PALETTE.keys())

_W, _H = 60, 38
_FRAMES = 8

# Exhaust tip in sprite cells (rear/left when the car faces right). The buddy
# widget maps this to a screen point and feeds it to the smoke overlay.
EXHAUST = (4, 29)


def _build(t: int) -> list[str]:
    g = [["."] * _W for _ in range(_H)]

    def put(x, y, c):
        if 0 <= x < _W and 0 <= y < _H:
            g[y][x] = c

    phase = t / _FRAMES

    # ---- Body: lower slab ------------------------------------------------
    for y in range(20, 31):
        for x in range(6, 54):
            put(x, y, "B")
    # rear deck + hood upper steps
    for x in range(9, 21):
        put(x, 19, "B")
    for x in range(10, 20):
        put(x, 18, "B")
    for x in range(40, 53):
        put(x, 19, "B")
    for x in range(41, 52):
        put(x, 18, "B")

    # ---- Greenhouse: roof, raked glass, pillars --------------------------
    for x in range(24, 35):                      # roof
        put(x, 12, "B")
        put(x, 13, "B")
    for y in range(14, 19):                      # backlight + windshield glass
        f = (y - 14) / 4.0
        xl = int(round(24 - 6 * f))              # rear window slopes down-left
        xr = int(round(34 + 6 * f))              # windshield slopes down-right
        for x in range(xl, xr + 1):
            put(x, y, "W")
    for y in range(14, 19):                      # B-pillar keeps some body
        put(int(round(28.5)), y, "b")

    # ---- Belt-line highlight + a single racing stripe --------------------
    for x in range(7, 53):
        if g[20][x] == "B":
            put(x, 20, "H")
    for x in range(9, 52):                       # low side stripe
        if g[26][x] in ("B", "b"):
            put(x, 26, "S")

    # ---- Lower-body core shadow -----------------------------------------
    for y in range(28, 31):
        for x in range(6, 54):
            if g[y][x] == "B":
                put(x, y, "b")

    # ---- Wheels: tyre, bright rim, rotating spokes, hub ------------------
    for wx, wy in ((16, 29), (45, 29)):
        for yy in range(_H):
            for xx in range(_W):
                if (xx - wx) ** 2 + (yy - wy) ** 2 <= 36:      # tyre R=6
                    put(xx, yy, "T")
        for yy in range(_H):
            for xx in range(_W):
                if (xx - wx) ** 2 + (yy - wy) ** 2 <= 10:      # rim R~3
                    put(xx, yy, "R")
        for k in range(5):          # 5-spoke rim; spins as the frames advance
            a = phase * 2 * math.pi + k * 2 * math.pi / 5
            for rr in range(4):
                put(int(round(wx + rr * math.cos(a))),
                    int(round(wy + rr * math.sin(a))), "r")
        put(wx, wy, "u")

    # ---- Lights, chrome bumpers, exhaust --------------------------------
    put(52, 21, "L"); put(52, 22, "L"); put(51, 21, "L")       # headlight (front)
    put(7, 20, "X"); put(7, 21, "X")                           # tail-light (rear)
    for y in range(21, 26):                                    # front bumper
        put(54, y, "C"); put(53, y, "C")
    for y in range(20, 25):                                    # rear bumper
        put(5, y, "C")
    put(3, 29, "x"); put(4, 29, "x"); put(5, 29, "x")          # exhaust pipe

    # ---- Outline where the car meets empty space ------------------------
    body = set("HBbWwTRruCLXSx")
    src = [row[:] for row in g]
    for y in range(_H):
        for x in range(_W):
            if src[y][x] in body and any(
                    not (0 <= x + a < _W and 0 <= y + b < _H)
                    or src[y + b][x + a] == "."
                    for a, b in ((0, 1), (1, 0), (-1, 0), (0, -1))):
                if src[y][x] == "T":
                    continue                     # tyres already read as dark
                put(x, y, "k")

    return ["".join(r) for r in g]


WALK_FRAMES = [_build(t) for t in range(_FRAMES)]
GALLOP_FRAMES = WALK_FRAMES
SPRITE_H = len(WALK_FRAMES[0])
SPRITE_W = len(WALK_FRAMES[0][0])


def frames_for_gait(gait: str) -> list[list[str]]:
    return WALK_FRAMES


def apply_overlays(rows: list[str], shades: bool = False,
                   blink: bool = False) -> list[str]:
    """Cars don't blink or wear shades — the overlay is a no-op, kept so the
    buddy widget can treat every sprite module the same way."""
    return list(rows)
