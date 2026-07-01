"""A custom-painted sparkline graph — the visual centrepiece of the widget.

Deliberately *not* pyqtgraph: we hand-draw with QPainter to get a modern,
clutter-free look — a smooth (Catmull-Rom) curve with a soft glow, a gradient
fill that fades to transparent, faint guide lines and a highlighted latest
point. No axes, no tick labels, no chrome.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


class Sparkline(QtWidgets.QWidget):
    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._values: list[float] = []
        self._color = QtGui.QColor("#3ddc84")
        self._grid = QtGui.QColor(255, 255, 255, 16)
        self._pref_h = 84
        self.setMinimumHeight(46)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Preferred)

    def set_height(self, h: int) -> None:
        self._pref_h = max(40, int(h))
        self.updateGeometry()

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(220, self._pref_h)

    def set_grid_color(self, color: QtGui.QColor) -> None:
        self._grid = color
        self.update()

    def set_data(self, values: list[float], color: str) -> None:
        self._values = values or []
        self._color = QtGui.QColor(color)
        self.update()

    # ------------------------------------------------------------------ #
    def _points(self, w: float, h: float) -> list[QtCore.QPointF]:
        vals = self._values
        n = len(vals)
        pad_top, pad_bot = 8.0, 4.0
        usable = max(1.0, h - pad_top - pad_bot)
        if n == 1:
            vals = [vals[0], vals[0]]
            n = 2
        step = w / (n - 1)
        pts = []
        for i, v in enumerate(vals):
            y = h - pad_bot - (max(0.0, min(100.0, v)) / 100.0) * usable
            pts.append(QtCore.QPointF(i * step, y))
        return pts

    @staticmethod
    def _smooth_path(pts: list[QtCore.QPointF]) -> QtGui.QPainterPath:
        """Catmull-Rom -> cubic Bézier for a fluid, natural curve."""
        path = QtGui.QPainterPath()
        if not pts:
            return path
        path.moveTo(pts[0])
        n = len(pts)
        for i in range(n - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2] if i + 2 < n else p2
            c1 = QtCore.QPointF(p1.x() + (p2.x() - p0.x()) / 6.0,
                                p1.y() + (p2.y() - p0.y()) / 6.0)
            c2 = QtCore.QPointF(p2.x() - (p3.x() - p1.x()) / 6.0,
                                p2.y() - (p3.y() - p1.y()) / 6.0)
            path.cubicTo(c1, c2, p2)
        return path

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        w = float(self.width())
        h = float(self.height())

        # Faint horizontal guide lines at 25/50/75%.
        grid_pen = QtGui.QPen(self._grid)
        grid_pen.setWidthF(1.0)
        painter.setPen(grid_pen)
        for frac in (0.25, 0.5, 0.75):
            y = h * frac
            painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(w, y))

        if not self._values:
            return

        pts = self._points(w, h)
        line = self._smooth_path(pts)

        # Gradient fill under the curve.
        fill = QtGui.QPainterPath(line)
        fill.lineTo(pts[-1].x(), h)
        fill.lineTo(pts[0].x(), h)
        fill.closeSubpath()
        grad = QtGui.QLinearGradient(0, 0, 0, h)
        top = QtGui.QColor(self._color)
        top.setAlpha(150)
        mid = QtGui.QColor(self._color)
        mid.setAlpha(40)
        bot = QtGui.QColor(self._color)
        bot.setAlpha(0)
        grad.setColorAt(0.0, top)
        grad.setColorAt(0.55, mid)
        grad.setColorAt(1.0, bot)
        painter.fillPath(fill, QtGui.QBrush(grad))

        # Glow (wide, translucent) then the crisp stroke.
        glow = QtGui.QColor(self._color)
        glow.setAlpha(70)
        glow_pen = QtGui.QPen(glow, 6.0)
        glow_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        glow_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.strokePath(line, glow_pen)

        stroke_pen = QtGui.QPen(self._color, 2.2)
        stroke_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        stroke_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.strokePath(line, stroke_pen)

        # Highlighted latest point.
        last = pts[-1]
        halo = QtGui.QColor(self._color)
        halo.setAlpha(60)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(last, 5.5, 5.5)
        painter.setBrush(QtGui.QColor("#ffffff"))
        painter.drawEllipse(last, 2.4, 2.4)
        painter.setBrush(self._color)
        painter.drawEllipse(last, 1.4, 1.4)
