"""Settings dialog: choose metrics, tune sampling, and style the widget."""

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
from .metrics import METRIC_DEFS, MetricsSampler


class SettingsDialog(QtWidgets.QDialog):
    def __init__(self, config: Config, sampler: MetricsSampler,
                 parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MemGraph — Settings")
        self.setModal(True)
        self.setMinimumWidth(440)
        self._cfg = config
        self._sampler = sampler
        self._metric_checks: dict[str, QtWidgets.QCheckBox] = {}

        tabs = QtWidgets.QTabWidget()
        tabs.addTab(self._metrics_tab(), "Metrics")
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._behaviour_tab(), "Behaviour")

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Save | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(tabs)
        lay.addWidget(buttons)

    # ------------------------------------------------------------------ #
    def _metrics_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)

        hint = QtWidgets.QLabel(
            "Tick the metrics to show. The first ticked metric is the primary "
            "one drawn as the big graph.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow(hint)

        enabled = set(self._cfg.enabled_metrics)
        for d in METRIC_DEFS:
            chk = QtWidgets.QCheckBox(f"{d.label}  —  {d.description}")
            chk.setChecked(d.key in enabled)
            self._metric_checks[d.key] = chk
            form.addRow(chk)

        gpu = self._sampler.gpu_name()
        gpu_hint = QtWidgets.QLabel(
            f"GPU detected: {gpu}" if self._sampler.gpu_available
            else "No NVIDIA GPU detected — VRAM/GPU/GPU-temp show n/a.")
        gpu_hint.setStyleSheet("color: gray; font-size: 11px;")
        gpu_hint.setWordWrap(True)
        form.addRow(gpu_hint)

        self.edit_proc = QtWidgets.QLineEdit(self._cfg.process_name)
        self.edit_proc.setPlaceholderText("e.g. ollama.exe")
        form.addRow("Process to track:", self.edit_proc)

        self.spin_refresh = QtWidgets.QSpinBox()
        self.spin_refresh.setRange(REFRESH_MS_MIN, REFRESH_MS_MAX)
        self.spin_refresh.setSingleStep(250)
        self.spin_refresh.setSuffix(" ms")
        self.spin_refresh.setValue(self._cfg.refresh_ms)
        form.addRow("Refresh interval:", self.spin_refresh)

        self.spin_history = QtWidgets.QSpinBox()
        self.spin_history.setRange(HISTORY_MIN, HISTORY_MAX)
        self.spin_history.setSingleStep(30)
        self.spin_history.setSuffix(" s")
        self.spin_history.setValue(self._cfg.history_seconds)
        form.addRow("History window:", self.spin_history)
        return w

    def _appearance_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)

        self.combo_theme = QtWidgets.QComboBox()
        self.combo_theme.addItems(["midnight", "graphite", "light"])
        self.combo_theme.setCurrentText(self._cfg.theme)
        form.addRow("Theme:", self.combo_theme)

        self.chk_spark = QtWidgets.QCheckBox("Show the sparkline graph")
        self.chk_spark.setChecked(self._cfg.show_sparkline)
        form.addRow(self.chk_spark)

        self.slider_opacity = QtWidgets.QSlider(QtCore.Qt.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(int(self._cfg.opacity * 100))
        self.lbl_opacity = QtWidgets.QLabel(f"{int(self._cfg.opacity * 100)}%")
        self.slider_opacity.valueChanged.connect(
            lambda v: self.lbl_opacity.setText(f"{v}%"))
        row = QtWidgets.QWidget()
        rl = QtWidgets.QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.addWidget(self.slider_opacity)
        rl.addWidget(self.lbl_opacity)
        form.addRow("Opacity:", row)

        self.spin_amber = QtWidgets.QSpinBox()
        self.spin_amber.setRange(1, 99)
        self.spin_amber.setSuffix(" %")
        self.spin_amber.setValue(self._cfg.threshold_amber)
        self.spin_red = QtWidgets.QSpinBox()
        self.spin_red.setRange(2, 100)
        self.spin_red.setSuffix(" %")
        self.spin_red.setValue(self._cfg.threshold_red)
        form.addRow("Amber at (usage):", self.spin_amber)
        form.addRow("Red at (usage):", self.spin_red)

        self.spin_tamber = QtWidgets.QSpinBox()
        self.spin_tamber.setRange(20, 110)
        self.spin_tamber.setSuffix(" °C")
        self.spin_tamber.setValue(self._cfg.temp_amber)
        self.spin_tred = QtWidgets.QSpinBox()
        self.spin_tred.setRange(21, 120)
        self.spin_tred.setSuffix(" °C")
        self.spin_tred.setValue(self._cfg.temp_red)
        form.addRow("Amber at (temp):", self.spin_tamber)
        form.addRow("Red at (temp):", self.spin_tred)
        return w

    def _behaviour_tab(self) -> QtWidgets.QWidget:
        w = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(w)

        self.combo_mode = QtWidgets.QComboBox()
        self.combo_mode.addItem("Llama (taskbar buddy)", "llama")
        self.combo_mode.addItem("Pinned (always visible)", "pinned")
        self.combo_mode.addItem("Peek (slide-out tab, auto-hide)", "peek")
        idx = self.combo_mode.findData(self._cfg.mode)
        self.combo_mode.setCurrentIndex(max(0, idx))
        form.addRow("Display mode:", self.combo_mode)

        self.chk_wander = QtWidgets.QCheckBox(
            "Llama walks back and forth across the screen")
        self.chk_wander.setChecked(self._cfg.llama_wander)
        form.addRow(self.chk_wander)

        self.spin_cross = QtWidgets.QSpinBox()
        self.spin_cross.setRange(1, 60)
        self.spin_cross.setSuffix(" min / crossing")
        self.spin_cross.setValue(max(1, round(self._cfg.llama_cross_seconds / 60)))
        form.addRow("Llama speed:", self.spin_cross)

        self.spin_scale = QtWidgets.QDoubleSpinBox()
        self.spin_scale.setRange(1.0, 4.0)
        self.spin_scale.setSingleStep(0.2)
        self.spin_scale.setSuffix("×")
        self.spin_scale.setValue(self._cfg.llama_scale)
        form.addRow("Llama size:", self.spin_scale)

        self.spin_peek = QtWidgets.QSpinBox()
        self.spin_peek.setRange(10, 600)
        self.spin_peek.setSingleStep(10)
        self.spin_peek.setSuffix(" s")
        self.spin_peek.setValue(self._cfg.peek_seconds)
        form.addRow("Auto-hide after:", self.spin_peek)

        self.chk_compact = QtWidgets.QCheckBox("Compact layout")
        self.chk_compact.setChecked(self._cfg.compact)
        form.addRow(self.chk_compact)

        self.chk_ontop = QtWidgets.QCheckBox("Always on top")
        self.chk_ontop.setChecked(self._cfg.always_on_top)
        self.chk_snap = QtWidgets.QCheckBox("Snap to screen edges")
        self.chk_snap.setChecked(self._cfg.snap_to_edges)
        self.chk_autostart = QtWidgets.QCheckBox("Start automatically at login")
        self.chk_autostart.setChecked(self._cfg.autostart)
        self.chk_hidden = QtWidgets.QCheckBox("Start hidden (tray only)")
        self.chk_hidden.setChecked(self._cfg.start_hidden)
        for c in (self.chk_ontop, self.chk_snap, self.chk_autostart, self.chk_hidden):
            form.addRow(c)
        return w

    # ------------------------------------------------------------------ #
    def result_config(self) -> Config:
        # Preserve enabled order: keep previously-enabled order, then append
        # newly-ticked metrics in registry order.
        prev = [k for k in self._cfg.enabled_metrics
                if self._metric_checks[k].isChecked()]
        added = [d.key for d in METRIC_DEFS
                 if self._metric_checks[d.key].isChecked() and d.key not in prev]
        enabled = prev + added

        return replace(
            self._cfg,
            enabled_metrics=enabled,
            process_name=self.edit_proc.text().strip(),
            refresh_ms=self.spin_refresh.value(),
            history_seconds=self.spin_history.value(),
            theme=self.combo_theme.currentText(),
            show_sparkline=self.chk_spark.isChecked(),
            opacity=self.slider_opacity.value() / 100.0,
            threshold_amber=self.spin_amber.value(),
            threshold_red=self.spin_red.value(),
            temp_amber=self.spin_tamber.value(),
            temp_red=self.spin_tred.value(),
            mode=self.combo_mode.currentData(),
            peek_seconds=self.spin_peek.value(),
            llama_wander=self.chk_wander.isChecked(),
            llama_cross_seconds=self.spin_cross.value() * 60,
            llama_scale=self.spin_scale.value(),
            compact=self.chk_compact.isChecked(),
            always_on_top=self.chk_ontop.isChecked(),
            snap_to_edges=self.chk_snap.isChecked(),
            autostart=self.chk_autostart.isChecked(),
            start_hidden=self.chk_hidden.isChecked(),
        ).clamp()
