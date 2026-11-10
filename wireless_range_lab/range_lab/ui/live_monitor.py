"""Compact live collector controls and visual telemetry monitor."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from PyQt5.QtCore import QProcess, pyqtSignal
from PyQt5.QtWidgets import (QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QPlainTextEdit, QSpinBox,
                             QVBoxLayout, QWidget)

from range_lab.storage import TrialRepository
from range_lab.trial_ids import parse_trial_id

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
except ImportError:  # The UI remains usable before optional plot dependency installation.
    FigureCanvasQTAgg = None


class LiveMonitor(QWidget):
    trial_finished = pyqtSignal(str)

    def __init__(self, repository: TrialRepository) -> None:
        super().__init__(); self.repository = repository; self.process: QProcess | None = None
        self.stop_file: Path | None = None; self.rtt: list[tuple[int, float]] = []; self.rssi: list[tuple[int, int]] = []
        self.sent = self.echoes = self.deadlines = self.esp_received = 0
        self._build(); self.refresh_trials()

    def _build(self) -> None:
        layout = QVBoxLayout(self)
        controls = QGroupBox("Live collection") ; form = QFormLayout(controls)
        self.trial_id = QComboBox(); refresh = QPushButton("Refresh trials"); refresh.clicked.connect(self.refresh_trials)
        trial_row = QHBoxLayout(); trial_row.addWidget(self.trial_id, 1); trial_row.addWidget(refresh); form.addRow("Saved attempt", trial_row)
        self.pico_port = QLineEdit("COM11"); self.esp_port = QLineEdit("COM12")
        self.duration = QSpinBox(); self.duration.setRange(0, 86_400); self.duration.setValue(60); self.duration.setSuffix(" s (0 = manual)")
        form.addRow("Pico port", self.pico_port); form.addRow("ESP32 port", self.esp_port); form.addRow("Collection duration", self.duration)
        buttons = QHBoxLayout(); self.start = QPushButton("Start live collection"); self.stop = QPushButton("Stop and finalize"); self.stop.setEnabled(False)
        self.start.clicked.connect(self.start_collection); self.stop.clicked.connect(self.stop_collection); buttons.addWidget(self.start); buttons.addWidget(self.stop); form.addRow(buttons)
        layout.addWidget(controls)
        self.counters = QLabel("Waiting for a saved attempt."); self.counters.setWordWrap(True); layout.addWidget(self.counters)
        if FigureCanvasQTAgg:
            self.figure = Figure(figsize=(7, 4), tight_layout=True); self.canvas = FigureCanvasQTAgg(self.figure)
            self.rtt_axis = self.figure.add_subplot(211); self.rssi_axis = self.figure.add_subplot(212, sharex=self.rtt_axis)
            self.rtt_axis.set_ylabel("RTT (ms)"); self.rssi_axis.set_ylabel("RSSI (dBm)"); self.rssi_axis.set_xlabel("Sequence")
            layout.addWidget(self.canvas, 1)
        else:
            self.figure = self.canvas = None; layout.addWidget(QLabel("Install matplotlib from requirements.txt to enable live plots."))
        self.events = QPlainTextEdit(); self.events.setReadOnly(True); self.events.document().setMaximumBlockCount(300); self.events.setMinimumHeight(130); layout.addWidget(self.events)

    def refresh_trials(self) -> None:
        current = self.trial_id.currentText(); ids = []
        for value in self.repository.list_trial_ids():
            try: parse_trial_id(value); ids.append(value)
            except ValueError: pass
        self.trial_id.clear(); self.trial_id.addItems(ids)
        if current in ids: self.trial_id.setCurrentText(current)

    def start_collection(self) -> None:
        trial_id = self.trial_id.currentText()
        if not trial_id: self.events.appendPlainText("Save a setup first."); return
        try:
            directory = self.repository.attempt_directory(trial_id)
            self.repository.ensure_collection_available(trial_id)
        except ValueError as error: self.events.appendPlainText(str(error)); return
        except (FileNotFoundError, FileExistsError) as error:
            self.events.appendPlainText(str(error)); return
        self.stop_file = directory / ".stop-request"
        if self.stop_file.exists(): self.stop_file.unlink()
        self.rtt.clear(); self.rssi.clear(); self.sent = self.echoes = self.deadlines = self.esp_received = 0; self._draw()
        script = Path(__file__).resolve().parents[2] / "tools" / "collect_dual_serial.py"
        arguments = [str(script), "--trial-id", trial_id, "--pico-port", self.pico_port.text().strip(), "--esp32-port", self.esp_port.text().strip(), "--stop-file", str(self.stop_file)]
        if self.duration.value(): arguments += ["--duration-s", str(self.duration.value())]
        self.process = QProcess(self); self.process.readyReadStandardOutput.connect(self._read_stdout); self.process.readyReadStandardError.connect(self._read_stderr); self.process.finished.connect(self._finished)
        self.process.start(sys.executable, arguments); self.start.setEnabled(False); self.stop.setEnabled(True); self.events.appendPlainText(f"Starting {trial_id}…")

    def stop_collection(self) -> None:
        if self.stop_file: self.stop_file.touch(); self.events.appendPlainText("Clean stop requested; waiting for summary.")
        self.stop.setEnabled(False)

    def _read_stdout(self) -> None:
        if not self.process: return
        for line in bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace").splitlines(): self._handle_line(line)

    def _read_stderr(self) -> None:
        if self.process: self.events.appendPlainText(bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace").strip())

    def _handle_line(self, line: str) -> None:
        self.events.appendPlainText(line)
        try: event = json.loads(line)
        except json.JSONDecodeError: return
        # The collector also prints human-readable progress and a final JSON
        # summary. Only individual telemetry records are event objects.
        if not isinstance(event, dict):
            return
        event_name, status, source = event.get("event"), event.get("status"), event.get("collector_source")
        if source == "pico" and event_name == "packet_tx" and status == "sent":
            self.sent += 1; sequence = event.get("sequence"); rssi = event.get("rssi_dbm")
            if isinstance(sequence, int) and isinstance(rssi, int): self.rssi.append((sequence, rssi))
        elif source == "esp32" and event_name == "packet_rx" and status == "received": self.esp_received += 1
        elif source == "pico" and event_name == "packet_rx" and status in {"echo_on_time", "echo_late"}:
            self.echoes += 1; sequence, rtt = event.get("sequence"), event.get("rtt_us")
            if isinstance(sequence, int) and isinstance(rtt, int): self.rtt.append((sequence, rtt / 1000))
        elif source == "pico" and event_name == "packet_deadline": self.deadlines += 1
        self.counters.setText(f"Pico sent: {self.sent}   ESP32 received: {self.esp_received}   Valid echoes: {self.echoes}   Deadlines: {self.deadlines}")
        self._draw()

    def _draw(self) -> None:
        if not self.canvas: return
        self.rtt_axis.clear(); self.rssi_axis.clear(); self.rtt_axis.set_ylabel("RTT (ms)"); self.rssi_axis.set_ylabel("RSSI (dBm)"); self.rssi_axis.set_xlabel("Sequence")
        if self.rtt: self.rtt_axis.plot(*zip(*self.rtt), ".-", color="#2563eb", label="valid echo"); self.rtt_axis.legend(loc="upper right")
        if self.rssi: self.rssi_axis.plot(*zip(*self.rssi), ".-", color="#059669", label="Pico RSSI"); self.rssi_axis.legend(loc="upper right")
        self.canvas.draw_idle()

    def _finished(self, _exit_code: int, _status) -> None:
        trial_id = self.trial_id.currentText()
        if self.figure and trial_id:
            output = self.repository.attempt_directory(trial_id) / "live_timeline.png"; self.figure.savefig(output, dpi=150); self.events.appendPlainText(f"Saved live graph: {output}")
        if self.stop_file and self.stop_file.exists(): self.stop_file.unlink()
        self.start.setEnabled(True); self.stop.setEnabled(False); self.trial_finished.emit(trial_id); self.refresh_trials()
