"""The floating, frameless, always-on-top graph widget.

This is the visible surface of MemGraph: a compact rounded panel showing a
live scrolling area-graph of the primary metric plus a big percentage readout
and one row per enabled metric. The whole panel is draggable so it can be
placed anywhere on the desktop, and its position is persisted.

Requires PySide6 + pyqtgraph at runtime (not needed for the unit tests).
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets
import pyqtgraph as pg

from .config import Config
from .history import History
from .metrics import MetricsSampler, Sample, color_for_level

# Theme palettes: (panel bg, text, muted text, graph bg, grid)
_THEMES = {
    "dark": {
        "panel": (22, 24, 30, 235),
        "text": "#f2f4f8",
        "muted": "#9aa4b2",
        "graph_bg": (14, 16, 22),
        "border": "#2a2e38",
    },
    "light": {
        "panel": (245, 246, 250, 240),
        "text": "#1c1f26",
        "muted": "#5b6473",
        "graph_bg": (255, 255, 255),
        "border": "#d6dae2",
    },
}

_DRAG_MARGIN = 24  # px from a screen edge to trigger snap


class MetricRow(QtWidgets.QWidget):
    """A single metric line: label, coloured percent, and used/total text."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.label = QtWidgets.QLabel("—")
        self.label.setObjectName("metricLabel")
        self.pct = QtWidgets.QLabel("0%")
        self.pct.setObjectName("metricPct")
        self.pct.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.detail = QtWidgets.QLabel("")
        self.detail.setObjectName("metricDetail")
        self.detail.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        layout.addWidget(self.label)
        layout.addStretch(1)
        layout.addWidget(self.detail)
        layout.addWidget(self.pct)

    def update_reading(self, reading, amber: int, red: int) -> None:
        self.label.setText(reading.label)
        if reading.available:
            level = reading.level(amber, red)
            color = color_for_level(level)
            self.pct.setText(f"{reading.percent:.0f}%")
            self.pct.setStyleSheet(f"color: {color}; font-weight: 600;")
            self.detail.setText(reading.readout())
        else:
            self.pct.setText("n/a")
            self.pct.setStyleSheet("color: #6b7280;")
            self.detail.setText(reading.detail or "")


