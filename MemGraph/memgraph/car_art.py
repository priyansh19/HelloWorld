"""Vector art for the Mustang buddy — a '67 fastback drawn with QPainter.

Why vector and not a character grid: the old 60x38 cell sprite simply cannot
carry the shapes that make a Mustang read as a Mustang — the long hood/short
deck proportion, the unbroken fastback roofline, the C-scoop on the rear
quarter, the tri-bar tail-lights. Those need curves, not 3-pixel steps.

So the car is drawn as real geometry in a 360x112 *design* coordinate space and
rasterised with antialiasing and supersampling, which means it stays crisp at
any widget size and renders vastly more pixels per frame than the grid ever
could (see :data:`SUPERSAMPLE`).

Shapes are drawn back-to-front: tyres, body (with the wheel arches subtracted so
the arch gap reads), glasshouse, then trim/lights/details, then the rims on top
so the spokes stay legible.

Public surface mirrors the other sprite modules so
:class:`~memgraph.llama.LlamaBuddy` can treat them interchangeably, plus
:func:`render_image` for the raster path.
"""

from __future__ import annotations

import math

from PySide6 import QtCore, QtGui

# ---------------------------------------------------------------------- #
# Design space and display sizing
# ---------------------------------------------------------------------- #
DESIGN_W, DESIGN_H = 360.0, 104.0
# Proportions come from a real '67 fastback: 108" wheelbase on a 184" body,
# 51" tall on 26" tyres. Ground sits at y=GROUND so everything below the sill
# reads as suspension/tyre, not bodywork.
GROUND = 100.0

# Sizing units the buddy widget multiplies by ``llama_scale`` (kept in the same
# ballpark as the tortoise's cell grid so existing scale settings still feel
# right). Aspect matches the design space.
SPRITE_W, SPRITE_H = 72, 23

# Supersampling factor for rasterisation: every output pixel is averaged from
# SUPERSAMPLE^2 samples, and the cache is kept at 2x display size for HiDPI.
SUPERSAMPLE = 5
_HIDPI = 2

FRAMES = 8
IS_VECTOR = True

# Exhaust tip in *sizing units*, used as the smoke plume's source.
EXHAUST = (6, 18)

# ---------------------------------------------------------------------- #
# Matte-black palette. Flat, closely-spaced values = satin, not gloss.
# ---------------------------------------------------------------------- #
_BODY_TOP = "#43454a"
_BODY_MID = "#2c2e32"
_BODY_LOW = "#191a1d"
_BODY_EDGE = "#0b0c0e"
_GLASS_TOP = "#5a636f"
_GLASS_LOW = "#39404a"
_TRIM = "#767c85"
_TRIM_DARK = "#4a4e55"
_TYRE = "#131315"
_TYRE_WALL = "#232427"
_RIM = "#8e949d"
_RIM_DARK = "#4b5057"
_HUB = "#2a2d31"
_HEAD = "#ffeaa7"
_TAIL = "#ff3b52"
_STRIPE = "#4f535a"
_CALIPER = "#c8302f"
_SPOKE = "#3b4048"
_GRILLE = "#101114"

# Compatibility shims: the buddy widget's tint path keys off these. The car
# never reddens (its smoke carries the RAM signal), so everything is exempt.
PALETTE = {
    "B": _BODY_MID, "H": _BODY_TOP, "b": _BODY_LOW, "k": _BODY_EDGE,
    "W": _GLASS_TOP, "w": _GLASS_LOW, "C": _TRIM, "x": _TRIM_DARK,
    "T": _TYRE, "R": _RIM, "r": _RIM_DARK, "u": _HUB,
    "L": _HEAD, "X": _TAIL, "S": _STRIPE, "G": _GRILLE,
    "c": _CALIPER, "p": _SPOKE,
}
PANIC_TINT = "#ff5470"
TINT_EXEMPT = set(PALETTE.keys())


def _c(hex_str: str, alpha: int = 255) -> QtGui.QColor:
    col = QtGui.QColor(hex_str)
    col.setAlpha(alpha)
    return col


# ---------------------------------------------------------------------- #
# Geometry — modern (S550/S650) Mustang proportions
# ---------------------------------------------------------------------- #
# Scaled off a real car: 188" long, 54" tall, 107" wheelbase, 38" front and
# 43" rear overhang, on 26.5" tyres wrapped around 20" rims. The low roof over
# tall body sides (greenhouse only ~half the door height) plus big wheels that
# nearly fill their arches are what make a modern Mustang read correctly.
_REAR_WHEEL = (93.0, 77.5)
_FRONT_WHEEL = (275.0, 77.5)
_TYRE_R = 22.5
_ARCH_R = 25.0             # tight arch gap — the wheels fill them
_RIM_R = 17.0              # 20" rim inside a 26.5" tyre == thin sidewall

