"""Application wiring and entrypoint.

Composes the sampler, the floating widget, the tray icon and the settings
dialog, and mediates config changes between them (persist to disk + apply to
the live widget + reconcile Windows autostart).
"""

from __future__ import annotations

import sys

from PySide6 import QtWidgets

from . import __app_name__, __version__
from . import autostart
from .config import Config, load_config, save_config
from .metrics import MetricsSampler
from .settings_dialog import SettingsDialog
from .tray import Tray
from .widget import MemGraphWidget


class MemGraphApp:
    def __init__(self) -> None:
        self.qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self.qapp.setApplicationName(__app_name__)
        self.qapp.setApplicationVersion(__version__)
        # Keep running when the widget is hidden to the tray.
        self.qapp.setQuitOnLastWindowClosed(False)

        self.cfg = load_config()
        self.sampler = MetricsSampler()

        self.widget = MemGraphWidget(self.cfg, self.sampler, on_move=self._on_move)
        self.widget.request_settings.connect(self.open_settings)
        self.widget.request_quit.connect(self.quit)

        self.tray = Tray(self.qapp)
        self.tray.toggle_visibility.connect(self.toggle_widget)
        self.tray.open_settings.connect(self.open_settings)
        self.tray.quit.connect(self.quit)

        # Reconcile autostart with the saved preference on every launch so the
        # registry never drifts from what the user chose.
        autostart.apply(self.cfg.autostart)

        if self.cfg.start_hidden:
            self.widget.hide()
        else:
            self.widget.show()

    # ------------------------------------------------------------------ #
    def _on_move(self, x: int, y: int) -> None:
        self.cfg.pos_x, self.cfg.pos_y = x, y
        save_config(self.cfg)

    def toggle_widget(self) -> None:
        if self.widget.isVisible():
            self.widget.hide()
        else:
            self.widget.show()
            self.widget.raise_()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.cfg, self.sampler, self.widget)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            new_cfg = dlg.result_config()
            # Preserve remembered geometry (not editable in the dialog).
            new_cfg.pos_x, new_cfg.pos_y = self.cfg.pos_x, self.cfg.pos_y
            new_cfg.width, new_cfg.height = self.cfg.width, self.cfg.height
            autostart_changed = new_cfg.autostart != self.cfg.autostart
            self.cfg = new_cfg
            save_config(self.cfg)
            self.widget.apply_config(self.cfg)
            if autostart_changed:
                autostart.apply(self.cfg.autostart)

    def quit(self) -> None:
        # Persist final window position before exiting.
        pos = self.widget.pos()
        self.cfg.pos_x, self.cfg.pos_y = pos.x(), pos.y()
        save_config(self.cfg)
        self.qapp.quit()

    def run(self) -> int:
        return self.qapp.exec()


def main() -> int:
    return MemGraphApp().run()


if __name__ == "__main__":
    raise SystemExit(main())
