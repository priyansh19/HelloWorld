"""System-tray integration: show/hide the widget, open settings, quit.

The tray icon is generated at runtime (no external asset needed) so the packaged
.exe stays self-contained. A simple coloured 'M' glyph on a rounded chip keeps it
recognisable in the notification area.
"""

from __future__ import annotations

from PySide6 import QtCore, QtGui, QtWidgets


def build_icon() -> QtGui.QIcon:
    """Draw a small MemGraph tray icon programmatically."""
    pix = QtGui.QPixmap(64, 64)
    pix.fill(QtCore.Qt.transparent)
    painter = QtGui.QPainter(pix)
    painter.setRenderHint(QtGui.QPainter.Antialiasing)
    painter.setBrush(QtGui.QColor("#1f6feb"))
    painter.setPen(QtCore.Qt.NoPen)
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)
    painter.setPen(QtGui.QColor("#ffffff"))
    font = QtGui.QFont("Segoe UI", 30, QtGui.QFont.Bold)
    painter.setFont(font)
    painter.drawText(pix.rect(), QtCore.Qt.AlignCenter, "M")
    painter.end()
    return QtGui.QIcon(pix)


class Tray(QtCore.QObject):
    toggle_visibility = QtCore.Signal()
    open_settings = QtCore.Signal()
    set_mode = QtCore.Signal(str)
    quit = QtCore.Signal()

    def __init__(self, parent: QtCore.QObject | None = None) -> None:
        super().__init__(parent)
        self.icon = QtWidgets.QSystemTrayIcon(build_icon(), parent)
        self.icon.setToolTip("MemGraph — memory monitor")

        menu = QtWidgets.QMenu()
        menu.addAction("Show / Hide", self.toggle_visibility.emit)

        mode_menu = menu.addMenu("Mode")
        mode_menu.addAction("🦙  Llama (taskbar buddy)",
                            lambda: self.set_mode.emit("llama"))
        mode_menu.addAction("Peek (edge tab)",
                            lambda: self.set_mode.emit("peek"))
        mode_menu.addAction("Pinned (always visible)",
                            lambda: self.set_mode.emit("pinned"))

        menu.addAction("Settings…", self.open_settings.emit)
        menu.addSeparator()
        menu.addAction("Quit", self.quit.emit)
        self.icon.setContextMenu(menu)
        self.icon.activated.connect(self._on_activated)
        self.icon.show()

    def _on_activated(self, reason) -> None:
        # Left-click / double-click toggles the widget.
        if reason in (QtWidgets.QSystemTrayIcon.Trigger,
                      QtWidgets.QSystemTrayIcon.DoubleClick):
            self.toggle_visibility.emit()

    def notify(self, title: str, message: str) -> None:
        self.icon.showMessage(title, message, build_icon(), 3000)
