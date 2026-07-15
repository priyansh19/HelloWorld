"""Application wiring and entrypoint.

Modes (selected by CLI flag, or auto-detected):
* ``--setup``   show the installer window.
* ``--widget``  run the floating widget.
* (no flag)     run the installer unless this exe is an installed copy (marker
                present beside it), in which case run the widget.

The widget enforces a single running instance: a second launch surfaces the
existing widget and exits instead of opening a duplicate.
"""

from __future__ import annotations

import sys

from PySide6 import QtWidgets

from . import __app_name__, __version__
from . import autostart
from .config import Config, load_config, save_config
from .installer import is_installed_copy, run_installer
from .metrics import MetricsSampler
from .settings_dialog import SettingsDialog
from .single_instance import SingleInstance
from .tray import Tray
from .widget import MemGraphWidget


class MemGraphApp:
    def __init__(self) -> None:
        self.qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.qapp.setApplicationName(__app_name__)
        self.qapp.setApplicationVersion(__version__)
        self.qapp.setQuitOnLastWindowClosed(False)

        self.cfg = load_config()
        self.sampler = MetricsSampler()

        self.widget = MemGraphWidget(self.cfg, self.sampler, on_move=self._on_move)
        self.widget.request_settings.connect(self.open_settings)
        self.widget.request_quit.connect(self.quit)
        self.widget.request_hide.connect(self.widget.hide)
        self.widget.request_mode.connect(self.set_mode)
        self.widget.request_admin.connect(self.relaunch_elevated)

        self.llama = None  # created lazily for llama mode

        self.tray = Tray(self.qapp)
        self.tray.toggle_visibility.connect(self.toggle_widget)
        self.tray.open_settings.connect(self.open_settings)
        self.tray.quit.connect(self.quit)

        autostart.apply(self.cfg.autostart)

        self._sync_mode_widgets(initial=True)

    # ------------------------------------------------------------------ #
    def _ensure_llama(self):
        if self.llama is None:
            from .llama import LlamaBuddy
            self.llama = LlamaBuddy(self.cfg, self.sampler,
                                    on_move=self._on_llama_move)
            self.llama.clicked.connect(self.toggle_card_popup)
            self.llama.request_settings.connect(self.open_settings)
            self.llama.request_quit.connect(self.quit)
            self.llama.request_mode.connect(self.set_mode)
        return self.llama

    def _sync_mode_widgets(self, initial: bool = False) -> None:
        """Show the right surfaces for the current mode."""
        if self.cfg.mode == "llama":
            self.widget.hide()
            self._ensure_llama()
            self.llama.apply_config(self.cfg)
            self.llama.show()
        else:
            if self.llama is not None:
                self.llama.hide()
            if self.cfg.start_hidden and initial:
                self.widget.hide()
            else:
                self.widget.show()

    def toggle_card_popup(self) -> None:
        """Click on the llama: pop the stat card just above it, or hide it."""
        if self.widget.isVisible():
            self.widget.hide()
            return
        anchor = self.llama.anchor_rect() if self.llama else None
        self.widget.show()
        self.widget.raise_()
        if anchor is not None:
            geo = self.llama._screen_geo()
            x = anchor.center().x() - self.widget.width() // 2
            x = max(geo.left(), min(geo.right() - self.widget.width(), x))
            y = anchor.top() - self.widget.height() - 4
            self.widget.move(x, max(geo.top(), y))

    # ------------------------------------------------------------------ #
    def surface(self) -> None:
        """Bring the widget to the foreground (used when a 2nd launch pings)."""
        if self.cfg.mode == "llama":
            self.toggle_card_popup() if not self.widget.isVisible() else None
            if self.llama:
                self.llama.show()
                self.llama.raise_()
            return
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()

    def _on_move(self, x: int, y: int) -> None:
        self.cfg.pos_x, self.cfg.pos_y = x, y
        save_config(self.cfg)

    def _on_llama_move(self, x: int) -> None:
        self.cfg.llama_x = x
        save_config(self.cfg)

    def set_mode(self, mode: str) -> None:
        self.cfg.mode = mode
        self.cfg.clamp()
        save_config(self.cfg)
        self.widget.apply_config(self.cfg)
        self._sync_mode_widgets()

    def relaunch_elevated(self) -> None:
        """Relaunch MemGraph with administrator rights so the sensor driver can
        load and read CPU / motherboard / memory temperatures. No-op unless on
        Windows; if the user declines the UAC prompt, the current instance stays.
        """
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            if getattr(sys, "frozen", False):
                exe, params = sys.executable, "--widget --takeover"
            else:
                exe, params = sys.executable, "-m memgraph --widget --takeover"
            rc = ctypes.windll.shell32.ShellExecuteW(
                None, "runas", exe, params, None, 1)
            if int(rc) > 32:            # success -> elevated instance launching
                self.quit()
        except Exception:
            pass

    def toggle_widget(self) -> None:
        if self.cfg.mode == "llama" and self.llama is not None:
            if self.llama.isVisible():
                self.llama.hide()
                self.widget.hide()
            else:
                self.llama.show()
            return
        if self.widget.isVisible():
            self.widget.hide()
        else:
            self.surface()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self.sampler, self.widget)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            new_cfg = dlg.result_config()
            new_cfg.pos_x, new_cfg.pos_y = self.cfg.pos_x, self.cfg.pos_y
            new_cfg.width, new_cfg.height = self.cfg.width, self.cfg.height
            autostart_changed = new_cfg.autostart != self.cfg.autostart
            self.cfg = new_cfg
            save_config(self.cfg)
            self.widget.apply_config(self.cfg)
            self._sync_mode_widgets()
            if autostart_changed:
                autostart.apply(self.cfg.autostart)

    def quit(self) -> None:
        pos = self.widget.pos()
        self.cfg.pos_x, self.cfg.pos_y = pos.x(), pos.y()
        save_config(self.cfg)
        self.qapp.quit()

    def run(self) -> int:
        return self.qapp.exec()


def _run_widget(takeover: bool = False) -> int:
    qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    guard = SingleInstance(qapp)
    if not guard.is_primary:
        if takeover:
            # An elevated relaunch: ask the running instance to exit, then claim
            # the slot so this (admin) instance becomes the single instance.
            guard.request_quit_primary()
            guard.try_become_primary()
        else:
            guard.ping_primary()   # surface the running instance, then exit
            return 0
    app = MemGraphApp()
    guard.start_server(app.surface, on_quit=app.quit)
    app._guard = guard  # keep a reference alive
    return app.run()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--setup" in argv or "--install" in argv:
        return run_installer()
    if "--widget" in argv or "--run" in argv:
        return _run_widget(takeover="--takeover" in argv)
    # No explicit mode: installed copies run the widget, otherwise show setup.
    if is_installed_copy():
        return _run_widget()
    return run_installer()


if __name__ == "__main__":
    raise SystemExit(main())
