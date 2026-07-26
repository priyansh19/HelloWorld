"""Translucent RAM-pressure smoke plume for the car buddy.

A click-through, always-on-top overlay hugging the taskbar that emits soft grey
smoke puffs from the car's exhaust. Puffs rise only about two inches above the
car, thinning as they climb and evaporating at that ceiling — a low, wide
burnout cloud rather than a screen-filling one. Density and sideways spread
scale with RAM stress (0..1), and everything stays translucent and transparent
to mouse input so it never gets in the user's way.

The overlay window is sized to just the smoke band — a strip a bit over a
thousand pixels wide that FOLLOWS the car, not the whole screen: repainting a
translucent layered window costs proportionally to its area, and both the
full-screen and full-width versions read as system-wide lag whenever the plume
was active. Puffs live in screen coordinates, so sliding the band never moves
the smoke; the window recentres only when the car nears its edge.

Kept deliberately self-contained; the buddy widget feeds it a source point and
an intensity each tick.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

_FPS_MS = 40              # 25 fps — every smoke frame re-uploads the whole
                          # band bitmap to the compositor, so the frame rate
                          # is the main lever on its cost
_MAX_PUFFS = 140          # hard cap so a pegged machine can't drown in puffs
_BASE_ALPHA = 30          # peak per-puff alpha (out of 255) — very see-through
_RISE_INCHES = 2.0        # how far above the exhaust the smoke may climb
_BAND_HEADROOM = 90       # extra window pixels above the rise cap for puff radii
_BAND_W = 1200            # band width; trailing smoke lives near the car
_RECENTER_MARGIN = 300    # recentre when the source gets this close to an edge


@dataclass
class _Puff:
    x: float
    y: float
    vx: float
    vy: float
    r: float
    grow: float
    age: float
    life: float


class SmokeOverlay(QtWidgets.QWidget):
    """A taskbar-hugging transparent band that renders the rising smoke."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowTransparentForInput |
            QtCore.Qt.X11BypassWindowManagerHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_AlwaysStackOnTop, True)

        self._puffs: list[_Puff] = []
        self._src = QtCore.QPointF(0.0, 0.0)
        self._intensity = 0.0
        self._spawn_acc = 0.0
        self._screen_geo = QtCore.QRect()
        self._rise_px = 192.0
        self._dir = -1.0          # which way the exhaust stream blows (x sign)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._step)
        self._puff_sprite: QtGui.QImage | None = None

    # ------------------------------------------------------------------ #
    def cover_screen(self, geo: QtCore.QRect) -> None:
        """Adopt the screen the car is on; the band itself follows the car.

        The rise cap is resolved in real inches via the screen's logical DPI.
        The actual window is placed/recentred lazily by :meth:`set_source`.
        """
        if geo == self._screen_geo:
            return
        self._screen_geo = QtCore.QRect(geo)
        scr = QtGui.QGuiApplication.screenAt(geo.center())
        dpi = float(scr.logicalDotsPerInch()) if scr else 96.0
        self._rise_px = _RISE_INCHES * dpi
        self._reband(geo.center().x())

    def _reband(self, center_x: float) -> None:
        geo = self._screen_geo
        if geo.isNull():
            return
        band_h = min(geo.height(), int(self._rise_px) + _BAND_HEADROOM)
        band_w = min(geo.width(), _BAND_W)
        x = int(center_x - band_w / 2)
        x = max(geo.left(), min(geo.right() - band_w + 1, x))
        self.setGeometry(x, geo.bottom() - band_h + 1, band_w, band_h)

    def set_source(self, gx: float, gy: float) -> None:
        """Exhaust tip in *global* coordinates (puffs live in screen space)."""
        self._src = QtCore.QPointF(gx, gy)
        # slide the band along only when the car approaches its edge, so the
        # window itself moves rarely rather than every frame
        if not self._screen_geo.isNull() and self.width() < self._screen_geo.width():
            if (gx < self.x() + _RECENTER_MARGIN
                    or gx > self.x() + self.width() - _RECENTER_MARGIN):
                self._reband(gx)

    def set_intensity(self, stress: float) -> None:
        self._intensity = max(0.0, min(1.0, stress))

    def set_direction(self, facing: int) -> None:
        """Car's travel direction; the stream blows out the back, opposite."""
        self._dir = -1.0 if facing >= 0 else 1.0

    def run(self, on: bool) -> None:
        if on and not self._timer.isActive():
            self._timer.start(_FPS_MS)
        elif not on and self._timer.isActive():
            self._timer.stop()
            self._puffs.clear()
            self.update()

    # ------------------------------------------------------------------ #
    def _step(self) -> None:
        dt = _FPS_MS / 1000.0
        s = self._intensity
        # Emit as soon as memory runs hot, so the first wisp is actually visible.
        emit = max(0.0, (s - 0.05) / 0.95)
        # spawn rate: a gentle wisp -> a thick, wide cloud near 100%.
        rate = emit * (10.0 + 62.0 * emit)         # puffs per second
        self._spawn_acc += rate * dt
        while self._spawn_acc >= 1.0 and len(self._puffs) < _MAX_PUFFS:
            self._spawn_acc -= 1.0
            self._spawn(emit)

        ceiling = self._src.y() - self._rise_px
        alive: list[_Puff] = []
        for p in self._puffs:
            p.age += dt
            # gone: lived out, or evaporated past the two-inch ceiling
            if p.age >= p.life or p.y + p.r < ceiling:
                continue
            # gentle buoyancy (stronger when stressed), swelling, turbulence;
            # sideways fanning grows with stress so a pegged machine gets a
            # wide, LOW burnout cloud hugging the taskbar.
            p.vy -= (3.0 + 11.0 * s) * dt
            p.vx += random.uniform(-9.0, 9.0) * dt * (0.4 + 5.0 * s)
            p.vx *= (1.0 + 0.9 * s * dt)
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.r += p.grow * dt
            alive.append(p)
        self._puffs = alive
        self.update()

    def _spawn(self, emit: float) -> None:
        # An exhaust stream, not a chimney: puffs leave the tailpipe mostly
        # HORIZONTALLY out the back of the car at tyre level, drifting only
        # gently upward. Stress adds throughput, sideways churn and lift, so a
        # burning machine reads as a burnout cloud boiling off the tyres.
        back = self._dir * random.uniform(30.0, 62.0) * (1.0 + 1.4 * emit)
        self._puffs.append(_Puff(
            x=self._src.x() + self._dir * random.uniform(0, 6),
            y=self._src.y() + random.uniform(-2, 2),
            vx=back + random.uniform(-10, 10) * emit,
            vy=-random.uniform(3.0, 12.0) - 34.0 * emit,
            r=random.uniform(5, 9) + 6.0 * emit,
            grow=random.uniform(10, 22) * (1.0 + 1.2 * emit),
            age=0.0,
            # short lives keep the cloud churning — fresh puffs appear and old
            # ones clear quickly, so intensity changes read almost immediately
            life=random.uniform(1.6, 3.0),
        ))

    # ------------------------------------------------------------------ #
    def _sprite(self) -> QtGui.QImage:
        """One pre-rendered soft puff, tinted grey.

        Radial gradients are the most expensive brush in Qt's raster engine;
        rendering the gradient once and blitting the cached image per puff is
        an order of magnitude cheaper — this is what makes the smoke afford
        able while the car drives all day.
        """
        if self._puff_sprite is None:
            size = 128
            img = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32_Premultiplied)
            img.fill(QtCore.Qt.transparent)
            p = QtGui.QPainter(img)
            p.setPen(QtCore.Qt.NoPen)
            grad = QtGui.QRadialGradient(size / 2, size / 2, size / 2)
            grad.setColorAt(0.0, QtGui.QColor(190, 192, 198, 255))
            grad.setColorAt(0.6, QtGui.QColor(170, 172, 180, 140))
            grad.setColorAt(1.0, QtGui.QColor(150, 152, 160, 0))
            p.setBrush(grad)
            p.drawEllipse(0, 0, size, size)
            p.end()
            self._puff_sprite = img
        return self._puff_sprite

    def paintEvent(self, _e: QtGui.QPaintEvent) -> None:
        if not self._puffs:
            return
        p = QtGui.QPainter(self)
        p.translate(-self.x(), -self.y())     # puffs are in screen coords
        sprite = self._sprite()
        rise = max(1.0, self._rise_px)
        src_y = self._src.y()
        for pf in self._puffs:
            frac = pf.age / pf.life
            fade = (1.0 - frac) * min(1.0, pf.age * 6.0)     # quick fade-in
            # thin out as it climbs; fully evaporated at the two-inch cap
            climb = max(0.0, min(1.0, (src_y - pf.y) / rise))
            a = _BASE_ALPHA * fade * (1.0 - climb) ** 1.15 * self._intensity
            if a <= 1.5:
                continue
            p.setOpacity(a / 255.0)
            p.drawImage(QtCore.QRectF(pf.x - pf.r, pf.y - pf.r,
                                      2 * pf.r, 2 * pf.r), sprite)
