"""Modern setup experience.

When the distributed ``MemGraph-Setup.exe`` is launched without an install
marker beside it, the app shows this installer window: a modern, branded UI that
describes the product and installs it (copies the exe into the user's programs
folder, creates Start-menu/desktop shortcuts, registers login autostart) and
then launches the widget.

All install side-effects are Windows-specific and guarded; on other platforms
the window still renders (useful for a visual check) but the install button
explains it only applies on Windows.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from . import __version__
from . import autostart
from .sparkline import Sparkline

INSTALL_MARKER = ".memgraph_installed"

_ACCENT = "#6f7be0"
_ACCENT_2 = "#3ddc84"

FEATURES = [
    ("Live graph widget", "always-on-top, drag it anywhere"),
    ("Built for local LLMs", "RAM, VRAM & your model process, live"),
    ("CPU · GPU · NPU · temps", "add any metrics, when sensors allow"),
    ("Set & forget", "autostarts at login, sits in the tray"),
]


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def default_install_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "Programs" / "MemGraph"


def is_installed_copy() -> bool:
    """True when the running exe sits next to an install marker."""
    try:
        exe_dir = Path(sys.executable).resolve().parent
        return (exe_dir / INSTALL_MARKER).exists()
    except Exception:
        return False


def _make_shortcut(lnk: Path, target: Path, args: str, workdir: Path) -> None:
    """Create a .lnk via the WScript.Shell COM object (no extra deps)."""
    if not _is_windows():
        return
    ps = (
        "$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{lnk}'); "
        f"$s.TargetPath = '{target}'; "
        f"$s.Arguments = '{args}'; "
        f"$s.WorkingDirectory = '{workdir}'; "
        f"$s.IconLocation = '{target}'; "
        "$s.Save()"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       check=False, creationflags=0x08000000)  # no window
    except Exception:
        pass


def perform_install(dest_dir: Path, autostart_on: bool,
                    desktop_shortcut: bool) -> Path:
    """Install the running exe into ``dest_dir``; return the installed exe path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    installed_exe = dest_dir / "MemGraph.exe"

    src = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False) and src != installed_exe.resolve():
        shutil.copy2(src, installed_exe)
    elif not getattr(sys, "frozen", False):
        # Running from source: nothing to copy; point launchers at the module.
        installed_exe = src  # the python interpreter

    (dest_dir / INSTALL_MARKER).write_text("1", encoding="utf-8")

    if _is_windows():
        if getattr(sys, "frozen", False):
            target, args = installed_exe, "--widget"
        else:
            target, args = installed_exe, "-m memgraph --widget"

        start_menu = Path(os.environ.get("APPDATA", "")) / \
            "Microsoft" / "Windows" / "Start Menu" / "Programs"
        start_menu.mkdir(parents=True, exist_ok=True)
        _make_shortcut(start_menu / "MemGraph.lnk", target, args, dest_dir)

        if desktop_shortcut:
            desktop = Path.home() / "Desktop"
            desktop.mkdir(parents=True, exist_ok=True)
            _make_shortcut(desktop / "MemGraph.lnk", target, args, dest_dir)

        cmd = f'"{target}" {args}'.strip()
        if autostart_on:
            autostart.enable(cmd)
        else:
            autostart.disable()

    return installed_exe


