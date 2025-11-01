"""
Context tối thiểu để chạy FSM trong states.py cùng với StateController.

Chức năng:
- Cung cấp logger và các API mà states.Context mong đợi.
- Mô phỏng hành vi thiết bị: các lệnh cmd_* chỉ ghi log và trả về True.
- Hỗ trợ timer: start_timer/cancel_timer phát Event("timer", payload=name) về StateController.
- Hỗ trợ polling tối giản: set_polling("base_state"|"arm_state", True/False, interval)
  sẽ phát định kỳ Event tương ứng để FSM có thể chuyển trạng thái khi demo.

Ghi chú:
- Đây là Context mô phỏng để demo luồng FSM. Khi tích hợp thật, hãy thay thế
  các cmd_* bằng lệnh gửi qua SerialComm và cập nhật set_polling đọc trạng thái thực.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Dict, Callable

from .controller import StateController, Event
from ..comm.serial_comm import SerialComm


def _to_hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


class RobotContext:
    """Context phần cứng tối thiểu, tương thích với states.Context Protocol.

    Tích hợp SerialComm để gửi lệnh thực qua cổng nối tiếp. Nếu chưa có parser phản hồi,
    các phương thức read_state chỉ ghi log dữ liệu nhận được và demo polling vẫn phát
    sự kiện giả để FSM hoạt động.
    """

    def __init__(self, controller: StateController, logger: Optional[logging.Logger] = None,
                 port: str = "COM14", baudrate: int = 9600):
        self._controller = controller
        self._logger = logger or logging.getLogger("robot_sm.context")
        self.last_detections = []  # list[dict]
        self.obstacle_cm: Optional[float] = None
        # Serial
        self.comm = SerialComm(port, baudrate)
        # Quản lý timers và polling
        self._timers: Dict[str, threading.Timer] = {}
        self._pollers: Dict[str, threading.Event] = {}
        self._arm_busy_counts: int = 0  # mô phỏng arm bận vài lần trước khi done

    # ---- Logger ----
    @property
    def logger(self) -> logging.Logger:
        return self._logger

    # ---- Serial command helpers ----
    def _send_command(self, command: str, **kwargs) -> bool:
        try:
            payload = SerialComm.build_command(command, **kwargs)
            self.logger.info("SEND %s: %s", command, _to_hex(payload))
            written = self.comm.send(payload)
            if written <= 0:
                self.logger.error("WRITE FAILED: %s", command)
                return False
            # Đọc nhanh phản hồi (nếu có)
            resp = self.comm.receive()
            if resp:
                self.logger.info("RESP %s (%d bytes): %s", command, len(resp), _to_hex(resp))
            return True
        except Exception as e:
            self.logger.exception("ERROR sending %s: %s", command, e)
            return False

    # ---- Serial commands ----
    def cmd_base_forward(self) -> bool:
        return self._send_command("base_forward")

    def cmd_base_stop(self) -> bool:
        return self._send_command("base_stop")

    def cmd_base_turn90(self) -> bool:
        return self._send_command("base_turn90")

    def cmd_base_read_state(self) -> bool:
        return self._send_command("base_read_state")

    def cmd_arm_pick(self, x_mm: int, y_mm: int) -> bool:
        ok = self._send_command("pickup", x=x_mm, y=y_mm)
        if ok:
            # reset mô phỏng để báo busy vài nhịp rồi done (cho tới khi có parser thực)
            self._arm_busy_counts = 0
        return ok

    def cmd_arm_read_state(self) -> bool:
        return self._send_command("arm_read_state")

    # ---- Timers ----
    def start_timer(self, name: str, seconds: float) -> None:
        self.cancel_timer(name)
        def fire():
            self.logger.debug("TIMER FIRED: %s", name)
            self._controller.dispatch(Event(type="timer", payload=name))
        t = threading.Timer(seconds, fire)
        self._timers[name] = t
        t.start()
        self.logger.debug("TIMER START: %s (%.2fs)", name, seconds)

    def cancel_timer(self, name: str) -> None:
        t = self._timers.pop(name, None)
        if t is not None:
            t.cancel()
            self.logger.debug("TIMER CANCEL: %s", name)

    # ---- Polling ----
    def set_polling(self, topic: str, enable: bool, interval_s: float = 1.0) -> None:
        key = f"poll_{topic}"
        # stop existing
        stop_evt = self._pollers.pop(key, None)
        if stop_evt is not None:
            stop_evt.set()
            self.logger.debug("POLL STOP: %s", topic)
        if not enable:
            return

        stop_evt = threading.Event()
        self._pollers[key] = stop_evt

        def loop_base_state():
            self.logger.debug("POLL START: base_state every %.2fs", interval_s)
            while not stop_evt.is_set():
                if self.cmd_base_read_state():
                    parsed = self.comm.read_parsed(timeout_s=0.5)
                    if parsed and parsed.get("source") == "actor" and parsed.get("type") == "state":
                        moving = bool(parsed.get("moving", False))
                        self.obstacle_cm = parsed.get("obstacle_cm", None)
                        payload = "turning" if moving else "stopped"
                        self._controller.dispatch(Event(type="base_state", payload=payload))
                stop_evt.wait(interval_s)

        def loop_arm_state():
            self.logger.debug("POLL START: arm_state every %.2fs", interval_s)
            while not stop_evt.is_set():
                if self.cmd_arm_read_state():
                    parsed = self.comm.read_parsed(timeout_s=0.5)
                    if parsed and parsed.get("source") == "arm" and parsed.get("type") == "state":
                        busy = bool(parsed.get("arm_busy", False))
                        self._controller.dispatch(Event(type="arm_state", payload=("busy" if busy else "done")))
                stop_evt.wait(interval_s)

        loops: Dict[str, Callable[[], None]] = {
            "base_state": loop_base_state,
            "arm_state": loop_arm_state,
        }
        loop_fn = loops.get(topic)
        if loop_fn is None:
            self.logger.warning("POLL UNKNOWN TOPIC: %s (ignored)", topic)
            return

        th = threading.Thread(target=loop_fn, name=key, daemon=True)
        th.start()

    # ---- Helper for demo ----
    def simulate_eggs_detected(self, eggs):
        """Phát sự kiện eggs_detected để kích hoạt luồng PickUp."""
        self.last_detections = eggs or []
        self._controller.dispatch(Event(type="eggs_detected", payload=self.last_detections))

    def simulate_obstacle_close(self, distance_cm: float):
        self.obstacle_cm = distance_cm
        if distance_cm < 30:
            self._controller.dispatch(Event(type="obstacle_too_close", payload=distance_cm))
