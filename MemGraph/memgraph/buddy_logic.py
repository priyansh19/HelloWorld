"""Pure logic for the taskbar llama buddy: sprites, overlays and moods.

Qt-free on purpose so the whole personality of the llama is unit-testable.
The sprite art is a character grid per frame; the widget rasterises it with
QPainter at runtime (no image assets).

Palette legend:
``E`` ear · ``H`` head · ``o`` eye · ``M`` muzzle · ``N`` neck · ``B`` body ·
``b`` belly shade · ``T`` tail · ``L``/``l`` legs · ``P``/``p`` saddle-pack ·
``S`` sunglasses · ``W`` lens glint · ``.`` transparent
"""

from __future__ import annotations

from dataclasses import dataclass

SPRITE_W = 24

PALETTE = {
    "E": "#e8d5b0", "H": "#f2e3c8", "N": "#f2e3c8", "B": "#f2e3c8",
    "b": "#d9c19a", "T": "#d9c19a", "L": "#d9c19a", "l": "#c4a87e",
    "M": "#c9a06e", "o": "#2a2118",
    "P": "#e0684b", "p": "#f28a6a", "S": "#14161c", "W": "#9fd8ff",
}

PANIC_TINT = "#ff5470"
# Pixels that keep their own colour when the panic tint is applied.
TINT_EXEMPT = set("SoW")

_BODY = [
    "........................",
    ".................E.E....",
    ".................EEE....",
    "................EHHHH...",
    "................HHHHo...",
    "................HHHM....",
    ".................NNN....",
    ".TT..............NNN....",
    ".TTBBBBBBBBBBBBBBNNN....",
    "..BBBBBBBBBBBBBBBNN.....",
    "..BBBBBBBBBBBBBBBB......",
    "..bBBBBBBBBBBBBBb.......",
]

_WALK_LEGS = [
    [
        "...LL...LL...LL..LL.....",
        "...LL...LL...LL..LL.....",
        "...ll...ll...ll..ll.....",
    ],
    [
        "....LL...LL..LL...LL....",
        "....LL...LL..LL...LL....",
        "....ll...ll..ll...ll....",
    ],
]

_GALLOP_LEGS = [
    [  # extended
        ".LL..........LLL........",
        "LL............LLL.......",
        "l..............ll.......",
    ],
    [  # gathered
        "....LL....LL............",
        ".....LL..LL.............",
        ".....ll..ll.............",
    ],
    [  # mid-stride
        "..LL......LL...LL.......",
        "..LL......LL....LL......",
        "..ll......ll....ll......",
    ],
]

WALK_FRAMES = [_BODY + legs for legs in _WALK_LEGS]
GALLOP_FRAMES = [_BODY + legs for legs in _GALLOP_LEGS]
SPRITE_H = len(WALK_FRAMES[0])


def frames_for_gait(gait: str) -> list[list[str]]:
    """Animation frames for a gait ('idle' shares the walk cycle, slower)."""
    return GALLOP_FRAMES if gait == "gallop" else WALK_FRAMES


def apply_overlays(rows: list[str], pack: str = "normal",
                   shades: bool = False, blink: bool = False) -> list[str]:
    """Stamp the saddle-pack / sunglasses / blink onto a frame copy."""
    rows = list(rows)
    if pack == "full":
        rows[5] = rows[5][:5] + "pppp" + rows[5][9:]
        rows[6] = rows[6][:4] + "PPPPPPP" + rows[6][11:]
        rows[7] = rows[7][:3] + "PPPPPPPP" + rows[7][11:]
    else:
        rows[6] = rows[6][:5] + "PPPP" + rows[6][9:]
        rows[7] = rows[7][:4] + "PPPPPP" + rows[7][10:]
    if shades:
        rows[3] = rows[3][:15] + "SSSSSS" + rows[3][21:]
        rows[4] = rows[4][:16] + "SWSSW" + rows[4][21:]
    elif blink:
        rows[4] = rows[4][:20] + "H" + rows[4][21:]
    return rows


@dataclass(frozen=True)
class Mood:
    gait: str            # "idle" | "walk" | "gallop"
    pack: str            # "normal" | "full"
    shades: bool         # tracked LLM process is running
    panic: bool          # primary metric past the red threshold
    frame_ms: int        # animation frame interval

    @property
    def wander_ok(self) -> bool:
        """Only stroll around when relaxed."""
        return self.gait != "gallop" and not self.panic


def mood_for(cpu_pct: float, ram_pct: float, amber: float, red: float,
             model_loaded: bool) -> Mood:
    """Map live metrics to the llama's behaviour.

    * CPU drives the gait: lazy stroll < 12%, walk < 50%, gallop above.
    * RAM drives the saddle-pack (full past amber) and panic (past red).
    * A running tracked process (your LLM) puts its shades on.
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
        frame_ms = int(220 - 1.2 * cpu_pct)          # 220ms .. ~160ms
    else:
        frame_ms = max(60, int(130 - 0.7 * cpu_pct))  # faster with load
    return Mood(gait=gait, pack=pack, shades=model_loaded,
                panic=panic, frame_ms=frame_ms)
