"""Settings dialog: every user-tunable option in one tabbed window.

The dialog reads a :class:`~memgraph.config.Config`, lets the user edit it, and
on *Save* returns a new validated Config. Applying it to the running widget and
persisting to disk is the caller's job (see ``app.py``).
"""

from __future__ import annotations

from dataclasses import replace

from PySide6 import QtCore, QtWidgets

from .config import (
    Config,
    HISTORY_MAX,
    HISTORY_MIN,
    REFRESH_MS_MAX,
    REFRESH_MS_MIN,
)
from .metrics import MetricsSampler


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, config: Config, sampler: MetricsSampler,
                 parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MemGraph — Settings")
        self.setModal(True)
        self.setMinimumWidth(420)
        self._cfg = config
        self._sampler = sampler

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._build_metrics_tab(), "Metrics")
        tabs.addTab(self._build_appearance_tab(), "Appearance")
        tabs.addTab(self._build_behaviour_tab(), "Behaviour")

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    # Tabs
    # ------------------------------------------------------------------ #
    def _build_metrics_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)

        self.chk_ram = QtWidgets.QCheckBox("Show system RAM")
        self.chk_ram.setChecked(self._cfg.show_ram)

        self.chk_vram = QtWidgets.QCheckBox("Show GPU VRAM")
        self.chk_vram.setChecked(self._cfg.show_vram)
        gpu = self._sampler.gpu_name()
        gpu_hint = QtWidgets.QLabel(
            f"Detected: {gpu}" if self._sampler.gpu_available
            else "No NVIDIA GPU detected — VRAM will show as n/a"
        )
        gpu_hint.setStyleSheet("color: gray; font-size: 11px;")

        self.chk_proc = QtWidgets.QCheckBox("Track a process")
        self.chk_proc.setChecked(self._cfg.show_process)
        self.edit_proc = QtWidgets.QLineEdit(self._cfg.process_name)
        self.edit_proc.setPlaceholderText("e.g. ollama.exe")

        form.addRow(self.chk_ram)
        form.addRow(self.chk_vram)
        form.addRow("", gpu_hint)
        form.addRow(self.chk_proc)
        form.addRow("Process name:", self.edit_proc)

        self.spin_refresh = QtWidgets.QSpinBox()
        self.spin_refresh.setRange(REFRESH_MS_MIN, REFRESH_MS_MAX)
        self.spin_refresh.setSingleStep(250)
        self.spin_refresh.setSuffix(" ms")
        self.spin_refresh.setValue(self._cfg.refresh_ms)

        self.spin_history = QtWidgets.QSpinBox()
        self.spin_history.setRange(HISTORY_MIN, HISTORY_MAX)
        self.spin_history.setSingleStep(30)
        self.spin_history.setSuffix(" s")
        self.spin_history.setValue(self._cfg.history_seconds)

        form.addRow("Refresh interval:", self.spin_refresh)
        form.addRow("History length:", self.spin_history)
        return w

    def _build_appearance_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)

        self.combo_theme = QtWidgets.QComboBox()
        self.combo_theme.addItems(["dark", "light"])
        self.combo_theme.setCurrentText(self._cfg.theme)

        self.slider_opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(int(self._cfg.opacity * 100))
        self.lbl_opacity = QtWidgets.QLabel(f"{int(self._cfg.opacity * 100)}%")
        self.slider_opacity.valueChanged.connect(
            lambda v: self.lbl_opacity.setText(f"{v}%"))
        op_row = QtWidgets.QHBoxLayout()
        op_row.addWidget(self.slider_opacity)
        op_row.addWidget(self.lbl_opacity)
        op_widget = QtWidgets.QWidget()
        op_widget.setLayout(op_row)

        self.spin_amber = QtWidgets.QSpinBox()
        self.spin_amber.setRange(1, 99)
        self.spin_amber.setSuffix(" %")
        self.spin_amber.setValue(self._cfg.threshold_amber)

        self.spin_red = QtWidgets.QSpinBox()
        self.spin_red.setRange(2, 100)
        self.spin_red.setSuffix(" %")
        self.spin_red.setValue(self._cfg.threshold_red)

        form.addRow("Theme:", self.combo_theme)
        form.addRow("Opacity:", op_widget)
        form.addRow("Amber threshold:", self.spin_amber)
        form.addRow("Red threshold:", self.spin_red)
        return w

    def _build_behaviour_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)

        self.chk_ontop = QtWidgets.QCheckBox("Always on top")
        self.chk_ontop.setChecked(self._cfg.always_on_top)

        self.chk_snap = QtWidgets.QCheckBox("Snap to screen edges")
        self.chk_snap.setChecked(self._cfg.snap_to_edges)

        self.chk_autostart = QtWidgets.QCheckBox("Start automatically at login")
        self.chk_autostart.setChecked(self._cfg.autostart)

        self.chk_hidden = QtWidgets.QCheckBox("Start hidden (tray only)")
        self.chk_hidden.setChecked(self._cfg.start_hidden)

        form.addRow(self.chk_ontop)
        form.addRow(self.chk_snap)
        form.addRow(self.chk_autostart)
        form.addRow(self.chk_hidden)
        return w

    # ------------------------------------------------------------------ #
    # Result
    # ------------------------------------------------------------------ #
    def result_config(self) -> Config:
        """Build a validated Config from the widget states (post-accept)."""
        return replace(
            self._cfg,
            show_ram=self.chk_ram.isChecked(),
            show_vram=self.chk_vram.isChecked(),
            show_process=self.chk_proc.isChecked(),
            process_name=self.edit_proc.text().strip(),
            refresh_ms=self.spin_refresh.value(),
            history_seconds=self.spin_history.value(),
            theme=self.combo_theme.currentText(),
            opacity=self.slider_opacity.value() / 100.0,
            threshold_amber=self.spin_amber.value(),
            threshold_red=self.spin_red.value(),
            always_on_top=self.chk_ontop.isChecked(),
            snap_to_edges=self.chk_snap.isChecked(),
            autostart=self.chk_autostart.isChecked(),
            start_hidden=self.chk_hidden.isChecked(),
        ).clamp()
