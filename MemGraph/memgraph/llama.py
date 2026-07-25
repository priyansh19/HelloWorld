"""RunLlama — the taskbar buddy mode.

A tiny frameless always-on-top window sitting on the taskbar edge, drawing the
pixel llama from :mod:`~memgraph.buddy_logic` live:

* stride speed = CPU load (idle stroll → walk → full gallop)
* saddle-pack swells past the amber RAM threshold
* sunglasses on while the tracked LLM process is running
* panic (red tint, sweat, ``!!``) past the red threshold
* occasionally wanders a few pixels along the taskbar when relaxed

Click the llama to pop the full stat card; right-click for the mode menu.
"""

from __future__ import annotations

import random
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from .buddy_logic import (
    PALETTE,
    PANIC_TINT,
    SPRITE_H,
    SPRITE_W,
    TINT_EXEMPT,
    apply_overlays,
    frames_for_gait,
    mood_for,
)
from .config import Config
from .metrics import MetricsSampler

_SCALE_BASE = 3.0      # multiplied by cfg.llama_scale
_METRICS_MS = 1000
_MOVE_MS = 30          # ~33 fps movement stepper
# Travel speed multiplier per gait. Kept close to 1 so the llama always strolls
# at a visible, mild pace (CPU load just nudges it a bit faster).
_GAIT_SPEED = {"idle": 0.85, "walk": 1.0, "gallop": 1.6}