_SILL = 83.0               # rocker panel
_BELT = 33.0               # beltline / window sill
_ROOF = 8.0


def _body_path() -> QtGui.QPainterPath:
    """Modern Mustang fastback silhouette: low chopped roof, heavily raked
    screens, ducktail deck, rear haunch and a front splitter."""
    p = QtGui.QPainterPath()
    p.moveTo(30, _SILL)                           # rear lower corner
    p.lineTo(24, 70)                              # rear bumper
    p.lineTo(21, 52)                              # tail panel, raked forward
    p.lineTo(20, 43)                              # ducktail spoiler lip
    p.lineTo(29, 39.5)                            # spoiler kicks up
    p.lineTo(42, 40)                              # very short deck
    p.cubicTo(74, 35, 112, 23, 148, 12.5)         # long fastback slope
    p.cubicTo(164, 10.5, 182, 9.5, 200, 10)       # low, flat roof
    p.cubicTo(212, 11.5, 221, 15, 228, 20)        # heavily raked A-pillar
    p.cubicTo(236, 24.5, 244, 29, 250, 31)        # windshield
    p.lineTo(256, 31.5)                           # cowl
    p.cubicTo(288, 31, 314, 33, 330, 37)          # hood slopes DOWN (wedge)
    p.cubicTo(334, 38, 337, 39.5, 338, 43)        # nose
    p.lineTo(338, 58)                             # short front fascia
    p.cubicTo(337, 67, 334, 72, 331, 75)          # lower air dam
    p.lineTo(336, 79)                             # splitter lip juts forward
    p.lineTo(328, 84)
    p.lineTo(30, _SILL)
    p.closeSubpath()
    return p


def _arch(cx: float, cy: float, r: float) -> QtGui.QPainterPath:
    p = QtGui.QPainterPath()
    p.addEllipse(QtCore.QRectF(cx - r, cy - r, 2 * r, 2 * r))
    return p


def _glass_path() -> QtGui.QPainterPath:
    """Side glass: short, chopped, with the fastback's tapering rear edge."""
    p = QtGui.QPainterPath()
    p.moveTo(246, 31.5)                      # A-pillar base
    p.cubicTo(238, 26, 228, 19, 218, 16.5)   # up the raked A-pillar
    p.lineTo(186, 13.0)                      # roof rail
    p.cubicTo(164, 15.5, 140, 22, 124, 29)   # long C-pillar down the slope
    p.lineTo(132, _BELT)
    p.lineTo(244, _BELT)                     # beltline
    p.closeSubpath()
    return p


def _draw_wheel(p: QtGui.QPainter, cx: float, cy: float, spin: float) -> None:
    """Big dark multi-spoke alloy with a red caliper peeking through."""
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_TYRE))                                    # tyre
    p.drawEllipse(QtCore.QPointF(cx, cy), _TYRE_R, _TYRE_R)
    p.setPen(QtGui.QPen(_c(_TYRE_WALL), 1.2))                # sidewall
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(cx, cy), _TYRE_R - 1.6, _TYRE_R - 1.6)

    p.setPen(QtCore.Qt.NoPen)                                # rim barrel
    p.setBrush(_c("#15171a"))
    p.drawEllipse(QtCore.QPointF(cx, cy), _RIM_R, _RIM_R)

    p.setBrush(_c(_CALIPER))                                 # red brake caliper
    cal = QtGui.QPainterPath()
    cal.moveTo(cx, cy)
    cal.arcTo(QtCore.QRectF(cx - 11, cy - 11, 22, 22), 118, 58)
    cal.closeSubpath()
    p.drawPath(cal)
    p.setBrush(_c("#2a2d32"))                                # disc face
    p.drawEllipse(QtCore.QPointF(cx, cy), 8.2, 8.2)

    p.setBrush(_c(_SPOKE))                                   # ten thin spokes
    for k in range(10):
        a = spin + k * 2 * math.pi / 10
        w = 0.115
        sp = QtGui.QPainterPath()
        sp.moveTo(cx + 4.0 * math.cos(a), cy + 4.0 * math.sin(a))
        sp.lineTo(cx + (_RIM_R - 1.2) * math.cos(a - w),
                  cy + (_RIM_R - 1.2) * math.sin(a - w))
        sp.lineTo(cx + (_RIM_R - 1.2) * math.cos(a + w),
                  cy + (_RIM_R - 1.2) * math.sin(a + w))
        sp.closeSubpath()
        p.drawPath(sp)
    p.setPen(QtGui.QPen(_c("#3c4149"), 1.0))                 # rim lip
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(cx, cy), _RIM_R - 0.5, _RIM_R - 0.5)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c("#202328"))
    p.drawEllipse(QtCore.QPointF(cx, cy), 3.4, 3.4)


