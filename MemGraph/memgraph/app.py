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

        self.tray = Tray(self.qapp)
        self.tray.toggle_visibility.connect(self.toggle_widget)
        self.tray.open_settings.connect(self.open_settings)
        self.tray.quit.connect(self.quit)

        autostart.apply(self.cfg.autostart)

        if self.cfg.start_hidden:
            self.widget.hide()
        else:
            self.widget.show()

    # ------------------------------------------------------------------ #
    def surface(self) -> None:
        """Bring the widget to the foreground (used when a 2nd launch pings)."""
        self.widget.show()
        self.widget.raise_()
        self.widget.activateWindow()

    def _on_move(self, x: int, y: int) -> None:
        self.cfg.pos_x, self.cfg.pos_y = x, y
        save_config(self.cfg)

    def toggle_widget(self) -> None:
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
            if autostart_changed:
                autostart.apply(self.cfg.autostart)

    def quit(self) -> None:
        pos = self.widget.pos()
        self.cfg.pos_x, self.cfg.pos_y = pos.x(), pos.y()
        save_config(self.cfg)
        self.qapp.quit()

    def run(self) -> int:
        return self.qapp.exec()


def _run_widget() -> int:
    app = MemGraphApp()
    guard = SingleInstance(app.qapp)
    if not guard.is_primary:
        # Another instance is already running: surface it and bail out.
        guard.ping_primary()
        return 0
    guard.start_server(app.surface)
    app._guard = guard  # keep a reference alive
    return app.run()


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--setup" in argv or "--install" in argv:
        return run_installer()
    if "--widget" in argv or "--run" in argv:
        return _run_widget()
    # No explicit mode: installed copies run the widget, otherwise show setup.
    if is_installed_copy():
        return _run_widget()
    return run_installer()


if __name__ == "__main__":
    raise SystemExit(main())