class LlamaBuddy(QtWidgets.QWidget):
    clicked = QtCore.Signal()
    request_settings = QtCore.Signal()
    request_quit = QtCore.Signal()
    request_mode = QtCore.Signal(str)

    def __init__(self, config: Config, sampler: MetricsSampler,
                 on_move: Optional[Callable[[int], None]] = None) -> None:
        super().__init__()
        self.cfg = config
        self.sampler = sampler
        self._on_move = on_move

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool |
                            QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self._scale = _SCALE_BASE * config.llama_scale
        self._pad_top = int(6 * config.llama_scale)  # headroom for "!!"/sweat
        self._recompute_size()

        self._mood = mood_for(0, 0, config.threshold_amber,
                              config.threshold_red, False)
        self._frame_i = 0
        self._blink = False
        self._facing = 1              # 1 → right, -1 → left
        self._drag_x: Optional[int] = None
        self._press_pos: Optional[QtCore.QPoint] = None
        self._tooltip = ""
        self._ram_pct = 0.0
        self._fs_hidden = False       # auto-hidden by a fullscreen app

        self._anim = QtCore.QTimer(self)
        self._anim.timeout.connect(self._on_anim)
        self._anim.start(self._mood.frame_ms)

        self._metrics_timer = QtCore.QTimer(self)
        self._metrics_timer.timeout.connect(self.tick)
        self._metrics_timer.start(_METRICS_MS)

        self._dock()
        self._pos_x = float(self.x())
        # Smooth, high-frequency movement independent of the sprite cadence.
        self._move_timer = QtCore.QTimer(self)
        self._move_timer.timeout.connect(self._move_step)
        self._move_timer.start(_MOVE_MS)

        self.tick()

    # ------------------------------------------------------------------ #
    # Live data → mood
    # ------------------------------------------------------------------ #
    def tick(self) -> None:
        cpu = self.sampler.cpu()
        ram = self.sampler.ram()
        proc = self.sampler.process(self.cfg.process_name)
        cpu_pct = cpu.pct if cpu.available else 0.0
        ram_pct = ram.pct if ram.available else 0.0
        self._ram_pct = ram_pct
        self._update_fullscreen_visibility()

        self._mood = mood_for(cpu_pct, ram_pct, self.cfg.threshold_amber,
                              self.cfg.threshold_red, proc.available)
        self._anim.setInterval(self._mood.frame_ms)

        tip = [f"RAM {ram_pct:.0f}%", f"CPU {cpu_pct:.0f}%"]
        if proc.available:
            tip.append(f"{self.cfg.process_name} {proc.pct:.0f}%")
        self._tooltip = "  ·  ".join(tip)
        self.setToolTip(self._tooltip)
        self.update()

    def _recompute_size(self) -> None:
        self._ox = 6.0
        w = int(SPRITE_W * self._scale + 2 * self._ox)
        h = int(SPRITE_H * self._scale) + self._pad_top
        self.setFixedSize(w, h)

    def apply_config(self, cfg: Config) -> None:
        self.cfg = cfg
        self._scale = _SCALE_BASE * cfg.llama_scale
        self._pad_top = int(6 * cfg.llama_scale)
        self._recompute_size()
        self.tick()
        self._dock()
        self._pos_x = float(self.x())

    # ------------------------------------------------------------------ #
    # Animation / traversal
    # ------------------------------------------------------------------ #
    def _on_anim(self) -> None:
        if not self.isVisible():
            return
        self._frame_i += 1
        # Occasional blink (only matters when shades are off).
        self._blink = (random.random() < 0.12)
        self.update()

    def _update_fullscreen_visibility(self) -> None:
        """Hide while a fullscreen app (video/game) is in front; restore after.

        Skipped if the user manually hid the buddy from the tray.
        """
        from ._fullscreen import fullscreen_app_active
        fs = fullscreen_app_active()
        if fs and not self._fs_hidden and self.isVisible():
            self._fs_hidden = True
            self.hide()
        elif not fs and self._fs_hidden:
            self._fs_hidden = False
            self.show()

    @staticmethod
    def _ram_speed_mult(ram_pct: float) -> float:
        """Above 70% RAM, speed rises 20% for each further 10% band.

        70-80% -> 1.2x, 80-90% -> 1.4x, 90-100% -> 1.6x, 100% -> 1.8x.
        """
        if ram_pct < 70:
            return 1.0
        bands = int((ram_pct - 70) // 10) + 1
        return min(2.0, 1.0 + 0.2 * bands)

    def _move_step(self) -> None:
        """Walk steadily across the screen, turning around at each edge.

        One full crossing takes ``llama_cross_seconds`` (~5 min) at a walk; gait
        (CPU) and high RAM speed it up. The sprite mirrors to face its travel.
        """
        if not self.isVisible() or self._drag_x is not None \
                or not self.cfg.llama_wander:
            return
        geo = self._screen_geo()
        left = geo.left()
        right = geo.right() - self.width()
        if right <= left:
            return
        px_per_sec = geo.width() / max(20, self.cfg.llama_cross_seconds)
        mult = (_GAIT_SPEED.get(self._mood.gait, 1.0)
                * self._ram_speed_mult(self._ram_pct))
        self._pos_x += self._facing * px_per_sec * mult * (_MOVE_MS / 1000.0)
        if self._pos_x <= left:
            self._pos_x, self._facing = float(left), 1
        elif self._pos_x >= right:
            self._pos_x, self._facing = float(right), -1
        self.move(int(round(self._pos_x)), self.y())

    # ------------------------------------------------------------------ #
    # Placement
    # ------------------------------------------------------------------ #
    def _screen_geo(self) -> QtCore.QRect:
        scr = self.screen() or QtWidgets.QApplication.primaryScreen()
        return scr.availableGeometry()

    def _dock(self) -> None:
        geo = self._screen_geo()
        x = self.cfg.llama_x
        if x < 0:
            x = geo.right() - self.width() - 220
        x = max(geo.left(), min(geo.right() - self.width(), x))
        self.move(x, geo.bottom() - self.height() + 1)

    def anchor_rect(self) -> QtCore.QRect:
        """Where the stat card should pop up (global coords)."""
        return QtCore.QRect(self.x(), self.y(), self.width(), self.height())

    # ------------------------------------------------------------------ #
    # Painting
    # ------------------------------------------------------------------ #
    def paintEvent(self, _e: QtGui.QPaintEvent) -> None:
        m = self._mood
        frames = frames_for_gait(m.gait)
        rows = frames[self._frame_i % len(frames)]
        rows = apply_overlays(rows, shades=m.shades,
                              blink=self._blink and not m.shades)

        p = QtGui.QPainter(self)
        s = self._scale
        ox, oy = self._ox, float(self._pad_top)
        tint = QtGui.QColor(PANIC_TINT) if m.panic else None
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch == ".":
                    continue
                col = QtGui.QColor(PALETTE.get(ch, "#f2e3c8"))
                if tint is not None and ch not in TINT_EXEMPT:
                    col = QtGui.QColor((col.red() + tint.red() * 2) // 3,
                                       (col.green() + tint.green() * 2) // 3,
                                       (col.blue() + tint.blue() * 2) // 3)
                px = rx if self._facing == 1 else (SPRITE_W - 1 - rx)
                p.fillRect(QtCore.QRectF(ox + px * s, oy + ry * s, s, s), col)

        if m.panic:
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            head_x = ox + (21 * s if self._facing == 1 else (SPRITE_W - 21) * s)
            p.setPen(QtCore.Qt.NoPen)
            p.setBrush(QtGui.QColor("#6fd9ff"))
            p.drawEllipse(QtCore.QPointF(head_x, oy + 1.0 * s), 2.5, 4)
            p.setPen(QtGui.QColor(PANIC_TINT))
            f = QtGui.QFont("Segoe UI", 10, QtGui.QFont.Black)
            p.setFont(f)
            p.drawText(QtCore.QRectF(head_x - 26, 0, 30, 14),
                       QtCore.Qt.AlignRight, "!!")

    # ------------------------------------------------------------------ #
    # Mouse: drag along the taskbar, click to open the card, menu on right
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, e: QtGui.QMouseEvent) -> None:
        if e.button() == QtCore.Qt.LeftButton:
            self._press_pos = e.globalPosition().toPoint()
            self._drag_x = self._press_pos.x() - self.x()
            e.accept()

    def mouseMoveEvent(self, e: QtGui.QMouseEvent) -> None:
        if self._drag_x is not None and e.buttons() & QtCore.Qt.LeftButton:
            geo = self._screen_geo()
            x = e.globalPosition().toPoint().x() - self._drag_x
            x = max(geo.left(), min(geo.right() - self.width(), x))
            self.move(x, self.y())
            e.accept()

    def mouseReleaseEvent(self, e: QtGui.QMouseEvent) -> None:
        if self._drag_x is None:
            return
        moved = (e.globalPosition().toPoint() - self._press_pos).manhattanLength() \
            if self._press_pos else 0
        self._drag_x = None
        self._press_pos = None
        self._pos_x = float(self.x())     # resume traversal from here
        if moved < 6:
            self.clicked.emit()
        else:
            self.cfg.llama_x = self.x()
            if self._on_move:
                self._on_move(self.x())
        e.accept()

    def contextMenuEvent(self, e: QtGui.QContextMenuEvent) -> None:
        menu = QtWidgets.QMenu(self)
        menu.addAction("Open stats", self.clicked.emit)
        menu.addSeparator()
        menu.addAction("Pinned mode", lambda: self.request_mode.emit("pinned"))
        menu.addAction("Peek mode", lambda: self.request_mode.emit("peek"))
        menu.addAction("✓ Llama mode", lambda: None)
        menu.addSeparator()
        menu.addAction("Settings…", self.request_settings.emit)
        menu.addAction("Quit MemGraph", self.request_quit.emit)
        menu.exec(e.globalPos())