class InstallerWindow(QtWidgets.QWidget):
    """The branded setup window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MemGraph Setup")
        self.setFixedSize(640, 560)
        self._installed_exe: Path | None = None
        self._done = False
        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        body = QtWidgets.QWidget()
        body.setObjectName("body")
        b = QtWidgets.QVBoxLayout(body)
        b.setContentsMargins(30, 22, 30, 24)
        b.setSpacing(16)

        intro = QtWidgets.QLabel(
            "A lightweight, professional desktop widget that shows your system "
            "memory — and CPU, GPU, NPU and temperatures — as a live graph, "
            "purpose-built for keeping an eye on memory pressure while running "
            "local LLM models.")
        intro.setObjectName("intro")
        intro.setWordWrap(True)
        b.addWidget(intro)

        b.addLayout(self._build_features())

        b.addWidget(self._build_location())
        b.addLayout(self._build_options())
        b.addStretch(1)
        b.addWidget(self._build_footer())

        root.addWidget(body, 1)
        self._apply_style()

    def _build_header(self) -> QtWidgets.QWidget:
        header = QtWidgets.QFrame()
        header.setObjectName("header")
        header.setFixedHeight(150)
        h = QtWidgets.QHBoxLayout(header)
        h.setContentsMargins(30, 0, 24, 0)

        left = QtWidgets.QVBoxLayout()
        left.setSpacing(4)
        left.addStretch(1)
        title = QtWidgets.QLabel("◈  MemGraph")
        title.setObjectName("title")
        tag = QtWidgets.QLabel("Live memory & hardware monitor for local LLMs")
        tag.setObjectName("tagline")
        ver = QtWidgets.QLabel(f"Version {__version__}")
        ver.setObjectName("version")
        left.addWidget(title)
        left.addWidget(tag)
        left.addWidget(ver)
        left.addStretch(1)
        h.addLayout(left, 1)

        # A little decorative sparkline in the header.
        spark = Sparkline()
        spark.setFixedSize(180, 90)
        spark.set_grid_color(QtGui.QColor(255, 255, 255, 24))
        spark.set_data([30, 34, 40, 38, 46, 52, 49, 58, 63, 60, 68, 74, 70,
                        78, 72], _ACCENT_2)
        h.addWidget(spark)
        return header

    def _build_features(self) -> QtWidgets.QVBoxLayout:
        box = QtWidgets.QVBoxLayout()
        box.setSpacing(10)
        for name, desc in FEATURES:
            row = QtWidgets.QHBoxLayout()
            row.setSpacing(12)
            check = QtWidgets.QLabel("✓")
            check.setObjectName("check")
            check.setFixedWidth(18)
            check.setAlignment(QtCore.Qt.AlignTop)
            text = QtWidgets.QLabel(f"<b>{name}</b> — {desc}")
            text.setObjectName("feature")
            text.setWordWrap(True)
            row.addWidget(check)
            row.addWidget(text, 1)
            box.addLayout(row)
        return box

    def _build_location(self) -> QtWidgets.QWidget:
        wrap = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lbl = QtWidgets.QLabel("Install to")
        lbl.setObjectName("locLabel")
        lbl.setFixedWidth(66)
        self.path_edit = QtWidgets.QLineEdit(str(default_install_dir()))
        self.path_edit.setObjectName("pathEdit")
        browse = QtWidgets.QPushButton("Browse…")
        browse.setObjectName("browse")
        browse.setCursor(QtCore.Qt.PointingHandCursor)
        browse.clicked.connect(self._browse)
        lay.addWidget(lbl)
        lay.addWidget(self.path_edit, 1)
        lay.addWidget(browse)
        return wrap

    def _build_options(self) -> QtWidgets.QVBoxLayout:
        box = QtWidgets.QVBoxLayout()
        box.setSpacing(6)
        self.chk_autostart = QtWidgets.QCheckBox("Start MemGraph automatically at login")
        self.chk_autostart.setChecked(True)
        self.chk_desktop = QtWidgets.QCheckBox("Create a desktop shortcut")
        self.chk_desktop.setChecked(True)
        self.chk_launch = QtWidgets.QCheckBox("Launch MemGraph when setup finishes")
        self.chk_launch.setChecked(True)
        for c in (self.chk_autostart, self.chk_desktop, self.chk_launch):
            c.setObjectName("opt")
            box.addWidget(c)
        return box

    def _build_footer(self) -> QtWidgets.QWidget:
        wrap = QtWidgets.QWidget()
        lay = QtWidgets.QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        self.status = QtWidgets.QLabel("")
        self.status.setObjectName("status")
        self.install_btn = QtWidgets.QPushButton("Install")
        self.install_btn.setObjectName("install")
        self.install_btn.setFixedHeight(40)
        self.install_btn.setMinimumWidth(150)
        self.install_btn.setCursor(QtCore.Qt.PointingHandCursor)
        self.install_btn.clicked.connect(self._on_install_clicked)
        lay.addWidget(self.status, 1)
        lay.addWidget(self.install_btn)
        return wrap

    # ------------------------------------------------------------------ #
    def _browse(self) -> None:
        d = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Choose install folder", self.path_edit.text())
        if d:
            self.path_edit.setText(str(Path(d) / "MemGraph"))

    def _on_install_clicked(self) -> None:
        if self._done:
            self._launch_and_close()
            return
        self.install_btn.setEnabled(False)
        self.status.setText("Installing…")
        QtWidgets.QApplication.processEvents()
        try:
            self._installed_exe = perform_install(
                Path(self.path_edit.text().strip() or str(default_install_dir())),
                self.chk_autostart.isChecked(),
                self.chk_desktop.isChecked(),
            )
            self._done = True
            self.status.setText("✓  Installed successfully")
            self.install_btn.setText("Launch MemGraph")
            self.install_btn.setEnabled(True)
            if not self.chk_launch.isChecked():
                self.install_btn.setText("Finish")
        except Exception as exc:  # pragma: no cover - platform specific
            self.status.setText(f"Install failed: {exc}")
            self.install_btn.setEnabled(True)

    def _launch_and_close(self) -> None:
        if self.chk_launch.isChecked() and self._installed_exe:
            try:
                if getattr(sys, "frozen", False):
                    subprocess.Popen([str(self._installed_exe), "--widget"])
                else:
                    subprocess.Popen([sys.executable, "-m", "memgraph", "--widget"])
            except Exception:
                pass
        self.close()

    # ------------------------------------------------------------------ #
    def _apply_style(self) -> None:
        self.setStyleSheet(f"""
            QWidget {{ font-family: 'Segoe UI', sans-serif; }}
            #body {{ background: #14151b; }}
            #header {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                       stop:0 #1b1e33, stop:1 #10111a); }}
            #title {{ color: #ffffff; font-size: 30px; font-weight: 800; }}
            #tagline {{ color: #c7ccda; font-size: 13px; }}
            #version {{ color: #7b839a; font-size: 11px; }}
            #intro {{ color: #c2c7d4; font-size: 13px; line-height: 150%; }}
            #feature {{ color: #d7dbe6; font-size: 12px; }}
            #check {{ color: {_ACCENT_2}; font-size: 15px; font-weight: 800; }}
            #locLabel, #opt {{ color: #aeb4c2; font-size: 12px; }}
            #opt {{ spacing: 8px; }}
            #pathEdit {{ background: #1e2029; color: #eef1f7; border: 1px solid
                         #2c2f3b; border-radius: 8px; padding: 8px 10px; }}
            #browse {{ background: #262a37; color: #e6e9f2; border: none;
                       border-radius: 8px; padding: 8px 14px; }}
            #browse:hover {{ background: #313648; }}
            #status {{ color: {_ACCENT_2}; font-size: 12px; }}
            #install {{ background: {_ACCENT}; color: #ffffff; font-size: 14px;
                        font-weight: 700; border: none; border-radius: 10px; }}
            #install:hover {{ background: #7f8bf0; }}
            #install:disabled {{ background: #3a3e52; color: #9aa0b2; }}
            QCheckBox::indicator {{ width: 16px; height: 16px; }}
        """)


def run_installer() -> int:
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    win = InstallerWindow()
    win.show()
    return app.exec()
