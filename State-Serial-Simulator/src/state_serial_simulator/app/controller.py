"""Main application controller coordinating UI, state machine and serial."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtWidgets

from state_serial_simulator.config.settings import Settings, load_settings
from state_serial_simulator.serial_io.manager import SerialConfig, SerialManager
from state_serial_simulator.simulators.actor import ActorSimulator
from state_serial_simulator.simulators.arm import ArmSimulator
from state_serial_simulator.state_machine.machine import StateMachine
from state_serial_simulator.utils.events import EventBus
from state_serial_simulator.utils.message_parser import classify_message
from state_serial_simulator.ui.main_window import MainWindow


class AppController(QtCore.QObject):
    """High level orchestrator creating and wiring subsystems."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        super().__init__()

        self._settings = settings or load_settings()
        self._app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        self._bus = EventBus()
        self._logger = logging.getLogger("state_serial_simulator")
        self._configure_logging()

        self._state_machine = StateMachine(
            states=self._settings.states,
            start_state=self._settings.start_state,
        )

        self._arm_sim = ArmSimulator()
        self._actor_sim = ActorSimulator()

        serial_config = SerialConfig(
            port=self._settings.serial_port,
            baudrate=self._settings.serial_baudrate,
            timeout=self._settings.serial_timeout,
        )
        self._serial_manager = SerialManager(serial_config)
        self._serial_manager.signals.message_received.connect(self._on_serial_message)
        self._serial_manager.signals.status_changed.connect(self._bus.serial_status.emit)

        ui_path = Path(__file__).resolve().parents[3] / "resources" / "ui" / "main_window.ui"
        self._window = MainWindow(self._bus, self._settings.states, ui_path)
        self._register_buttons()

        # Wiring between event bus and controller logic.
        self._bus.trigger_event.connect(self._on_trigger_event)

        # Initial UI state.
        current_state = self._state_machine.current_state
        self._window.set_current_state(current_state.name, current_state.label)
        self._bus.serial_status.emit(False, f"Chua ket noi {self._settings.serial_port}")

    def _configure_logging(self) -> None:
        """Configure Python logging and integrate with the UI bus."""
        self._logger.setLevel(logging.INFO)
        if not self._logger.handlers:
            formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

            file_handler = logging.FileHandler(self._settings.log_file, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)

            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setLevel(logging.INFO)
            stream_handler.setFormatter(formatter)
            self._logger.addHandler(stream_handler)

    def _register_buttons(self) -> None:
        """Wire UI buttons to simulator events."""
        mapping = {
            "buttonStartCycle": "START_CYCLE",
            "buttonReset": "RESET",
            "buttonArmReady": self._arm_sim.emit_ready(),
            "buttonArmError": self._arm_sim.emit_error(),
            "buttonActorStart": self._actor_sim.emit_start(),
            "buttonActorComplete": self._actor_sim.emit_complete(),
            "buttonActorFault": self._actor_sim.emit_fault(),
        }

        for button_name, event in mapping.items():
            self._window.register_event_button(event, button_name)

    @QtCore.pyqtSlot(str)
    def _on_trigger_event(self, event: str) -> None:
        """Handle events emitted from the UI."""
        self._dispatch_event(event, source="UI")

    def _dispatch_event(self, event: str, source: str) -> None:
        """Send an event through the state machine and serial interface."""
        self._log("INFO", f"{source} phat su kien {event}")
        result = self._state_machine.dispatch(event)

        payload = {
            "previous_state": result.previous_state,
            "event": result.event,
            "next_state": result.next_state,
            "accepted": result.accepted,
            "message": result.message,
        }
        self._bus.transition_result.emit(payload)

        if result.accepted and result.changed:
            self._bus.state_changed.emit(result.previous_state, result.next_state)
            self._run_state_side_effects(result.next_state)

        if result.accepted:
            serial_payload = self._settings.serial_payload_for(event)
            if serial_payload:
                self._log("INFO", f"TX -> {serial_payload}")
                self._serial_manager.send(serial_payload)
        else:
            self._log("WARN", result.message)

    def _run_state_side_effects(self, state_name: str) -> None:
        """Execute side effects tied to specific states."""
        if state_name == "ARM_CONFIRMED" and self._settings.auto_start_actor:
            QtCore.QTimer.singleShot(150, lambda: self._dispatch_event(self._actor_sim.emit_start(), "Auto"))

    @QtCore.pyqtSlot(str)
    def _on_serial_message(self, payload: str) -> None:
        """Handle payloads arriving from the serial port."""
        info = classify_message(payload)
        self._bus.serial_message.emit(info.origin, info.intent, info.payload)
        self._logger.info("SERIAL RX [%s/%s] %s", info.origin, info.intent, info.payload)
        if payload.startswith("EVENT:"):
            event = payload.split(":", 1)[1].strip()
            self._dispatch_event(event, source="SERIAL")

    def _log(self, level: str, message: str) -> None:
        """Log message to both logging module and UI."""
        self._logger.log(getattr(logging, level, logging.INFO), message)
        self._bus.log_event.emit(level, message)

    def run(self) -> int:
        """Start the simulator event loop."""
        self._log("INFO", "Khoi dong State Serial Simulator")
        self._serial_manager.start()
        self._window.show()
        exit_code = self._app.exec_()
        self._serial_manager.stop()
        self._log("INFO", "Da thoat State Serial Simulator")
        return exit_code