def _draw(p: QtGui.QPainter, frame_i: int) -> None:
    spin = (frame_i / FRAMES) * 2 * math.pi

    _draw_wheel(p, *_REAR_WHEEL, spin=spin)
    _draw_wheel(p, *_FRONT_WHEEL, spin=spin)

    # ---- body, with wheel arches subtracted -----------------------------
    body = _body_path()
    body = body.subtracted(_arch(*_REAR_WHEEL, r=_ARCH_R))
    body = body.subtracted(_arch(*_FRONT_WHEEL, r=_ARCH_R))
    grad = QtGui.QLinearGradient(0, _ROOF, 0, _SILL)
    grad.setColorAt(0.00, _c(_BODY_TOP))
    grad.setColorAt(0.45, _c(_BODY_MID))
    grad.setColorAt(1.00, _c(_BODY_LOW))
    p.setPen(QtGui.QPen(_c(_BODY_EDGE), 1.4))
    p.setBrush(grad)
    p.drawPath(body)

    p.save()
    p.setClipPath(body)

    # ---- rear haunch: a broad highlight swelling over the back wheel -----
    hh = QtGui.QRadialGradient(_REAR_WHEEL[0] + 2, 50, 42)
    hh.setColorAt(0.0, _c("#4c4f56", 150))
    hh.setColorAt(1.0, _c("#4c4f56", 0))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(hh)
    p.drawRect(QtCore.QRectF(40, 34, 130, 48))

    # ---- glasshouse ------------------------------------------------------
    gl = QtGui.QLinearGradient(0, 10, 0, _BELT)
    gl.setColorAt(0.0, _c(_GLASS_TOP))
    gl.setColorAt(1.0, _c(_GLASS_LOW))
    p.setPen(QtGui.QPen(_c(_BODY_EDGE), 1.1))
    p.setBrush(gl)
    p.drawPath(_glass_path())
    # slim quarter window split off by the B-pillar
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_BODY_MID))
    pill = QtGui.QPainterPath()
    pill.moveTo(180, 13.2); pill.lineTo(186, 13.6)
    pill.lineTo(182, 32.6); pill.lineTo(176, 32.6)
    pill.closeSubpath()
    p.drawPath(pill)

    # ---- sharp character line sweeping up into the haunch ----------------
    p.setPen(QtGui.QPen(_c("#585d66"), 1.7))
    cl = QtGui.QPainterPath()
    cl.moveTo(258, 55)
    cl.cubicTo(224, 54, 176, 52, 122, 49)
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawPath(cl)

    # ---- side gill vent behind the front arch ---------------------------
    p.setPen(QtGui.QPen(_c(_BODY_EDGE), 1.0))
    p.setBrush(_c("#191b1f"))
    gill = QtGui.QPainterPath()
    gill.moveTo(250, 45); gill.lineTo(264, 44)
    gill.lineTo(262, 51); gill.lineTo(248, 52)
    gill.closeSubpath()
    p.drawPath(gill)

    # ---- rocker stripe along the sill ------------------------------------
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c("#15171a"))
    p.drawRect(QtCore.QRectF(110, 76.5, 150, 5.0))
    p.setBrush(_c(_STRIPE))
    p.drawRect(QtCore.QRectF(110, 76.5, 150, 1.4))

    # ---- door cut lines + door-mounted mirror ---------------------------
    p.setPen(QtGui.QPen(_c("#14161a"), 1.2))
    p.drawLine(QtCore.QPointF(176, 33), QtCore.QPointF(172, 76))
    p.drawLine(QtCore.QPointF(246, 32), QtCore.QPointF(244, 74))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_TRIM_DARK))
    p.drawRoundedRect(QtCore.QRectF(202, 39, 12, 2.8), 1.3, 1.3)

    # ---- hood heat-extractor slot ---------------------------------------
    p.setBrush(_c("#171a1e"))
    p.drawRoundedRect(QtCore.QRectF(284, 31.5, 26, 2.6), 1.2, 1.2)

    # ---- vertical tri-bar tail-light ------------------------------------
    p.setBrush(_c(_TAIL))
    for i in range(3):
        p.drawRoundedRect(QtCore.QRectF(21.5 + i * 3.4, 48, 2.6, 12.0),
                          0.9, 0.9)

    # ---- swept-back LED headlight with tri-bar signature ----------------
    hl = QtGui.QPainterPath()
    hl.moveTo(308, 40.0)
    hl.lineTo(334, 44.0)
    hl.lineTo(333, 51.5)
    hl.lineTo(307, 46.5)
    hl.closeSubpath()
    p.setBrush(_c("#1b1e22"))
    p.drawPath(hl)
    p.setPen(QtGui.QPen(_c(_HEAD), 1.5))
    for i in range(3):
        y = 42.6 + i * 2.2
        p.drawLine(QtCore.QPointF(312 + i * 1.2, y),
                   QtCore.QPointF(331, y + 1.8))

    # ---- lower grille / air intake --------------------------------------
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_GRILLE))
    p.drawRoundedRect(QtCore.QRectF(325, 58, 12, 12), 2.0, 2.0)

    # ---- dual racing stripes running hood -> roof -> deck ---------------
    # Seen at this shallow angle they read as two light bands riding the top
    # surfaces — the most instantly recognisable Mustang GT cue there is.
    p.setPen(QtGui.QPen(_c("#6f757e"), 1.5))
    p.setBrush(QtCore.Qt.NoBrush)
    for off in (0.0, 2.6):
        st = QtGui.QPainterPath()
        st.moveTo(332, 38.5 + off)
        st.cubicTo(312, 34.6 + off, 288, 32.8 + off, 258, 33.2 + off)
        p.drawPath(st)
        st2 = QtGui.QPainterPath()
        st2.moveTo(196, 12.0 + off)
        st2.cubicTo(178, 11.4 + off, 164, 12.4 + off, 150, 14.6 + off)
        p.drawPath(st2)

    p.restore()

    # ---- rim light along the upper body ---------------------------------
    # Without this a matte-black car is invisible against a dark taskbar, so
    # the top surfaces catch a cool highlight that separates it from the
    # background while keeping the paint matte.
    p.save()
    p.setClipRect(QtCore.QRectF(0, 0, DESIGN_W, 46))
    p.setPen(QtGui.QPen(_c("#8b929c", 190), 1.5))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawPath(body)
    p.restore()

    # ---- mirror sits proud of the body ----------------------------------
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_BODY_LOW))
    p.drawRoundedRect(QtCore.QRectF(244, 29.5, 9, 4.0), 1.6, 1.6)

    # ---- rear diffuser fins ---------------------------------------------
    p.setBrush(_c("#14161a"))
    p.drawRoundedRect(QtCore.QRectF(24, 74.5, 30, 8.0), 1.6, 1.6)

    # ---- quad exhaust tips ----------------------------------------------
    p.setBrush(_c(_TRIM))
    p.drawRoundedRect(QtCore.QRectF(30, 78.5, 9, 3.6), 1.4, 1.4)
    p.drawRoundedRect(QtCore.QRectF(41, 78.8, 8, 3.4), 1.4, 1.4)


