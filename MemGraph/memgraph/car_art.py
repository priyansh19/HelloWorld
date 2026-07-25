"""Art for the Mustang buddy: a supplied PNG if there is one, else vector art.

**Custom PNG (preferred).** Drop a transparent-background, side-on PNG of the
car at either of these paths and it is used verbatim as the sprite — no rebuild,
no code change, just restart the widget:

* ``%LOCALAPPDATA%\\MemGraph\\car.png``   (per-user, survives updates)
* ``memgraph/assets/car.png``            (shipped with the package)

The image should face **right**; the widget mirrors it when the car drives left.
Everything else keeps working — it drifts along the taskbar and smokes from
:data:`EXHAUST` as RAM climbs. See :func:`asset_path`.

**Vector fallback.** With no PNG present the car is drawn as real geometry in a
360x104 design space, traced from measured landmarks on an S550 side profile
(cowl 27.5% back from the nose, roof 43-55%, backlight base 81.5%, beltline at
79% of height). It is rasterised with antialiasing and supersampling, so it
stays crisp at any size — see :data:`SUPERSAMPLE`.

Shapes are drawn back-to-front: tyres, body (with the wheel arches subtracted so
the arch gap reads), glasshouse, then trim/lights/details.

Public surface mirrors the other sprite modules so
:class:`~memgraph.llama.LlamaBuddy` can treat them interchangeably, plus
:func:`render_image` for the raster path.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

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
SPRITE_W, SPRITE_H = 72, 21

# Supersampling factor for rasterisation: every output pixel is averaged from
# SUPERSAMPLE^2 samples, and the cache is kept at 2x display size for HiDPI.
SUPERSAMPLE = 5
_HIDPI = 2

FRAMES = 8
IS_VECTOR = True

# Exhaust tip in *sizing units*, used as the smoke plume's source.
EXHAUST = (6, 16)

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
# The cues that actually make this read as a Mustang, in order of impact:
#   1. the rear haunches and deck sit HIGHER than the door beltline, so the
#      tail is tall and compact instead of a long flat shelf;
#   2. the side glass tapers hard toward the rear into a shallow wedge;
#   3. the roof is short, with a fast drop straight into that high haunch;
#   4. a chunky overall ratio (~3.2 long : 1 tall), not a stretched coupe;
#   5. big wheels nearly filling their arches, behind red calipers.
_REAR_WHEEL = (90.0, 75.0)
_FRONT_WHEEL = (278.0, 75.0)      # 57% of length apart == 107" wheelbase
_TYRE_R = 25.0
_ARCH_R = 27.5
_RIM_R = 18.0

_SILL = 84.0               # rocker panel  (17% of height)
_BELT = 28.0               # beltline      (79% of height)
_ROOF = 9.0                # roof top      (100%)


def _body_path() -> QtGui.QPainterPath:
    """Side profile traced from measured landmarks on a real S550 profile.

    Read off the reference as fractions of overall length back from the nose:
    front axle 20%, cowl 27.5%, roof 43-55%, backlight base 81.5%, rear axle
    77%, ducktail 96.5%. Heights as fractions of overall height above ground:
    beltline 79%, cowl 77%, deck 71%, hood-at-nose 67%, rocker 17%. The long
    backlight slope and the thin band of glass near the roof are what actually
    make the shape read as a Mustang.
    """
    p = QtGui.QPainterPath()
    p.moveTo(28, _SILL)                           # rear lower corner
    p.cubicTo(20, 83, 16, 75, 16, 66)             # rear valance
    p.lineTo(16, 50)                              # tail panel
    p.cubicTo(16, 43, 19, 38, 27, 36.5)           # ducktail lip
    p.cubicTo(44, 33.5, 62, 30, 77, 27.5)         # short deck rising forward
    p.cubicTo(100, 22, 132, 14, 164, 9.5)         # LONG backlight slope
    p.lineTo(203, 9)                              # flat roof
    p.cubicTo(219, 10.5, 238, 20, 254, 30)        # heavily raked windshield
    p.lineTo(262, 30.5)                           # cowl
    p.cubicTo(292, 31, 320, 34, 336, 39)          # hood, wedging down
    p.cubicTo(342, 41, 345, 46, 345, 52)          # nose rolls over
    p.cubicTo(345, 62, 343, 72, 338, 79)          # fascia + air dam
    p.lineTo(342, 83)                             # splitter lip
    p.lineTo(330, 86)
    p.lineTo(28, 86)
    p.closeSubpath()
    return p


def _arch(cx: float, cy: float, r: float) -> QtGui.QPainterPath:
    p = QtGui.QPainterPath()
    p.addEllipse(QtCore.QRectF(cx - r, cy - r, 2 * r, 2 * r))
    return p


def _glass_path() -> QtGui.QPainterPath:
    """Side glass as a shallow wedge tapering sharply toward the rear."""
    p = QtGui.QPainterPath()
    p.moveTo(248, 29.0)                      # A-pillar base at the cowl
    p.cubicTo(236, 21, 222, 13, 206, 10.8)   # up the raked A-pillar
    p.lineTo(172, 10.4)                      # roof rail
    p.cubicTo(152, 11.8, 130, 15.6, 114, 20.6)  # C-pillar down the backlight
    p.lineTo(120, 26.0)                      # tapered quarter-window base
    p.lineTo(246, _BELT - 0.6)                # beltline
    p.closeSubpath()
    return p


def _draw_wheel(p: QtGui.QPainter, cx: float, cy: float, spin: float) -> None:
    """Big dark multi-spoke alloy with a red caliper peeking through."""
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_TYRE))
    p.drawEllipse(QtCore.QPointF(cx, cy), _TYRE_R, _TYRE_R)
    p.setPen(QtGui.QPen(_c(_TYRE_WALL), 1.2))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(cx, cy), _TYRE_R - 1.6, _TYRE_R - 1.6)

    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c("#15171a"))
    p.drawEllipse(QtCore.QPointF(cx, cy), _RIM_R, _RIM_R)

    p.setBrush(_c(_CALIPER))
    cal = QtGui.QPainterPath()
    cal.moveTo(cx, cy)
    cal.arcTo(QtCore.QRectF(cx - 11, cy - 11, 22, 22), 118, 58)
    cal.closeSubpath()
    p.drawPath(cal)
    p.setBrush(_c("#2a2d32"))
    p.drawEllipse(QtCore.QPointF(cx, cy), 8.2, 8.2)

    p.setBrush(_c(_SPOKE))
    for k in range(5):
        a = spin + k * 2 * math.pi / 5
        w = 0.30
        sp = QtGui.QPainterPath()
        sp.moveTo(cx + 4.0 * math.cos(a), cy + 4.0 * math.sin(a))
        sp.lineTo(cx + (_RIM_R - 1.2) * math.cos(a - w),
                  cy + (_RIM_R - 1.2) * math.sin(a - w))
        sp.lineTo(cx + (_RIM_R - 1.2) * math.cos(a + w),
                  cy + (_RIM_R - 1.2) * math.sin(a + w))
        sp.closeSubpath()
        p.drawPath(sp)
    p.setPen(QtGui.QPen(_c("#3c4149"), 1.0))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawEllipse(QtCore.QPointF(cx, cy), _RIM_R - 0.5, _RIM_R - 0.5)
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c("#202328"))
    p.drawEllipse(QtCore.QPointF(cx, cy), 3.4, 3.4)


def _draw(p: QtGui.QPainter, frame_i: int) -> None:
    spin = (frame_i / FRAMES) * 2 * math.pi

    _draw_wheel(p, *_REAR_WHEEL, spin=spin)
    _draw_wheel(p, *_FRONT_WHEEL, spin=spin)

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

    # ---- rear haunch: broad highlight swelling over the back wheel -------
    hh = QtGui.QRadialGradient(_REAR_WHEEL[0] + 4, 40, 42)
    hh.setColorAt(0.0, _c("#50545c", 165))
    hh.setColorAt(1.0, _c("#50545c", 0))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(hh)
    p.drawRect(QtCore.QRectF(22, 24, 130, 60))

    # ---- glasshouse ------------------------------------------------------
    gl = QtGui.QLinearGradient(0, 11, 0, _BELT)
    gl.setColorAt(0.0, _c(_GLASS_TOP))
    gl.setColorAt(1.0, _c(_GLASS_LOW))
    p.setPen(QtGui.QPen(_c(_BODY_EDGE), 1.1))
    p.setBrush(gl)
    p.drawPath(_glass_path())
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_BODY_MID))
    pill = QtGui.QPainterPath()                  # B-pillar
    pill.moveTo(126, 16.6); pill.lineTo(132, 15.6)
    pill.lineTo(130, 26.8); pill.lineTo(124, 27.0)
    pill.closeSubpath()
    p.drawPath(pill)

    # ---- character line sweeping up into the haunch ----------------------
    p.setPen(QtGui.QPen(_c("#585d66"), 1.6))
    p.setBrush(QtCore.Qt.NoBrush)
    cl = QtGui.QPainterPath()
    cl.moveTo(266, 46)
    cl.cubicTo(228, 48, 170, 47, 116, 41)
    p.drawPath(cl)

    # ---- side gill vent behind the front arch ---------------------------
    p.setPen(QtGui.QPen(_c(_BODY_EDGE), 1.0))
    p.setBrush(_c("#191b1f"))
    gill = QtGui.QPainterPath()
    gill.moveTo(254, 42); gill.lineTo(268, 41)
    gill.lineTo(267, 45); gill.lineTo(253, 46)
    gill.closeSubpath()
    p.drawPath(gill)

    # ---- rocker stripe ---------------------------------------------------
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c("#15171a"))
    p.drawRect(QtCore.QRectF(119, 78.0, 128, 5.0))
    p.setBrush(_c(_STRIPE))
    p.drawRect(QtCore.QRectF(119, 78.0, 128, 1.3))

    # ---- door cut lines + door-mounted mirror ---------------------------
    p.setPen(QtGui.QPen(_c("#14161a"), 1.2))
    p.drawLine(QtCore.QPointF(122, 26), QtCore.QPointF(119, 74))
    p.drawLine(QtCore.QPointF(250, 30), QtCore.QPointF(247, 76))
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_TRIM_DARK))
    p.drawRoundedRect(QtCore.QRectF(142, 33, 13, 2.8), 1.3, 1.3)

    # ---- hood heat-extractor slot ---------------------------------------
    p.setBrush(_c("#171a1e"))
    p.drawRoundedRect(QtCore.QRectF(280, 32.5, 28, 2.4), 1.1, 1.1)

    # ---- vertical tri-bar tail-light ------------------------------------
    p.setBrush(_c(_TAIL))
    for i in range(3):
        p.drawRoundedRect(QtCore.QRectF(22.5 + i * 4.6, 39, 3.2, 11.0),
                          0.9, 0.9)

    # ---- swept-back LED headlight with tri-bar signature ----------------
    hl = QtGui.QPainterPath()
    hl.moveTo(311, 47.0)
    hl.lineTo(338, 50.0)
    hl.lineTo(337, 57.0)
    hl.lineTo(310, 54.0)
    hl.closeSubpath()
    p.setBrush(_c("#1b1e22"))
    p.drawPath(hl)
    p.setPen(QtGui.QPen(_c(_HEAD), 1.4))
    for i in range(3):
        y = 50.0 + i * 2.2
        p.drawLine(QtCore.QPointF(317 + i * 1.3, y),
                   QtCore.QPointF(338, y + 1.0))

    # ---- lower grille / air intake --------------------------------------
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_GRILLE))
    p.drawRoundedRect(QtCore.QRectF(326, 63, 15, 12), 2.0, 2.0)

    # ---- dual racing stripes over hood and roof -------------------------
    p.setPen(QtGui.QPen(_c("#6f757e"), 1.5))
    p.setBrush(QtCore.Qt.NoBrush)
    for off in (0.0, 2.6):
        st = QtGui.QPainterPath()
        st.moveTo(334, 40.0 + off)
        st.cubicTo(314, 35.0 + off, 288, 32.0 + off, 266, 31.6 + off)
        p.drawPath(st)

    p.restore()

    # ---- rim light so a matte-black car reads on a dark taskbar ---------
    p.save()
    p.setClipRect(QtCore.QRectF(0, 0, DESIGN_W, 42))
    p.setPen(QtGui.QPen(_c("#8b929c", 190), 1.5))
    p.setBrush(QtCore.Qt.NoBrush)
    p.drawPath(body)
    p.restore()

    # ---- mirror sits proud of the body ----------------------------------
    p.setPen(QtCore.Qt.NoPen)
    p.setBrush(_c(_BODY_LOW))
    p.drawRoundedRect(QtCore.QRectF(243, 25.5, 8, 3.4), 1.5, 1.5)

    # ---- rear diffuser + quad exhaust tips ------------------------------
    p.setBrush(_c("#14161a"))
    p.drawRoundedRect(QtCore.QRectF(20, 73.0, 34, 9.0), 1.6, 1.6)
    p.setBrush(_c(_TRIM))
    p.drawRoundedRect(QtCore.QRectF(23, 76.5, 10, 3.6), 1.4, 1.4)
    p.drawRoundedRect(QtCore.QRectF(36, 76.8, 9, 3.4), 1.4, 1.4)


# ---------------------------------------------------------------------- #
# Rasterisation (cached per size + frame)
# ---------------------------------------------------------------------- #
_cache: dict[tuple[int, int], QtGui.QImage] = {}

# Where a user-supplied car picture may live. Checked in order; the first hit
# wins and replaces the drawn car entirely.
_ASSET_NAMES = ("car.png", "car.jpg", "car.jpeg", "car.webp")


def asset_path() -> Path | None:
    """The user's car picture, if they have supplied one.

    Looks in ``%LOCALAPPDATA%\\MemGraph\\`` first (per-user, survives updates)
    and then in the packaged ``assets`` directory.
    """
    roots = []
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
    if base:
        roots.append(Path(base) / "MemGraph")
    roots.append(Path(__file__).resolve().parent / "assets")
    for root in roots:
        for name in _ASSET_NAMES:
            p = root / name
            if p.is_file():
                return p
    return None


_asset_sprite: QtGui.QImage | None = None
_asset_checked = False


def _asset_image() -> QtGui.QImage | None:
    """The prepared (background-keyed, trimmed) user sprite, or None."""
    global _asset_sprite, _asset_checked
    if not _asset_checked:
        _asset_checked = True
        src = asset_path()
        if src is not None:
            from .car_asset import prepare
            try:
                img = prepare(src)
            except Exception:
                img = None            # never let a bad picture break the widget
            if img is not None and not img.isNull():
                _asset_sprite = img
    return _asset_sprite


def sprite_units() -> tuple[int, int]:
    """Sizing units for the current sprite, respecting a supplied picture's
    aspect ratio so it is never stretched."""
    art = _asset_image()
    if art is not None and art.width() > 0:
        return SPRITE_W, max(1, round(SPRITE_W * art.height() / art.width()))
    return SPRITE_W, SPRITE_H


def reload_asset() -> None:
    """Forget the cached sprite so a newly dropped picture is picked up."""
    global _asset_sprite, _asset_checked
    _asset_sprite = None
    _asset_checked = False
    _cache.clear()


def render_image(px_w: int, frame_i: int) -> QtGui.QImage:
    """Rasterise ``frame_i`` at ``px_w`` logical pixels wide (cached).

    Internally drawn at ``px_w * _HIDPI * SUPERSAMPLE`` and downscaled, so edges
    are smooth and the result stays sharp on HiDPI displays.
    """
    px_w = max(8, int(px_w))
    # A supplied picture wins outright — scale it and skip the drawn car. All
    # frames are identical (a photo has no walk cycle); the life comes from the
    # car drifting along the taskbar and the smoke plume.
    art = _asset_image()
    if art is not None:
        key = (px_w, -1)
        hit = _cache.get(key)
        if hit is None:
            out_w = px_w * _HIDPI
            out_h = max(1, round(out_w * art.height() / art.width()))
            hit = art.scaled(out_w, out_h, QtCore.Qt.IgnoreAspectRatio,
                             QtCore.Qt.SmoothTransformation)
            hit.setDevicePixelRatio(float(_HIDPI))
            _cache[key] = hit
        return hit

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
