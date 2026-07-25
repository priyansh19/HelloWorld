"""A custom-painted sparkline graph.

Two looks from one widget:

* **full** — the large hero graph: smooth Catmull-Rom curve, soft glow, gradient
  fill, faint guides and a highlighted latest point.
* **compact (boxed)** — a small Task-Manager-style tile graph: a bordered box
  with a filled area curve inside, no glow/dot, cheap to paint many at once.

No image assets — everything is drawn with QPainter.
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
        self._compact = False
        self._box_bg = QtGui.QColor(0, 0, 0, 60)
        self._box_border = QtGui.QColor(255, 255, 255, 30)
        self.setMinimumHeight(30)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Preferred)

    def set_height(self, h: int) -> None:
        self._pref_h = max(28, int(h))
        self.updateGeometry()

    def set_compact(self, on: bool) -> None:
        self._compact = on

    def set_box_colors(self, bg: QtGui.QColor, border: QtGui.QColor) -> None:
        self._box_bg, self._box_border = bg, border

    def set_grid_color(self, color: QtGui.QColor) -> None:
        self._grid = color
        self.update()

    def set_data(self, values: list[float], color: str) -> None:
        self._values = values or []
        self._color = QtGui.QColor(color)
        self.update()

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(220, self._pref_h)

    # ------------------------------------------------------------------ #
    def _points(self, x0: float, y0: float, w: float, h: float) -> list[QtCore.QPointF]:
        vals = self._values
        n = len(vals)
        pad_top, pad_bot = (3.0, 2.0) if self._compact else (8.0, 4.0)
        usable = max(1.0, h - pad_top - pad_bot)
        if n == 1:
            vals = [vals[0], vals[0]]
            n = 2
        step = w / (n - 1)
        pts = []
        for i, v in enumerate(vals):
            y = y0 + h - pad_bot - (max(0.0, min(100.0, v)) / 100.0) * usable
            pts.append(QtCore.QPointF(x0 + i * step, y))
        return pts

    @staticmethod
    def _smooth_path(pts: list[QtCore.QPointF]) -> QtGui.QPainterPath:
        path = QtGui.QPainterPath()
        if not pts:
            return path
        path.moveTo(pts[0])
        n = len(pts)
        for i in range(n - 1):
            p0 = pts[i - 1] if i > 0 else pts[i]
            p1, p2 = pts[i], pts[i + 1]
            p3 = pts[i + 2] if i + 2 < n else p2
            c1 = QtCore.QPointF(p1.x() + (p2.x() - p0.x()) / 6.0,
                                p1.y() + (p2.y() - p0.y()) / 6.0)
            c2 = QtCore.QPointF(p2.x() - (p3.x() - p1.x()) / 6.0,
                                p2.y() - (p3.y() - p1.y()) / 6.0)
            path.cubicTo(c1, c2, p2)
        return path

    def paintEvent(self, _e: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        if self._compact:
            self._paint_compact(painter)
        else:
            self._paint_full(painter)

    # -- compact boxed tile -------------------------------------------- #
    def _paint_compact(self, p: QtGui.QPainter) -> None:
        box = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(self._box_bg)
        p.drawRoundedRect(box, 4, 4)

        inner = box.adjusted(1.5, 1.5, -1.5, -1.5)
        p.save()
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(inner, 3, 3)
        p.setClipPath(clip)

        # a couple of faint guide lines
        gp = QtGui.QPen(self._grid, 1.0)
        p.setPen(gp)
        for frac in (0.33, 0.66):
            y = inner.top() + inner.height() * frac
            p.drawLine(QtCore.QPointF(inner.left(), y),
                       QtCore.QPointF(inner.right(), y))

        if self._values:
            pts = self._points(inner.left(), inner.top(),
                               inner.width(), inner.height())
            line = self._smooth_path(pts)
            fill = QtGui.QPainterPath(line)
            fill.lineTo(pts[-1].x(), inner.bottom())
            fill.lineTo(pts[0].x(), inner.bottom())
            fill.closeSubpath()
            grad = QtGui.QLinearGradient(0, inner.top(), 0, inner.bottom())
            top = QtGui.QColor(self._color); top.setAlpha(150)
            bot = QtGui.QColor(self._color); bot.setAlpha(10)
            grad.setColorAt(0.0, top)
            grad.setColorAt(1.0, bot)
            p.fillPath(fill, QtGui.QBrush(grad))
            pen = QtGui.QPen(self._color, 1.5)
            pen.setJoinStyle(QtCore.Qt.RoundJoin)
            p.strokePath(line, pen)
        p.restore()

        p.setPen(QtGui.QPen(self._box_border, 1.0))
        p.setBrush(QtCore.Qt.NoBrush)
        p.drawRoundedRect(box, 4, 4)

    # -- full hero graph ----------------------------------------------- #
    def _paint_full(self, painter: QtGui.QPainter) -> None:
        w = float(self.width())
        h = float(self.height())
        grid_pen = QtGui.QPen(self._grid)
        grid_pen.setWidthF(1.0)
        painter.setPen(grid_pen)
        for frac in (0.25, 0.5, 0.75):
            y = h * frac
            painter.drawLine(QtCore.QPointF(0, y), QtCore.QPointF(w, y))
        if not self._values:
            return
        pts = self._points(0, 0, w, h)
        line = self._smooth_path(pts)
        fill = QtGui.QPainterPath(line)
        fill.lineTo(pts[-1].x(), h)
        fill.lineTo(pts[0].x(), h)
        fill.closeSubpath()
        grad = QtGui.QLinearGradient(0, 0, 0, h)
        top = QtGui.QColor(self._color); top.setAlpha(150)
        mid = QtGui.QColor(self._color); mid.setAlpha(40)
        bot = QtGui.QColor(self._color); bot.setAlpha(0)
        grad.setColorAt(0.0, top)
        grad.setColorAt(0.55, mid)
        grad.setColorAt(1.0, bot)
        painter.fillPath(fill, QtGui.QBrush(grad))
        glow = QtGui.QColor(self._color); glow.setAlpha(70)
        glow_pen = QtGui.QPen(glow, 6.0)
        glow_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        glow_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.strokePath(line, glow_pen)
        stroke_pen = QtGui.QPen(self._color, 2.2)
        stroke_pen.setJoinStyle(QtCore.Qt.RoundJoin)
        stroke_pen.setCapStyle(QtCore.Qt.RoundCap)
        painter.strokePath(line, stroke_pen)
        last = pts[-1]
        halo = QtGui.QColor(self._color); halo.setAlpha(60)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(last, 5.5, 5.5)
        painter.setBrush(QtGui.QColor("#ffffff"))
        painter.drawEllipse(last, 2.4, 2.4)
        painter.setBrush(self._color)
        painter.drawEllipse(last, 1.4, 1.4)
