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
import threading
from typing import Callable, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from . import buddy_logic, car3d, car_art
from .buddy_logic import mood_for
from .config import Config
from .drive_logic import Driver, DriveState
from .metrics import MetricsSampler


def _sprite_module(character: str):
    """The art module for the chosen character ("tortoise" or "car").

    The car prefers the baked 3D atlas (real model, yaw ring, spinning
    wheels); the vector drawing remains as the fallback for source builds
    without the baked assets.
    """
    if character == "car":
        return car3d if car3d.available() else car_art
    return buddy_logic

_SCALE_BASE = 1.0      # px per sprite cell, multiplied by cfg.llama_scale
                       # (the tortoise sprite is high-resolution: 54x34 cells)
_METRICS_MS = 1000
_MOVE_MS = 16          # ~60 fps movement stepper (real dt measured per step)
# Travel speed multiplier per gait. Kept close to 1 so the llama always strolls
# at a visible, mild pace (CPU load just nudges it a bit faster).
_GAIT_SPEED = {"idle": 0.85, "walk": 1.0, "gallop": 1.6}
# A car should cruise, not creep — the Mustang drifts along the taskbar
# noticeably faster than the tortoise walks.
_CAR_DRIFT_SPEED = 3.0


class LlamaBuddy(QtWidgets.QWidget):
    clicked = QtCore.Signal()
    request_settings = QtCore.Signal()
    request_quit = QtCore.Signal()
    request_mode = QtCore.Signal(str)
    request_character = QtCore.Signal(str)   # "car" | "tortoise"
    request_smoke = QtCore.Signal(bool)      # toggle the RAM smoke plume

    def __init__(self, config: Config, sampler: MetricsSampler,
                 on_move: Optional[Callable[[int], None]] = None) -> None:
        super().__init__()
        self.cfg = config
        self.sampler = sampler
        self._on_move = on_move

        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Tool |
                            QtCore.Qt.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self._art = _sprite_module(config.buddy_character)
        self._scale = _SCALE_BASE * config.llama_scale
        self._pad_top = int(6 * config.llama_scale)  # headroom for "!!"/sweat
        self._smoke = None            # created lazily for the car character
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

        # Metrics are sampled in a daemon thread: the process-table scan can
        # take >100 ms on a busy system, which reads as a once-a-second hitch
        # in the car's motion if run on the GUI thread. tick() only consumes
        # the latest sampled values.
        self._sampled = (0.0, 0.0, False)
        self._sampler_stop = threading.Event()
        threading.Thread(target=self._sample_loop, daemon=True).start()
        self._metrics_timer = QtCore.QTimer(self)
        self._metrics_timer.timeout.connect(self.tick)
        self._metrics_timer.start(_METRICS_MS)

        self._dock()
        self._pos_x = float(self.x())
        # 3D car driving state (position/yaw/wheel spin), advanced pure-logic
        # side so the park/drift behaviour is unit-testable.
        self._driver = Driver(park_below=config.car_park_below)
        self._drive = DriveState(x=float(self.x()))
        # Smooth, high-frequency movement independent of the sprite cadence.
        # PreciseTimer + measured dt: Windows coalesces coarse timers, and a
        # fixed-dt assumption turns that jitter into visible speed surging.
        self._move_clock = QtCore.QElapsedTimer()
        self._move_clock.start()
        self._move_timer = QtCore.QTimer(self)
        self._move_timer.setTimerType(QtCore.Qt.PreciseTimer)
        self._move_timer.timeout.connect(self._move_step)
        self._move_timer.start(_MOVE_MS)
        self._warm_frames()

        self.tick()

    # ------------------------------------------------------------------ #
    # Live data → mood
    # ------------------------------------------------------------------ #
    def _sample_loop(self) -> None:
        """Daemon thread: keep the latest cpu/ram/process readings fresh."""
        while not self._sampler_stop.wait(_METRICS_MS / 1000.0):
            try:
                cpu = self.sampler.cpu()
                ram = self.sampler.ram()
                proc = self.sampler.process(self.cfg.process_name)
                self._sampled = (cpu.pct if cpu.available else 0.0,
                                 ram.pct if ram.available else 0.0,
                                 proc.available)
            except Exception:
                pass

    def tick(self) -> None:
        cpu_pct, ram_pct, proc_avail = self._sampled
        self._ram_pct = ram_pct
        self._update_fullscreen_visibility()

        self._mood = mood_for(cpu_pct, ram_pct, self.cfg.threshold_amber,
                              self.cfg.threshold_red, proc_avail)
        self._anim.setInterval(self._mood.frame_ms)

        tip = [f"RAM {ram_pct:.0f}%", f"CPU {cpu_pct:.0f}%"]
        if proc_avail:
            tip.append(f"{self.cfg.process_name} running")
        self._tooltip = "  ·  ".join(tip)
        self.setToolTip(self._tooltip)
        self._update_smoke(self._mood.stress)
        self.update()

    def _sprite_units(self) -> tuple[int, int]:
        """Sprite width/height in sizing units — a supplied picture may set its
        own aspect ratio, so ask the art module when it can tell us."""
        fn = getattr(self._art, "sprite_units", None)
        if fn is not None:
            return fn()
        return self._art.SPRITE_W, self._art.SPRITE_H

    def _recompute_size(self) -> None:
        self._ox = 6.0
        sw, sh = self._sprite_units()
        w = int(sw * self._scale + 2 * self._ox)
        h = int(sh * self._scale) + self._pad_top
        self.setFixedSize(w, h)

    def apply_config(self, cfg: Config) -> None:
        self.cfg = cfg
        self._art = _sprite_module(cfg.buddy_character)
        self._scale = _SCALE_BASE * cfg.llama_scale
        self._pad_top = int(6 * cfg.llama_scale)
        self._recompute_size()
        if cfg.buddy_character != "car":
            self._stop_smoke()
        self._driver = Driver(park_below=cfg.car_park_below)
        self.tick()
        self._dock()
        self._pos_x = float(self.x())
        self._drive.x = float(self.x())
        self._warm_frames()

    def _warm_frames(self) -> None:
        """Pre-scale atlas frames for the current size so painting never has
        to scale on demand — the first drift/turn stays hitch-free. The two
        driving headings are warmed immediately; the rest of the turn ring is
        spread across idle timer slots."""
        if self._art is not car3d or not car3d.available():
            return
        sw, _ = self._sprite_units()
        px_w = int(round(sw * self._scale))
        car3d.warm(px_w)                     # driving headings, all spins
        a = car3d.atlas()
        pending = [y for y in range(a.frames) if y not in (0, a.frames // 2)]

        def warm_next() -> None:
            if pending:
                car3d.warm(px_w, [pending.pop()])
                QtCore.QTimer.singleShot(50, warm_next)

        QtCore.QTimer.singleShot(200, warm_next)

    # ------------------------------------------------------------------ #
    # RAM "burnout" smoke (car character only)
    # ------------------------------------------------------------------ #
    def _stop_smoke(self) -> None:
        if self._smoke is not None:
            self._smoke.run(False)
            self._smoke.hide()

    def _update_smoke(self, stress: float) -> None:
        """Puff grey smoke from the exhaust in proportion to RAM stress.

        While the 3D car is driving there is always at least a light exhaust
        stream, so the tailpipe visibly breathes even before memory runs hot;
        RAM stress then thickens it into the burnout cloud.
        """
        if self.cfg.buddy_character != "car" or not self.cfg.car_smoke:
            self._stop_smoke()
            return
        if self._art is car3d and not self._drive.parked:
            stress = max(stress, 0.16)
        if stress <= 0.0 and self._smoke is None:
            return
        if self._smoke is None:
            from .smoke import SmokeOverlay
            self._smoke = SmokeOverlay()
        sm = self._smoke
        sm.cover_screen(self.screen().geometry() if self.screen()
                        else self._screen_geo())
        sm.set_intensity(stress)
        sm.set_direction(self._facing)
        # Track the exhaust tip as the car drifts (mirrored when facing left).
        ex, ey = self._art.EXHAUST
        col = ex if self._facing == 1 else (self._art.SPRITE_W - 1 - ex)
        sm.set_source(self.x() + self._ox + col * self._scale,
                      self.y() + self._pad_top + ey * self._scale)
        if stress > 0.0 and not self._fs_hidden and self.isVisible():
            if not sm.isVisible():
                sm.show()
            sm.run(True)
        else:
            self._stop_smoke()

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
            self._stop_smoke()
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
        """Advance the buddy along the taskbar.

        The 3D car runs the Driver state machine: parked at a corner below the
        RAM line, drifting back and forth above it, sweeping its yaw through
        the baked ring to turn around, wheels rolling with road speed. The
        tortoise (and vector-car fallback) keeps the simple bounce walk.
        """
        if not self.isVisible() or self._drag_x is not None:
            return
        geo = self._screen_geo()
        left = geo.left()
        right = geo.right() - self.width()
        if right <= left:
            return

        dt = min(0.1, self._move_clock.restart() / 1000.0)
        if self._art is car3d:
            st = self._drive
            st.x = self._pos_x
            # Cruise pace: cross the screen in ~18 s; RAM adds up to ~2.6x.
            cruise = geo.width() / 18.0
            sw, _ = self._sprite_units()
            self._driver.step(st, dt, self._ram_pct,
                              float(left), float(right), cruise,
                              sprite_w_px=sw * self._scale)
            self._pos_x = st.x
            self._facing = st.facing
            self.move(int(round(self._pos_x)), self.y())
            if st.speed > 0 or st.turning:
                self.update()             # yaw/wheels changed -> repaint
            if self._smoke is not None and self._smoke.isVisible():
                self._update_smoke(self._mood.stress)
            return

        if not self.cfg.llama_wander:
            return
        px_per_sec = geo.width() / max(20, self.cfg.llama_cross_seconds)
        mult = (_GAIT_SPEED.get(self._mood.gait, 1.0)
                * self._ram_speed_mult(self._ram_pct))
        if self.cfg.buddy_character == "car":
            mult *= _CAR_DRIFT_SPEED
        self._pos_x += self._facing * px_per_sec * mult * dt
        if self._pos_x <= left:
            self._pos_x, self._facing = float(left), 1
        elif self._pos_x >= right:
            self._pos_x, self._facing = float(right), -1
        self.move(int(round(self._pos_x)), self.y())
        if self._smoke is not None and self._smoke.isVisible():
            self._update_smoke(self._mood.stress)   # plume follows the exhaust

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
        art = self._art
        p = QtGui.QPainter(self)
        s = self._scale
        ox, oy = self._ox, float(self._pad_top)

        # Baked 3D car: pick the frame for the current heading and wheel
        # phase. No mirroring — the yaw ring covers every direction.
        if art is car3d:
            sw, sh = self._sprite_units()
            w, h = sw * s, sh * s
            st = self._drive
            img = car3d.frame_image(int(round(w)), st.yaw,
                                    self._driver.spin_phase(st))
            if img is not None:
                p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
                p.drawImage(QtCore.QRectF(ox, oy, w, h), img)
            return

        # Vector characters rasterise to a cached high-resolution image
        # rather than a grid of cells.
        if getattr(art, "IS_VECTOR", False):
            sw, sh = self._sprite_units()
            w = sw * s
            h = sh * s
            img = art.render_image(int(round(w)), self._frame_i)
            p.setRenderHint(QtGui.QPainter.SmoothPixmapTransform, True)
            p.save()
            if self._facing == -1:            # mirror to face its travel
                p.translate(self.width(), 0)
                p.scale(-1, 1)
            p.drawImage(QtCore.QRectF(ox, oy, w, h), img)
            p.restore()
            return

        frames = art.frames_for_gait(m.gait)
        rows = frames[self._frame_i % len(frames)]
        rows = art.apply_overlays(rows, shades=m.shades,
                                  blink=self._blink and not m.shades)
        PALETTE, PANIC_TINT = art.PALETTE, art.PANIC_TINT
        TINT_EXEMPT, SPRITE_W = art.TINT_EXEMPT, art.SPRITE_W
        # RAM alarm: blend toward red by the stress level (face/legs/shell).
        amt = min(0.85, m.stress * 0.85)
        tint = QtGui.QColor(PANIC_TINT)
        for ry, row in enumerate(rows):
            for rx, ch in enumerate(row):
                if ch == ".":
                    continue
                col = QtGui.QColor(PALETTE.get(ch, "#f2e3c8"))
                if amt > 0 and ch not in TINT_EXEMPT:
                    col = QtGui.QColor(
                        int(col.red() * (1 - amt) + tint.red() * amt),
                        int(col.green() * (1 - amt) + tint.green() * amt),
                        int(col.blue() * (1 - amt) + tint.blue() * amt))
                px = rx if self._facing == 1 else (SPRITE_W - 1 - rx)
                p.fillRect(QtCore.QRectF(ox + px * s, oy + ry * s, s, s), col)

        # The car conveys panic through its smoke plume, not a "!!" bubble.
        if m.panic and self.cfg.buddy_character != "car":
            p.setRenderHint(QtGui.QPainter.Antialiasing)
            head_col = 50  # tortoise head sits near the right edge of the sprite
            head_x = ox + (head_col * s if self._facing == 1
                           else (SPRITE_W - head_col) * s)
            p.setPen(QtGui.QColor(PANIC_TINT))
            f = QtGui.QFont("Segoe UI", int(6 * self._scale), QtGui.QFont.Black)
            p.setFont(f)
            p.drawText(QtCore.QRectF(head_x - 30, 0, 34, self._pad_top + 2),
                       QtCore.Qt.AlignHCenter | QtCore.Qt.AlignBottom, "!!")

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
        self._drive.x = self._pos_x
        self._drive.park_side = 0         # re-choose the corner if parked
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
        car = self.cfg.buddy_character == "car"
        menu.addAction(("✓ " if car else "") + "Mustang",
                       lambda: self.request_character.emit("car"))
        menu.addAction(("✓ " if not car else "") + "Tortoise",
                       lambda: self.request_character.emit("tortoise"))
        if car:
            menu.addAction(("✓ " if self.cfg.car_smoke else "") + "RAM smoke",
                           lambda: self.request_smoke.emit(not self.cfg.car_smoke))
        menu.addSeparator()
        menu.addAction("Pinned mode", lambda: self.request_mode.emit("pinned"))
        menu.addAction("Peek mode", lambda: self.request_mode.emit("peek"))
        menu.addAction("✓ Llama mode", lambda: None)
        menu.addSeparator()
        menu.addAction("Settings…", self.request_settings.emit)
        menu.addAction("Quit MemGraph", self.request_quit.emit)
        menu.exec(e.globalPos())
