"""The two traffic cones the Mustang drifts around.

Tiny frameless, click-through, always-on-top windows standing on the taskbar
near each end of the screen. Their content is static — painted once per size —
so they cost effectively nothing while the car loops around them.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets

_ORANGE = "#f07818"
_ORANGE_DARK = "#c85a10"
_BAND = "#f5f2ea"
_BASE = "#2e2a26"


class ConeWidget(QtWidgets.QWidget):
    """One traffic cone: orange body, two reflective bands, square base."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(
            QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool |
            QtCore.Qt.WindowStaysOnTopHint |
            QtCore.Qt.WindowTransparentForInput)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)

    def set_cone_size(self, height_px: int) -> None:
        h = max(14, int(height_px))
        self.setFixedSize(max(12, int(h * 0.85)), h)

    def place(self, center_x: int, bottom_y: int) -> None:
        self.move(int(center_x - self.width() / 2),
                  int(bottom_y - self.height() + 1))

    # ------------------------------------------------------------------ #
    def paintEvent(self, _e: QtGui.QPaintEvent) -> None:
        w, h = self.width(), self.height()
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)
        p.setPen(QtCore.Qt.NoPen)

        base_h = max(2.0, h * 0.10)
        p.setBrush(QtGui.QColor(_BASE))                      # square base
        p.drawRoundedRect(QtCore.QRectF(0, h - base_h, w, base_h), 1.5, 1.5)

        body = QtGui.QPainterPath()                          # tapered body
        tip_w = w * 0.16
        body.moveTo(w / 2 - tip_w / 2, h * 0.04)
        body.lineTo(w / 2 + tip_w / 2, h * 0.04)
        body.lineTo(w * 0.86, h - base_h)
        body.lineTo(w * 0.14, h - base_h)
        body.closeSubpath()
        grad = QtGui.QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, QtGui.QColor(_ORANGE))
        grad.setColorAt(1.0, QtGui.QColor(_ORANGE_DARK))
        p.setBrush(grad)
        p.drawPath(body)

        p.setClipPath(body)                                  # two white bands
        p.setBrush(QtGui.QColor(_BAND))
        p.drawRect(QtCore.QRectF(0, h * 0.30, w, h * 0.14))
        p.drawRect(QtCore.QRectF(0, h * 0.56, w, h * 0.12))
