"""The floating widget: compact glassy card with two display modes.

* **Pinned** — the card stays on screen (draggable anywhere) until you hide or
  quit it, or switch mode.
* **Peek** — the card hides at the right screen edge as a slim vertical
  ``MEMGRAPH`` tab. Click the tab and the card slides out into the foreground,
  stays for ``peek_seconds`` (default 2 min, and while you hover it), then slides
  back in.

The graph is hand-painted (see :mod:`~memgraph.sparkline`); the panel is a
glassy rounded card with a drop shadow, a hero readout and sleek per-metric bars.
"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .config import Config
from .history import History
from .metrics import Metric, MetricsSampler, color_for_level
from .sparkline import Sparkline

_THEMES = {
    "midnight": {
        "top": (26, 29, 42), "bottom": (14, 15, 23),
        "border": (255, 255, 255, 26), "inner": (255, 255, 255, 20),
        "text": "#eef1f7", "muted": "#8b93a7", "track": (255, 255, 255, 22),
        "grid": (255, 255, 255, 16), "brand": "#6f7be0",
    },
    "graphite": {
        "top": (44, 46, 52), "bottom": (26, 27, 31),
        "border": (255, 255, 255, 26), "inner": (255, 255, 255, 18),
        "text": "#f2f3f5", "muted": "#9aa0ab", "track": (255, 255, 255, 22),
        "grid": (255, 255, 255, 14), "brand": "#8a93a6",
    },
    "light": {
        "top": (252, 253, 255), "bottom": (238, 241, 248),
        "border": (10, 20, 40, 40), "inner": (255, 255, 255, 220),
        "text": "#1b2030", "muted": "#5b6473", "track": (10, 20, 40, 28),
        "grid": (10, 20, 40, 18), "brand": "#4954c9",
    },
}

_MARGIN = 16       # room around the card for the drop shadow (pinned mode)
_DRAG_SNAP = 22
_TAB_W = 24        # width of the peek tab


def _qcolor(rgb) -> QtGui.QColor:
    return QtGui.QColor(*rgb)


class SideTab(QtWidgets.QWidget):
    """Slim vertical 'MEMGRAPH' tab shown at the screen edge in peek mode."""

    clicked = QtCore.Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedWidth(_TAB_W)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._accent = QtGui.QColor("#6f7be0")

    def set_accent(self, accent: str) -> None:
        self._accent = QtGui.QColor(accent)
        self.update()

    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.LeftButton:
            self.clicked.emit()
            e.accept()

    def paintEvent(self, _e) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(0, 6, -1, -6)
        grad = QtGui.QLinearGradient(r.topLeft(), r.bottomLeft())
        grad.setColorAt(0.0, self._accent)
        grad.setColorAt(1.0, self._accent.darker(135))
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(grad)
        p.drawRoundedRect(r, 8, 8)
        p.setPen(QtGui.QColor("#ffffff"))
        f = QtGui.QFont("Segoe UI", 8, QtGui.QFont.Bold)
        f.setLetterSpacing(QtGui.QFont.AbsoluteSpacing, 2.0)
        p.setFont(f)
        p.translate(r.center())
        p.rotate(-90)
        box = QtCore.QRectF(-r.height() / 2, -r.width() / 2, r.height(), r.width())
        p.drawText(box, QtCore.Qt.AlignCenter, "MEMGRAPH")


class MiniBar(QtWidgets.QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pct = 0.0
        self._color = QtGui.QColor("#3ddc84")
        self._track = QtGui.QColor(255, 255, 255, 22)
        self.setFixedHeight(5)
        self.setMinimumWidth(36)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding,
                           QtWidgets.QSizePolicy.Fixed)

    def set_value(self, pct: float, color: str, track: QtGui.QColor) -> None:
        self._pct = max(0.0, min(100.0, pct))
        self._color = QtGui.QColor(color)
        self._track = track
        self.update()

    def paintEvent(self, _e) -> None:
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = self.rect().adjusted(0, 0, -1, -1)
        radius = r.height() / 2.0
        p.setPen(QtCore.Qt.NoPen)
        p.setBrush(self._track)
        p.drawRoundedRect(r, radius, radius)
        if self._pct <= 0:
            return
        fw = max(r.height(), r.width() * self._pct / 100.0)
        fill = QtCore.QRectF(r.x(), r.y(), fw, r.height())
        grad = QtGui.QLinearGradient(fill.left(), 0, fill.right(), 0)
        c0 = QtGui.QColor(self._color)
        c0.setAlpha(180)
        grad.setColorAt(0.0, c0)
        grad.setColorAt(1.0, self._color)
        p.setBrush(QtGui.QBrush(grad))
        p.drawRoundedRect(fill, radius, radius)


class MetricRow(QtWidgets.QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        self.label = QtWidgets.QLabel("—")
        self.label.setObjectName("rowLabel")
        self.label.setFixedWidth(58)
        self.bar = MiniBar()
        self.detail = QtWidgets.QLabel("")
        self.detail.setObjectName("rowDetail")
        self.detail.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.value = QtWidgets.QLabel("0%")
        self.value.setObjectName("rowValue")
        self.value.setFixedWidth(46)
        self.value.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        lay.addWidget(self.label)
        lay.addWidget(self.bar, 1)
        lay.addWidget(self.detail)
        lay.addWidget(self.value)

    def update_metric(self, m: Metric, cfg: Config, track: QtGui.QColor) -> None:
        self.label.setText(m.label)
        if m.available:
            level = m.level(cfg.threshold_amber, cfg.threshold_red,
                            cfg.temp_amber, cfg.temp_red)
            color = color_for_level(level)
            self.bar.show()
            self.bar.set_value(m.pct, color, track)
            self.detail.setText(m.sub_text())
            self.value.setText(m.value_text())
            self.value.setStyleSheet(f"color:{color};")
        else:
            self.bar.hide()
            self.detail.setText(m.detail or "")
            self.value.setText("n/a")
            self.value.setStyleSheet("color:#6b7280;")


class MemGraphWidget(QtWidgets.QWidget):
    request_settings = QtCore.Signal()
    request_quit = QtCore.Signal()
    request_hide = QtCore.Signal()
    request_mode = QtCore.Signal(str)

    def __init__(self, config: Config, sampler: MetricsSampler,
                 on_move: Optional[Callable[[int, int], None]] = None) -> None:
        super().__init__()
        self.cfg = config
        self.sampler = sampler
        self._on_move = on_move
        self._drag_offset: Optional[QtCore.QPoint] = None
        self.history = History(config.history_points)
        self.rows: dict[str, MetricRow] = {}
        self._peek_open = False

        self.setWindowTitle("MemGraph")
        self._apply_window_flags()
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setMinimumSize(160, 130)

        self._anim = QtCore.QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._peek_timer = QtCore.QTimer(self)
        self._peek_timer.setSingleShot(True)
        self._peek_timer.timeout.connect(self._peek_hide)

        self._build_ui()
        self._apply_theme()

        self._timer = QtCore.QTimer(self)
        self._timer.timeout.connect(self.tick)
        self._timer.start(config.refresh_ms)
        self.tick()
        self._apply_mode(initial=True)

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        outer = QtWidgets.QHBoxLayout(self)
        outer.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        outer.setSpacing(0)

        self.tab = SideTab()
        self.tab.clicked.connect(self._toggle_peek)
        self.tab.hide()
        outer.addWidget(self.tab)

        self.card = QtWidgets.QFrame()
        self.card.setObjectName("card")
        shadow = QtWidgets.QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow.setColor(QtGui.QColor(0, 0, 0, 170))
        self.card.setGraphicsEffect(shadow)
        outer.addWidget(self.card, 1)

        self.card_layout = QtWidgets.QVBoxLayout(self.card)
        self.card_layout.setContentsMargins(13, 9, 13, 11)
        self.card_layout.setSpacing(5)

        top = QtWidgets.QHBoxLayout()
        top.setSpacing(6)
        self.brand = QtWidgets.QLabel("● MEMGRAPH")
        self.brand.setObjectName("brand")
        self.menu_btn = QtWidgets.QToolButton()
        self.menu_btn.setObjectName("menuBtn")
        self.menu_btn.setText("⋯")
        self.menu_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.menu_btn.clicked.connect(self._open_menu)
        top.addWidget(self.brand)
        top.addStretch(1)
        top.addWidget(self.menu_btn)
        self.card_layout.addLayout(top)

        hero = QtWidgets.QHBoxLayout()
        self.hero_label = QtWidgets.QLabel("MEMORY")
        self.hero_label.setObjectName("heroLabel")
        self.hero_value = QtWidgets.QLabel("0%")
        self.hero_value.setObjectName("heroValue")
        self.hero_value.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        hero.addWidget(self.hero_label)
        hero.addStretch(1)
        hero.addWidget(self.hero_value)
        self.card_layout.addLayout(hero)

        self.spark = Sparkline()
        self.card_layout.addWidget(self.spark, 1)

        self.divider = QtWidgets.QFrame()
        self.divider.setObjectName("divider")
        self.divider.setFixedHeight(1)
        self.card_layout.addWidget(self.divider)

        self.rows_box = QtWidgets.QVBoxLayout()
        self.rows_box.setSpacing(5)
        self.card_layout.addLayout(self.rows_box)

    def _apply_window_flags(self) -> None:
        flags = QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool
        if self.cfg.always_on_top or self.cfg.mode == "peek":
            flags |= QtCore.Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def _apply_theme(self) -> None:
        t = _THEMES.get(self.cfg.theme, _THEMES["midnight"])
        self._theme = t
        comp = self.cfg.compact
        self.setWindowOpacity(self.cfg.opacity)
        self.spark.set_grid_color(_qcolor(t["grid"]))
        self.spark.setVisible(self.cfg.show_sparkline)
        self.spark.set_height(52 if comp else 84)
        self.tab.set_accent(t["brand"])

        self.card_layout.setContentsMargins(*((13, 9, 13, 11) if comp
                                              else (16, 12, 16, 14)))
        self.card_layout.setSpacing(5 if comp else 7)
        hero_sz = 22 if comp else 30
        self.setStyleSheet(f"""
            QLabel {{ color: {t['text']}; font-family: 'Segoe UI', sans-serif; }}
            #brand {{ color: {t['brand']}; font-size: 9px; font-weight: 700;
                      letter-spacing: 3px; }}
            #menuBtn {{ color: {t['muted']}; font-size: 15px; font-weight: 700;
                        border: none; background: transparent; padding: 0 3px; }}
            #menuBtn:hover {{ color: {t['text']}; }}
            #heroLabel {{ color: {t['muted']}; font-size: 11px; font-weight: 600;
                          letter-spacing: 2px; }}
            #heroValue {{ font-size: {hero_sz}px; font-weight: 800; }}
            #rowLabel {{ color: {t['muted']}; font-size: 10px; font-weight: 600; }}
            #rowDetail {{ color: {t['muted']}; font-size: 9px; }}
            #rowValue {{ font-size: 11px; font-weight: 700; }}
            #divider {{ background: rgba(255,255,255,0.08); }}
        """)
        self.card.update()
        self.update()

    def paintEvent(self, _e: QtGui.QPaintEvent) -> None:
        t = self._theme
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        rect = QtCore.QRectF(self.card.geometry())
        grad = QtGui.QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, _qcolor(t["top"]))
        grad.setColorAt(1.0, _qcolor(t["bottom"]))
        p.setBrush(QtGui.QBrush(grad))
        p.setPen(QtGui.QPen(_qcolor(t["border"]), 1.2))
        p.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 16, 16)
        hl = QtGui.QPen(_qcolor(t["inner"]), 1.0)
        p.setPen(hl)
        p.drawLine(rect.left() + 12, rect.top() + 1.5,
                   rect.right() - 12, rect.top() + 1.5)

    # ------------------------------------------------------------------ #
    def tick(self) -> None:
        metrics = self.sampler.sample(self.cfg.enabled_metrics,
                                      self.cfg.process_name)
        if not metrics:
            self.hero_value.setText("—")
            return
        primary = metrics[0]
        pct = primary.pct if primary.available else 0.0
        self.history.append(pct)
        level = primary.level(self.cfg.threshold_amber, self.cfg.threshold_red,
                              self.cfg.temp_amber, self.cfg.temp_red)
        color = color_for_level(level)
        self.hero_label.setText(primary.label.upper())
        self.hero_value.setText(primary.value_text())
        self.hero_value.setStyleSheet(f"color:{color};")
        self.spark.set_data(self.history.values(), color)
        self._sync_rows(metrics)
        self._fit_to_content()

    def _fit_to_content(self) -> None:
        lay = self.layout()
        if lay is None:
            return
        lay.activate()
        peek = self.cfg.mode == "peek"
        w = self.cfg.width + (_TAB_W if peek else 2 * _MARGIN)
        h = self.sizeHint().height()
        if abs(self.width() - w) > 1 or abs(self.height() - h) > 2:
            self.resize(w, h)
            if peek:
                self._redock(animate=False)

    def _sync_rows(self, metrics: list[Metric]) -> None:
        track = _qcolor(self._theme["track"])
        keys = [m.key for m in metrics]
        for key in list(self.rows):
            if key not in keys:
                w = self.rows.pop(key)
                self.rows_box.removeWidget(w)
                w.deleteLater()
        for m in metrics:
            row = self.rows.get(m.key)
            if row is None:
                row = MetricRow(self.card)
                self.rows[m.key] = row
                self.rows_box.addWidget(row)
            row.update_metric(m, self.cfg, track)

    # ------------------------------------------------------------------ #
    def apply_config(self, cfg: Config) -> None:
        self.cfg = cfg
        self.history.resize(cfg.history_points)
        self._apply_window_flags()
        self.show()
        self._apply_theme()
        self._timer.setInterval(cfg.refresh_ms)
        self.tick()
        self._apply_mode()

    # -- modes ---------------------------------------------------------- #
    def _apply_mode(self, initial: bool = False) -> None:
        peek = self.cfg.mode == "peek"
        self.tab.setVisible(peek)
        outer = self.layout()
        if peek:
            outer.setContentsMargins(0, _MARGIN // 2, 0, _MARGIN // 2)
        else:
            outer.setContentsMargins(_MARGIN, _MARGIN, _MARGIN, _MARGIN)
        self._fit_to_content()
        if peek:
            self._peek_open = False
            self._peek_timer.stop()
            self._redock(animate=False)
        else:
            self._peek_timer.stop()
            self._restore_position()

    def _screen_geo(self) -> QtCore.QRect:
        scr = self.screen() or QtWidgets.QApplication.primaryScreen()
        return scr.availableGeometry()

    def _peek_x(self, opened: bool) -> int:
        g = self._screen_geo()
        right = g.x() + g.width()
        return right - self.width() if opened else right - _TAB_W

    def _peek_y(self) -> int:
        g = self._screen_geo()
        y = self.cfg.pos_y if self.cfg.pos_y >= 0 else g.y() + 80
        return max(g.y(), min(g.y() + g.height() - self.height(), y))

    def _redock(self, animate: bool = True) -> None:
        target = QtCore.QPoint(self._peek_x(self._peek_open), self._peek_y())
        if animate:
            self._animate_to(target)
        else:
            self.move(target)

    def _animate_to(self, target: QtCore.QPoint) -> None:
        self._anim.stop()
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(target)
        self._anim.start()

    def _toggle_peek(self) -> None:
        if self._peek_open:
            self._peek_hide()
        else:
            self._peek_show()

    def _peek_show(self) -> None:
        self._peek_open = True
        self.show()
        self.raise_()
        self._animate_to(QtCore.QPoint(self._peek_x(True), self._peek_y()))
        self._peek_timer.start(self.cfg.peek_seconds * 1000)

    def _peek_hide(self) -> None:
        self._peek_open = False
        self._peek_timer.stop()
        self._animate_to(QtCore.QPoint(self._peek_x(False), self._peek_y()))

    def enterEvent(self, _e) -> None:
        # Keep the panel open while the pointer is over it.
        if self.cfg.mode == "peek" and self._peek_open:
            self._peek_timer.stop()

    def leaveEvent(self, _e) -> None:
        if self.cfg.mode == "peek" and self._peek_open:
            self._peek_timer.start(self.cfg.peek_seconds * 1000)

    # -- dragging / placement ------------------------------------------ #
    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.LeftButton:
            self._drag_offset = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e: QtGui.QMouseEvent) -> None:
        if self._drag_offset is not None and e.buttons() & QtCore.Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self._drag_offset)
            e.accept()

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent) -> None:
        if self._drag_offset is None:
            return
        self._drag_offset = None
        if self.cfg.mode == "peek":
            # Re-dock to the edge, keeping the new vertical position.
            self.cfg.pos_y = self.y()
            self._redock(animate=True)
            if self._on_move:
                self._on_move(self.x(), self.y())
        else:
            if self.cfg.snap_to_edges:
                self._snap_to_edge()
            if self._on_move:
                self._on_move(self.x(), self.y())
        e.accept()

    def _snap_to_edge(self) -> None:
        screen = self._screen_geo()
        x, y = self.x(), self.y()
        if abs(x + _MARGIN - screen.left()) < _DRAG_SNAP:
            x = screen.left() - _MARGIN
        elif abs(screen.right() - (x + self.width() - _MARGIN)) < _DRAG_SNAP:
            x = screen.right() - self.width() + _MARGIN
        if abs(y + _MARGIN - screen.top()) < _DRAG_SNAP:
            y = screen.top() - _MARGIN
        elif abs(screen.bottom() - (y + self.height() - _MARGIN)) < _DRAG_SNAP:
            y = screen.bottom() - self.height() + _MARGIN
        self.move(x, y)

    def _restore_position(self) -> None:
        if self.cfg.pos_x >= 0 and self.cfg.pos_y >= 0:
            self.move(self.cfg.pos_x, self.cfg.pos_y)
        else:
            screen = self._screen_geo()
            self.move(screen.right() - self.width() + _MARGIN - 12,
                      screen.top() + 24)

    # -- menu ----------------------------------------------------------- #
    def contextMenuEvent(self, e: QtGui.QContextMenuEvent) -> None:
        self._popup(e.globalPos())

    def _open_menu(self) -> None:
        self._popup(self.menu_btn.mapToGlobal(
            QtCore.QPoint(0, self.menu_btn.height())))

    def _popup(self, global_pos: QtCore.QPoint) -> None:
        menu = QtWidgets.QMenu(self)
        peek = self.cfg.mode == "peek"
        a_pin = menu.addAction("✓ Pinned mode" if not peek else "Pinned mode")
        a_pin.triggered.connect(lambda: self.request_mode.emit("pinned"))
        a_peek = menu.addAction("✓ Peek mode (auto-hide)" if peek
                                else "Peek mode (auto-hide)")
        a_peek.triggered.connect(lambda: self.request_mode.emit("peek"))
        menu.addSeparator()
        menu.addAction("Settings…", self.request_settings.emit)
        menu.addAction("Hide to tray", self.request_hide.emit)
        menu.addSeparator()
        menu.addAction("Quit MemGraph", self.request_quit.emit)
        menu.exec(global_pos)