# ---------------------------------------------------------------------- #
# Rasterisation (cached per size + frame)
# ---------------------------------------------------------------------- #
_cache: dict[tuple[int, int], QtGui.QImage] = {}


def render_image(px_w: int, frame_i: int) -> QtGui.QImage:
    """Rasterise ``frame_i`` at ``px_w`` logical pixels wide (cached).

    Internally drawn at ``px_w * _HIDPI * SUPERSAMPLE`` and downscaled, so edges
    are smooth and the result stays sharp on HiDPI displays.
    """
    px_w = max(8, int(px_w))
    key = (px_w, frame_i % FRAMES)
    hit = _cache.get(key)
    if hit is not None:
        return hit

    out_w = px_w * _HIDPI
    out_h = max(1, round(out_w * DESIGN_H / DESIGN_W))
    big = QtGui.QImage(out_w * SUPERSAMPLE, out_h * SUPERSAMPLE,
                       QtGui.QImage.Format_ARGB32_Premultiplied)
    big.fill(QtCore.Qt.transparent)
    p = QtGui.QPainter(big)
    p.setRenderHint(QtGui.QPainter.Antialiasing, True)
    p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
    s = (out_w * SUPERSAMPLE) / DESIGN_W
    p.scale(s, s)
    _draw(p, frame_i % FRAMES)
    p.end()

    img = big.scaled(out_w, out_h, QtCore.Qt.IgnoreAspectRatio,
                     QtCore.Qt.SmoothTransformation)
    img.setDevicePixelRatio(float(_HIDPI))
    _cache[key] = img
    return img


def samples_per_frame(px_w: int) -> int:
    """How many samples are rasterised per frame — used by tests/diagnostics."""
    out_w = max(8, int(px_w)) * _HIDPI
    out_h = max(1, round(out_w * DESIGN_H / DESIGN_W))
    return (out_w * SUPERSAMPLE) * (out_h * SUPERSAMPLE)


# ---------------------------------------------------------------------- #
# Compatibility shims so the buddy widget can treat sprites alike
# ---------------------------------------------------------------------- #
def frames_for_gait(gait: str) -> list[int]:
    return list(range(FRAMES))


def apply_overlays(rows, shades: bool = False, blink: bool = False):
    """Cars don't blink or wear shades — no-op, kept for interface parity."""
    return rows
