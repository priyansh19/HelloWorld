"""Pure logic for the taskbar buddy: a pixel cat, its animation and moods.

Qt-free on purpose so the buddy's whole personality is unit-testable. The art is
a character grid per frame; the widget rasterises it with QPainter at runtime
(no image assets).

Palette legend:
``C`` body · ``c`` belly/leg shade · ``H`` head · ``E`` ear · ``i`` inner ear ·
``o`` eye · ``n`` nose · ``T`` tail · ``L`` leg · ``p`` paw · ``S`` sunglasses ·
``W`` lens glint · ``.`` transparent
"""

from __future__ import annotations

from dataclasses import dataclass

PALETTE = {
    "C": "#e8b06a", "c": "#cf8f45", "H": "#eab873", "E": "#e8b06a",
    "i": "#e8968a", "o": "#2a2118", "n": "#c9705f", "T": "#e8b06a",
    "L": "#cf8f45", "p": "#b87a38", "S": "#14161c", "W": "#9fd8ff",
    # kept so old references don't break:
    "N": "#eab873", "M": "#c9705f", "b": "#cf8f45",
}

PANIC_TINT = "#ff5470"
TINT_EXEMPT = set("SoWn")  # eyes/shades/nose keep their colour under panic tint

# Cat body (facing right): upright ears + raised round head, oval body, tail.
_BODY = [
    "..................E..E....",
    ".................EiE.EiE..",
    ".................HHHHHHH..",
    "................HHHHHHHH..",
    "T...............HHHHHHHHH.",
    "TT..............HHHHHoHHH.",
    "TT..............HHHHHHHnn.",
    ".T...........CCCCCCHHHHHH.",
    ".TCCCCCCCCCCCCCCCCCCCCCC..",
    "..CCCCCCCCCCCCCCCCCCCCC...",
    "..CCCCCCCCCCCCCCCCCCCC....",
    "..cCCCCCCCCCCCCCCCCCCc....",
]

_WALK_LEGS = [
    ["...LL..LL......LL..LL.....",
     "...LL..LL......LL..LL.....",
     "...pp..pp......pp..pp....."],
    ["..LL...LL.....LL...LL.....",
     "..LL...LL.....LL...LL.....",
     "..pp...pp.....pp...pp....."],
]

_GALLOP_LEGS = [
    ["...L.....L.....L.....L....",
     "..L......L....L......L....",
     "..p......p....p......p...."],
    ["....LLLL.........LLLL.....",
     "....LLLL.........LLLL.....",
     "....pppp.........pppp....."],
    ["...LL..LL......LL..LL.....",
     "..L.....L.....L.....L.....",
     "..p.....p.....p.....p....."],
]


def _pad(rows: list[str]) -> list[str]:
    w = max(len(r) for r in rows)
    return [r.ljust(w, ".") for r in rows]


WALK_FRAMES = [_pad(_BODY + legs) for legs in _WALK_LEGS]
GALLOP_FRAMES = [_pad(_BODY + legs) for legs in _GALLOP_LEGS]
SPRITE_H = len(WALK_FRAMES[0])
SPRITE_W = len(WALK_FRAMES[0][0])


def frames_for_gait(gait: str) -> list[list[str]]:
    """Animation frames for a gait ('idle' shares the walk cycle, slower)."""
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
        seg = "SS" + "S" + "W"           # lens + glint
        lo = max(0, c - 2)
        rows[r] = row[:lo] + seg[:len(row) - lo] + row[lo + len(seg):]
    elif blink:
        rows[r] = rows[r][:c] + "H" + rows[r][c + 1:]
    return rows


@dataclass(frozen=True)
class Mood:
    gait: str            # "idle" | "walk" | "gallop"
    pack: str            # kept for compatibility (unused visually now)
    shades: bool         # tracked LLM process is running
    panic: bool          # RAM past the red threshold
    frame_ms: int        # animation frame interval

    @property
    def wander_ok(self) -> bool:
        return self.gait != "gallop" and not self.panic


def mood_for(cpu_pct: float, ram_pct: float, amber: float, red: float,
             model_loaded: bool) -> Mood:
    """Map live metrics to the cat's behaviour.

    CPU drives the gait (stroll < 12% < walk < 50% < gallop); RAM past the red
    threshold triggers panic; a running tracked process puts sunglasses on.
    (Traversal *speed* is driven by RAM in the widget itself.)
    """
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
