"""Translucent RAM-pressure smoke plume for the car buddy.

A full-screen, click-through, always-on-top overlay that emits soft grey smoke
puffs from the car's exhaust. The puffs rise toward the top of the screen (the
"ceiling"), drift, swell and fade — you can see straight through them. The
plume's density and how wide it spreads scale with RAM stress (0..1): a light
wisp when memory first runs hot, a screen-filling haze near 100%. Because the
window is transparent to mouse input it never gets in the user's way.

Kept deliberately self-contained; the buddy widget feeds it a source point and
an intensity each tick.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

_FPS_MS = 33
_MAX_PUFFS = 420          # hard cap so a pegged machine can't drown in puffs
_BASE_ALPHA = 46          # peak per-puff alpha (out of 255) — very see-through


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
    """A screen-sized transparent canvas that renders the rising smoke."""

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

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self._step)

    # ------------------------------------------------------------------ #
    def cover_screen(self, geo: QtCore.QRect) -> None:
        """Resize/move to span the whole screen the car is on."""
        if geo != self._screen_geo:
            self._screen_geo = QtCore.QRect(geo)
            self.setGeometry(geo)

    def set_source(self, gx: float, gy: float) -> None:
        """Exhaust tip in *global* coordinates."""
        self._src = QtCore.QPointF(gx - self.x(), gy - self.y())

    def set_intensity(self, stress: float) -> None:
        self._intensity = max(0.0, min(1.0, stress))

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

        alive: list[_Puff] = []
        for p in self._puffs:
            p.age += dt
            if p.age >= p.life or p.y + p.r < 0:
                continue
            # buoyant rise (accelerates a touch), swelling, lazy turbulence
            p.vy -= 14.0 * dt
            # turbulence grows with stress, and puffs keep fanning sideways as
            # they climb so a pegged machine ends up hazing the whole screen.
            p.vx += random.uniform(-9.0, 9.0) * dt * (0.4 + 5.0 * s)
            p.vx *= (1.0 + 0.9 * s * dt)
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.r += p.grow * dt
            alive.append(p)
        self._puffs = alive
        self.update()

    def _spawn(self, emit: float) -> None:
        # Wider initial fan-out and faster rise as stress climbs, so at ~100%
        # the plume spreads across the screen instead of a thin ribbon.
        spread = 10.0 + 190.0 * emit
        rise = 70.0 + 130.0 * emit
        self._puffs.append(_Puff(
            x=self._src.x() + random.uniform(-4, 4),
            y=self._src.y() + random.uniform(-2, 2),
            vx=random.uniform(-spread, spread),
            vy=-rise * random.uniform(0.8, 1.2),
            r=random.uniform(8, 15),
            grow=random.uniform(20, 40) * (1.0 + emit),
            age=0.0,
            life=random.uniform(3.5, 6.5),
        ))

    # ------------------------------------------------------------------ #
    def paintEvent(self, _e: QtGui.QPaintEvent) -> None:
        if not self._puffs:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtCore.Qt.NoPen)
        h = max(1, self.height())
        for pf in self._puffs:
            frac = pf.age / pf.life
            fade = (1.0 - frac) * min(1.0, pf.age * 3.0)     # fade in then out
            # thin further as it nears the ceiling ("evaporates in the sky")
            ceil = max(0.0, min(1.0, pf.y / h))
            a = int(_BASE_ALPHA * fade * (0.35 + 0.65 * ceil) * self._intensity)
            if a <= 1:
                continue
            grad = QtGui.QRadialGradient(pf.x, pf.y, max(1.0, pf.r))
            grad.setColorAt(0.0, QtGui.QColor(190, 192, 198, a))
            grad.setColorAt(0.6, QtGui.QColor(170, 172, 180, int(a * 0.55)))
            grad.setColorAt(1.0, QtGui.QColor(150, 152, 160, 0))
            p.setBrush(grad)
            p.drawEllipse(QtCore.QPointF(pf.x, pf.y), pf.r, pf.r)