class MemGraphWidget(QtWidgets.QWidget):
    """Frameless draggable panel with a live graph and metric rows."""

    request_settings = QtCore.Signal()
    request_quit = QtCore.Signal()

    def __init__(self, config: Config, sampler: MetricsSampler,
                 on_move: Optional[Callable[[int, int], None]] = None) -> None:
        super().__init__()
        self.cfg = config
        self.sampler = sampler
        self._on_move = on_move
        self._drag_offset: Optional[QtCore.QPoint] = None
        self.history = History(config.history_points)

        self.setWindowTitle("MemGraph")
        self._apply_window_flags()
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setMinimumSize(200, 120)
        self.resize(config.width, config.height)

        self._build_ui()
        self._apply_theme()
        self._restore_position()

        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(config.refresh_ms)
        self.tick()  # paint immediately instead of waiting one interval

    # ------------------------------------------------------------------ #
    # UI construction
    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(4)

        # Header: title + big percent
        header = QtWidgets.QHBoxLayout()
        self.title = QtWidgets.QLabel("Memory")
        self.title.setObjectName("title")
        self.big_pct = QtWidgets.QLabel("0%")
        self.big_pct.setObjectName("bigPct")
        self.big_pct.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        header.addWidget(self.title)
        header.addStretch(1)
        header.addWidget(self.big_pct)
        root.addLayout(header)

        # Live graph
        self.plot = pg.PlotWidget()
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.setYRange(0, 100, padding=0)
        self.plot.getAxis("left").setWidth(24)
        self.plot.getAxis("bottom").hide()
        self.plot.setLabel("left", "")
        self.curve = self.plot.plot([], [], fillLevel=0, antialias=True)
        root.addWidget(self.plot, stretch=1)

        # Metric rows
        self.rows: dict[str, MetricRow] = {}
        self.rows_container = QtWidgets.QVBoxLayout()
        self.rows_container.setSpacing(2)
        root.addLayout(self.rows_container)

    def _apply_window_flags(self) -> None:
        flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool
        if self.cfg.always_on_top:
            flags |= QtCore.Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _apply_theme(self) -> None:
        t = _THEMES.get(self.cfg.theme, _THEMES["dark"])
        self._theme = t
        self.setWindowOpacity(self.cfg.opacity)
        pr, pg_, pb, pa = t["panel"]
        self.setStyleSheet(f"""
            QWidget {{ color: {t['text']}; font-family: 'Segoe UI', sans-serif; }}
            #title {{ font-size: 12px; color: {t['muted']}; letter-spacing: 1px;
                      text-transform: uppercase; }}
            #bigPct {{ font-size: 26px; font-weight: 700; }}
            #metricLabel {{ font-size: 11px; color: {t['muted']}; }}
            #metricPct {{ font-size: 11px; }}
            #metricDetail {{ font-size: 10px; color: {t['muted']}; }}
        """)
        self.plot.setBackground(t["graph_bg"])
        self.update()  # repaint rounded panel

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        """Draw the rounded translucent panel behind the child widgets."""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        r, g, b, a = self._theme["panel"]
        painter.setBrush(QtGui.QColor(r, g, b, a))
        pen = QtGui.QPen(QtGui.QColor(self._theme["border"]))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, 14, 14)
        super().paintEvent(event)

    # ------------------------------------------------------------------ #
    # Live update
    # ------------------------------------------------------------------ #
    def tick(self) -> None:
        sample = self.sampler.sample(
            self.cfg.show_ram, self.cfg.show_vram,
            self.cfg.show_process, self.cfg.process_name,
        )
        if sample is None:
            self.big_pct.setText("—")
            return
        self._render_sample(sample)

    def _render_sample(self, sample: Sample) -> None:
        primary = sample.primary
        pct = primary.percent if primary.available else 0.0
        self.history.append(pct)

        self.title.setText(primary.label)
        level = primary.level(self.cfg.threshold_amber, self.cfg.threshold_red)
        color = color_for_level(level)
        self.big_pct.setText(f"{pct:.0f}%" if primary.available else "n/a")
        self.big_pct.setStyleSheet(f"color: {color}; font-weight: 700;")

        ys = self.history.values()
        xs = list(range(len(ys)))
        fill = QtGui.QColor(color)
        fill.setAlpha(70)
        self.curve.setData(xs, ys, pen=pg.mkPen(color, width=2),
                           fillLevel=0, brush=fill)

        self._sync_rows(sample.all_readings())

    def _sync_rows(self, readings) -> None:
        keys = [r.key for r in readings]
        # Remove rows no longer shown
        for key in list(self.rows):
            if key not in keys:
                w = self.rows.pop(key)
                self.rows_container.removeWidget(w)
                w.deleteLater()
        # Add/update
        for reading in readings:
            row = self.rows.get(reading.key)
            if row is None:
                row = MetricRow(self)
                self.rows[reading.key] = row
                self.rows_container.addWidget(row)
            row.update_reading(reading, self.cfg.threshold_amber,
                               self.cfg.threshold_red)

    # ------------------------------------------------------------------ #
    # Runtime reconfiguration (called after settings change)
    # ------------------------------------------------------------------ #
    def apply_config(self, cfg: Config) -> None:
        self.cfg = cfg
        self.history.resize(cfg.history_points)
        self._apply_window_flags()
        self.show()  # re-show needed after changing window flags
        self._apply_theme()
        self._timer.setInterval(cfg.refresh_ms)
        self.tick()

    # ------------------------------------------------------------------ #
    # Dragging + placement
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if event.button() == QtCore.Qt.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & QtCore.Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._drag_offset is not None:
            self._drag_offset = None
            if self.cfg.snap_to_edges:
                self._snap_to_edge()
            pos = self.pos()
            if self._on_move:
                self._on_move(pos.x(), pos.y())
            event.accept()

    def _snap_to_edge(self) -> None:
        screen = self.screen().availableGeometry()
        x, y = self.x(), self.y()
        if abs(x - screen.left()) < _DRAG_MARGIN:
            x = screen.left()
        elif abs(screen.right() - (x + self.width())) < _DRAG_MARGIN:
            x = screen.right() - self.width()
        if abs(y - screen.top()) < _DRAG_MARGIN:
            y = screen.top()
        elif abs(screen.bottom() - (y + self.height())) < _DRAG_MARGIN:
            y = screen.bottom() - self.height()
        self.move(x, y)

    def _restore_position(self) -> None:
        if self.cfg.pos_x >= 0 and self.cfg.pos_y >= 0:
            self.move(self.cfg.pos_x, self.cfg.pos_y)
        else:
            # Default: top-right corner with a small margin.
            screen = QtWidgets.QApplication.primaryScreen().availableGeometry()
            self.move(screen.right() - self.width() - 24, screen.top() + 24)

    # ------------------------------------------------------------------ #
    # Context menu
    # ------------------------------------------------------------------ #
    def _show_menu(self, pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("Settings…", self.request_settings.emit)
        menu.addSeparator()
        menu.addAction("Quit MemGraph", self.request_quit.emit)
        menu.exec(self.mapToGlobal(pos))
