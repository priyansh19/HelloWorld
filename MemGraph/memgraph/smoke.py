"""Translucent RAM-pressure smoke plume for the car buddy.

A click-through, always-on-top overlay hugging the taskbar that emits soft grey
smoke puffs from the car's exhaust. Puffs rise only about two inches above the
car, thinning as they climb and evaporating at that ceiling — a low, wide
burnout cloud rather than a screen-filling one. Density and sideways spread
scale with RAM stress (0..1), and everything stays translucent and transparent
to mouse input so it never gets in the user's way.

The overlay window is sized to just the smoke band (screen wide, a few hundred
pixels tall) instead of the whole screen: repainting a translucent layered
window costs proportionally to its area, and the full-screen version read as
system-wide lag whenever the plume was active.

Kept deliberately self-contained; the buddy widget feeds it a source point and
an intensity each tick.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

_FPS_MS = 33
_MAX_PUFFS = 220          # hard cap so a pegged machine can't drown in puffs
_BASE_ALPHA = 46          # peak per-puff alpha (out of 255) — very see-through
_RISE_INCHES = 2.0        # how far above the exhaust the smoke may climb
_BAND_HEADROOM = 90       # extra window pixels above the rise cap for puff radii


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

    # ------------------------------------------------------------------ #
    def cover_screen(self, geo: QtCore.QRect) -> None:
        """Cover just the smoke band at the bottom of the given screen.

        The rise cap is resolved in real inches via the screen's logical DPI,
        and the window is a screen-wide strip tall enough for the cap plus a
        little headroom — far cheaper to composite than a full-screen layer.
        """
        if geo == self._screen_geo:
            return
        self._screen_geo = QtCore.QRect(geo)
        scr = QtGui.QGuiApplication.screenAt(geo.center())
        dpi = float(scr.logicalDotsPerInch()) if scr else 96.0
        self._rise_px = _RISE_INCHES * dpi
        band_h = min(geo.height(), int(self._rise_px) + _BAND_HEADROOM)
        self.setGeometry(geo.left(), geo.bottom() - band_h + 1,
                         geo.width(), band_h)

    def set_source(self, gx: float, gy: float) -> None:
        """Exhaust tip in *global* coordinates."""
        self._src = QtCore.QPointF(gx - self.x(), gy - self.y())

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
    def paintEvent(self, _e: QtGui.QPaintEvent) -> None:
        if not self._puffs:
            return
        p = QtGui.QPainter(self)
        # No antialiasing: the radial gradients are soft-edged already, and
        # skipping AA keeps this band cheap to repaint at 30 fps.
        p.setPen(QtCore.Qt.NoPen)
        rise = max(1.0, self._rise_px)
        src_y = self._src.y()
        for pf in self._puffs:
            frac = pf.age / pf.life
            fade = (1.0 - frac) * min(1.0, pf.age * 6.0)     # quick fade-in
            # thin out as it climbs; fully evaporated at the two-inch cap
            climb = max(0.0, min(1.0, (src_y - pf.y) / rise))
            a = int(_BASE_ALPHA * fade * (1.0 - climb) ** 1.15
                    * self._intensity)
            if a <= 1:
                continue
            grad = QtGui.QRadialGradient(pf.x, pf.y, max(1.0, pf.r))
            grad.setColorAt(0.0, QtGui.QColor(190, 192, 198, a))
            grad.setColorAt(0.6, QtGui.QColor(170, 172, 180, int(a * 0.55)))
            grad.setColorAt(1.0, QtGui.QColor(150, 152, 160, 0))
            p.setBrush(grad)
            p.drawEllipse(QtCore.QPointF(pf.x, pf.y), pf.r, pf.r)
