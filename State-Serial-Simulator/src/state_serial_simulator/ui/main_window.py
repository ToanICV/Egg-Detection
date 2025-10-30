"""Main Qt window for the simulator."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

from PyQt5 import QtCore, QtGui, QtWidgets, uic

from state_serial_simulator.state_machine.model import StateDefinition, TransitionResult
from state_serial_simulator.utils.events import EventBus


class MainWindow(QtWidgets.QMainWindow):
    """Main window coordinating UI widgets with the event bus."""

    def __init__(
        self,
        bus: EventBus,
        states: Mapping[str, StateDefinition],
        ui_path: Path,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._bus = bus
        self._states = states
        self._ui_path = ui_path

        uic.loadUi(str(ui_path), self)

        self._serial_status_label: QtWidgets.QLabel = self.findChild(QtWidgets.QLabel, "labelSerialStatus")
        self._current_state_label: QtWidgets.QLabel = self.findChild(QtWidgets.QLabel, "labelCurrentState")
        self._states_list: QtWidgets.QListWidget = self.findChild(QtWidgets.QListWidget, "listStates")
        self._history_list: QtWidgets.QListWidget = self.findChild(QtWidgets.QListWidget, "listHistory")
        self._log_text: QtWidgets.QPlainTextEdit = self.findChild(QtWidgets.QPlainTextEdit, "textLog")

        self._setup_state_list()
        self._connect_bus()

    def _setup_state_list(self) -> None:
        """Initialise the state list widget."""
        self._states_list.clear()
        self._states_list.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self._states_list.setFocusPolicy(QtCore.Qt.NoFocus)
        self._states_list.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        for state in self._states.values():
            item = QtWidgets.QListWidgetItem(state.label)
            item.setData(QtCore.Qt.UserRole, state.name)
            self._states_list.addItem(item)

    def _connect_bus(self) -> None:
        """Connect event bus signals to UI handlers."""
        self._bus.state_changed.connect(self._on_state_changed)
        self._bus.transition_result.connect(self._on_transition_result)
        self._bus.log_event.connect(self._on_log_entry)
        self._bus.serial_status.connect(self._on_serial_status)
        self._bus.serial_message.connect(self._on_serial_message)

    def register_event_button(self, event: str, button_name: str) -> None:
        """Wire a button to emit a specific event through the bus."""
        button = self.findChild(QtWidgets.QPushButton, button_name)
        if not button:
            raise ValueError(f"Button '{button_name}' not found in UI definition.")

        button.clicked.connect(lambda _checked=False, ev=event: self._bus.trigger_event.emit(ev))
        button.setProperty("simEvent", event)
        button.setToolTip(f"Phat su kien {event}")

    def set_current_state(self, state_name: str, state_label: str | None = None) -> None:
        """Update the current state display."""
        label = state_label or state_name
        self._current_state_label.setText(f"Trang thai hien tai: {label}")
        self._highlight_state(state_name)

    def append_history(self, result: TransitionResult) -> None:
        """Append a transition result to the history list."""
        text = f"{result.previous_state} --({result.event})-> {result.next_state}"
        item = QtWidgets.QListWidgetItem(text)
        self._history_list.insertItem(0, item)
        self._history_list.setCurrentItem(item)

    def append_log(self, level: str, message: str) -> None:
        """Append a log entry to the log text box."""
        self._log_text.appendPlainText(f"[{level}] {message}")
        self._log_text.verticalScrollBar().setValue(self._log_text.verticalScrollBar().maximum())

    def _highlight_state(self, state_name: str) -> None:
        """Highlight the state in the list widget."""
        for index in range(self._states_list.count()):
            item = self._states_list.item(index)
            if item.data(QtCore.Qt.UserRole) == state_name:
                item.setBackground(QtGui.QColor("#e0ffe0"))
            else:
                item.setBackground(QtGui.QColor("#ffffff"))

    @QtCore.pyqtSlot(str, str)
    def _on_state_changed(self, previous_state: str, current_state: str) -> None:
        state = self._states.get(current_state)
        label = state.label if state else current_state
        self.set_current_state(current_state, label)

    @QtCore.pyqtSlot(dict)
    def _on_transition_result(self, payload: dict) -> None:
        result = TransitionResult(
            previous_state=payload.get("previous_state", ""),
            event=payload.get("event", ""),
            next_state=payload.get("next_state", ""),
            accepted=payload.get("accepted", False),
            message=payload.get("message", ""),
        )
        self.append_history(result)
        level = "INFO" if result.accepted else "WARN"
        self.append_log(level, result.message)

    @QtCore.pyqtSlot(str, str)
    def _on_log_entry(self, level: str, message: str) -> None:
        self.append_log(level, message)

    @QtCore.pyqtSlot(bool, str)
    def _on_serial_status(self, connected: bool, message: str) -> None:
        self._serial_status_label.setText(f"Ket noi serial: {message}")
        palette = self._serial_status_label.palette()
        color = QtGui.QColor("#2e7d32" if connected else "#c62828")
        palette.setColor(QtGui.QPalette.WindowText, color)
        self._serial_status_label.setPalette(palette)

    @QtCore.pyqtSlot(str, str, str)
    def _on_serial_message(self, origin: str, intent: str, payload: str) -> None:
        label_origin = origin or "UNKNOWN"
        label_intent = intent or "UNKNOWN"
        self.append_log("SERIAL", f"[{label_origin}][{label_intent}] RX: {payload}")


__all__ = ["MainWindow"]
