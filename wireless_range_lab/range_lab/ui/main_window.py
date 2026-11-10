"""Desktop interface for reproducible wireless trials."""

from __future__ import annotations

import json

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QGuiApplication
from PyQt5.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QPlainTextEdit,
    QVBoxLayout, QWidget, QSpinBox, QTabWidget, QScrollArea,
)

from range_lab.models import ANTENNA_TYPES, DEVICE_TYPES, RADIO_TECHNOLOGIES, Endpoint, TrialMetadata
from range_lab.storage import TrialRepository
from range_lab.ui.live_monitor import LiveMonitor


class MainWindow(QMainWindow):
    def __init__(self, repository: TrialRepository) -> None:
        super().__init__()
        self.repository = repository
        self.current_trial_id: str | None = None
        self.setWindowTitle("Wireless Range Lab")
        self.resize(980, 760)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        layout.addWidget(QLabel("Define a reproducible condition. The app creates the next attempt ID automatically."))
        layout.addWidget(self._endpoint_group("Endpoint A"))
        layout.addWidget(self._endpoint_group("Endpoint B"))

        setup_group = QGroupBox("Link and environment")
        form = QFormLayout(setup_group)
        self.operator = QLineEdit()
        self.radio_technology = QComboBox(); self.radio_technology.addItems(RADIO_TECHNOLOGIES)
        self.communication_mode = QLineEdit(); self.communication_mode.setPlaceholderText("e.g., Wi-Fi client ↔ laptop hotspot")
        self.distance_m = QDoubleSpinBox(); self.distance_m.setRange(0, 100000); self.distance_m.setDecimals(2); self.distance_m.setSuffix(" m")
        self.rotation_deg = QSpinBox(); self.rotation_deg.setRange(-999, 999); self.rotation_deg.setSuffix(" deg")
        self.echo_timeout_ms = QSpinBox(); self.echo_timeout_ms.setRange(1, 9999); self.echo_timeout_ms.setValue(1000); self.echo_timeout_ms.setSuffix(" ms")
        self.reference_distance_m = QDoubleSpinBox(); self.reference_distance_m.setRange(0, 100000); self.reference_distance_m.setDecimals(2); self.reference_distance_m.setSpecialValueText("Not recorded"); self.reference_distance_m.setSuffix(" m")
        self.environment = QLineEdit(); self.environment.setPlaceholderText("e.g., indoor corridor, outdoor open field")
        self.location = QLineEdit(); self.location.setPlaceholderText("Site or test area")
        self.line_of_sight = QCheckBox("Clear line of sight")
        self.channel = QLineEdit(); self.channel.setPlaceholderText("e.g., Wi-Fi ch. 6 / BLE 1M")
        self.tx_power = QLineEdit(); self.tx_power.setPlaceholderText("e.g., 10 dBm / default")
        self.obstacles = QLineEdit(); self.obstacles.setPlaceholderText("Walls, people, foliage, metal…")
        self.notes = QPlainTextEdit(); self.notes.setPlaceholderText("Anything that could affect repeatability")
        for label, field in (("Operator", self.operator), ("Technology", self.radio_technology), ("Communication mode", self.communication_mode), ("Endpoint separation", self.distance_m), ("Net rotation", self.rotation_deg), ("Echo timeout", self.echo_timeout_ms), ("Distance to reference point", self.reference_distance_m), ("Environment", self.environment), ("Location", self.location), ("Visibility", self.line_of_sight), ("Channel / PHY", self.channel), ("Transmit power", self.tx_power), ("Obstacles", self.obstacles), ("Notes", self.notes)):
            form.addRow(label, field)
        layout.addWidget(setup_group)

        self.status = QLabel("Ready to save a trial setup.")
        self.status.setWordWrap(True)
        save_button = QPushButton("Save trial setup")
        save_button.clicked.connect(self._save_trial)
        buttons = QHBoxLayout()
        buttons.addWidget(save_button)
        self.copy_trial_id_button = QPushButton("Copy trial ID")
        self.copy_trial_id_button.setEnabled(False)
        self.copy_trial_id_button.clicked.connect(self._copy_trial_id)
        buttons.addWidget(self.copy_trial_id_button)
        layout.addLayout(buttons)
        layout.addWidget(self.status)
        setup_content = QWidget(); setup_content.setLayout(layout)
        setup_scroll = QScrollArea(); setup_scroll.setWidgetResizable(True); setup_scroll.setWidget(setup_content)
        tabs = QTabWidget(); tabs.addTab(setup_scroll, "Run setup")
        self.live_monitor = LiveMonitor(self.repository); self.live_monitor.trial_finished.connect(self._refresh_summaries)
        tabs.addTab(self.live_monitor, "Live monitor")
        results = QWidget(); results_layout = QVBoxLayout(results)
        results_layout.addWidget(QLabel("Open a completed summary. Attempt folders also contain raw events, reports, and graphs."))
        results_layout.addWidget(self._summary_group(), 1)
        tabs.addTab(results, "Saved results")
        self.setCentralWidget(tabs)
        self._refresh_summaries()

    def _summary_group(self) -> QGroupBox:
        group = QGroupBox("Saved trial summary")
        layout = QVBoxLayout(group)
        selector_layout = QHBoxLayout()
        self.summary_trial_selector = QComboBox()
        self.summary_trial_selector.currentTextChanged.connect(self._load_selected_summary)
        refresh_button = QPushButton("Refresh summaries")
        refresh_button.clicked.connect(self._refresh_summaries)
        selector_layout.addWidget(QLabel("Trial"))
        selector_layout.addWidget(self.summary_trial_selector, stretch=1)
        selector_layout.addWidget(refresh_button)
        self.show_raw_summary = QCheckBox("Show raw JSON")
        self.show_raw_summary.toggled.connect(lambda _checked: self._load_selected_summary(self.summary_trial_selector.currentText()))
        self.summary_view = QPlainTextEdit()
        self.summary_view.setReadOnly(True)
        self.summary_view.setMinimumHeight(180)
        layout.addLayout(selector_layout)
        layout.addWidget(self.show_raw_summary)
        layout.addWidget(self.summary_view)
        return group

    def _endpoint_group(self, title: str) -> QGroupBox:
        group = QGroupBox(title)
        form = QFormLayout(group)
        prefix = "a" if title.endswith("A") else "b"
        device = QComboBox(); device.addItems(DEVICE_TYPES)
        label = QLineEdit(); label.setPlaceholderText("e.g., pico2w-01")
        identifier = QLineEdit(); identifier.setPlaceholderText("MAC, USB serial, or inventory tag")
        antenna = QComboBox(); antenna.addItems(ANTENNA_TYPES)
        firmware = QLineEdit(); firmware.setPlaceholderText("Firmware/build version")
        setattr(self, f"{prefix}_device", device); setattr(self, f"{prefix}_label", label)
        setattr(self, f"{prefix}_identifier", identifier); setattr(self, f"{prefix}_antenna", antenna); setattr(self, f"{prefix}_firmware", firmware)
        for field_name, field in (("Device", device), ("Label", label), ("Identifier", identifier), ("Antenna", antenna), ("Firmware", firmware)):
            form.addRow(field_name, field)
        return group

    def _endpoint(self, prefix: str) -> Endpoint:
        return Endpoint(
            device_type=getattr(self, f"{prefix}_device").currentText(),
            label=getattr(self, f"{prefix}_label").text(),
            identifier=getattr(self, f"{prefix}_identifier").text(),
            antenna_type=getattr(self, f"{prefix}_antenna").currentText(),
            firmware_version=getattr(self, f"{prefix}_firmware").text(),
        )

    def _save_trial(self) -> None:
        reference_distance = self.reference_distance_m.value() or None
        trial = self.repository.create_automatic_trial(
            operator=self.operator.text(), endpoint_a=self._endpoint("a"), endpoint_b=self._endpoint("b"),
            radio_technology=self.radio_technology.currentText(), communication_mode=self.communication_mode.text(),
            distance_m=self.distance_m.value(), reference_distance_m=reference_distance,
            environment=self.environment.text(), location=self.location.text(), line_of_sight=self.line_of_sight.isChecked(),
            obstacles=self.obstacles.text(), channel=self.channel.text(), tx_power=self.tx_power.text(), notes=self.notes.toPlainText(),
            rotation_deg=self.rotation_deg.value(), timeout_ms=self.echo_timeout_ms.value(),
        )
        try:
            path = self.repository.save(trial)
        except (ValueError, FileExistsError) as error:
            QMessageBox.warning(self, "Cannot save trial", str(error))
            return
        self.current_trial_id = trial.trial_id
        self.copy_trial_id_button.setEnabled(True)
        self.status.setText(f"Saved {trial.trial_id} to {path}")
        self._refresh_summaries(select_trial_id=trial.trial_id)
        self.live_monitor.refresh_trials()

    def _copy_trial_id(self) -> None:
        if not self.current_trial_id:
            return
        QGuiApplication.clipboard().setText(self.current_trial_id)
        self.status.setText(f"Copied trial ID: {self.current_trial_id}")

    def _refresh_summaries(self, select_trial_id: str | None = None) -> None:
        previous = select_trial_id or self.summary_trial_selector.currentText()
        trial_ids = self.repository.list_trial_ids()
        self.summary_trial_selector.blockSignals(True)
        self.summary_trial_selector.clear()
        self.summary_trial_selector.addItems(trial_ids)
        if previous in trial_ids:
            self.summary_trial_selector.setCurrentText(previous)
        self.summary_trial_selector.blockSignals(False)
        self._load_selected_summary(self.summary_trial_selector.currentText())

    def _load_selected_summary(self, trial_id: str) -> None:
        if not trial_id:
            self.summary_view.setPlainText("No saved trials yet.")
            return
        self.current_trial_id = trial_id
        self.copy_trial_id_button.setEnabled(True)
        summary = self.repository.load_any_summary(trial_id)
        if summary is None:
            self.summary_view.setPlainText(
                f"No summary saved for {trial_id}.\n"
                "Run the serial collector, then click Refresh summaries."
            )
            return
        if self.show_raw_summary.isChecked():
            self.summary_view.setPlainText(json.dumps(summary, indent=2))
            return
        metadata = summary.get("metadata") or {}
        metrics = summary.get("metrics") or {}
        lines = [f"Trial: {summary.get('trial_id', trial_id)}"]
        if metadata.get("condition_id"):
            lines.append(f"Condition: {metadata['condition_id']}  |  Attempt: {metadata.get('attempt_number')}")
        lines.extend([
            f"Endpoints: {metadata.get('endpoint_a', {}).get('label', '?')}  ↔  {metadata.get('endpoint_b', {}).get('label', '?')}",
            f"Setup: {metadata.get('distance_m', '?')} m, rotation {metadata.get('rotation_deg', '?')}°, timeout {metadata.get('timeout_ms', '?')} ms",
            f"Environment: {metadata.get('environment', '?')} | {metadata.get('location', '')}",
            "", "Key measurements:",
        ])
        preferred = ("metrics_reliability", "packets_transmitted_observed_by_pico", "packets_received_observed_by_esp32", "valid_echoes_received_by_pico", "on_time_echoes", "late_echoes", "unobserved_after_grace", "end_to_end_echo_success_ratio", "rtt_median_us", "rtt_p95_us", "rtt_p99_us", "rssi_median_dbm", "goodput_payload_bytes_per_second")
        for key in preferred:
            if key in metrics: lines.append(f"  {key}: {metrics[key]}")
        if not any(key in metrics for key in preferred):
            lines.append("  No derived summary has been saved yet.")
        lines.extend(["", "Enable ‘Show raw JSON’ for every recorded field."])
        self.summary_view.setPlainText("\n".join(lines))
