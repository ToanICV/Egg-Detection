"""
StateController tối giản để quản lý vòng đời FSM dựa trên các lớp State trong states.py.

Chức năng:
- Giữ current_state và Context, đảm bảo gọi enter/exit đúng thứ tự khi chuyển trạng thái.
- Chuyển tiếp event vào state hiện tại thông qua handle(); nếu handle() trả về state mới
  thì tự động exit() state cũ và enter() state mới.
- Cung cấp API start() để khởi động FSM từ một state khởi tạo.
- Ghi log quá trình chuyển trạng thái (nếu ctx.logger có sẵn).

Ngữ cảnh sử dụng:
- Dùng cho kiến trúc FSM "thuần Python" trong states.py, không phụ thuộc thư viện bên ngoài.
- Controller này có thể được nhúng trong service điều khiển, nhận event từ Vision/Sensor/Serial/Timer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Any

from . import states as sm_states


@dataclass
class Event:
    """Event chuẩn tối giản: có type và payload.

    Bạn có thể dùng trực tiếp lớp này, hoặc truyền bất cứ object nào có field
    `type` và `payload` tương thích.
    """

    type: str
    payload: Any = None


class StateController:
    """Điều phối FSM dựa trên các State trong states.py."""

    def __init__(self, ctx: sm_states.Context, initial_state: Optional[sm_states.BaseState] = None) -> None:
        self.ctx = ctx
        self.current_state: Optional[sm_states.BaseState] = None
        if initial_state is not None:
            self.start(initial_state)

    def start(self, initial_state: sm_states.BaseState) -> None:
        """Khởi động FSM với trạng thái ban đầu."""
        if self.current_state is not None:
            raise RuntimeError("FSM already started")
        self.current_state = initial_state
        self._log_state("ENTER", self.current_state)
        self.current_state.enter(self.ctx)

    def dispatch(self, event: Any) -> None:
        """Gửi một event vào FSM.

        Tham số `event` có thể là:
        - instance Event ở trên
        - hoặc bất cứ object có thuộc tính `type` và `payload`.
        """
        if self.current_state is None:
            raise RuntimeError("FSM not started. Call start(initial_state) first.")

        # Chuẩn hóa event
        ev = event if hasattr(event, "type") and hasattr(event, "payload") else Event(type=str(event), payload=None)
        self._log_event(ev)

        # Cho state xử lý
        try:
            next_state = self.current_state.handle(self.ctx, ev)
        except Exception:
            # Đảm bảo lỗi trong handle không phá hỏng controller; log và giữ nguyên state
            self._log_error("HANDLE_ERROR", ev)
            raise

        # Nếu state yêu cầu chuyển
        if next_state and next_state is not self.current_state:
            self._transition(next_state)

    def _transition(self, next_state: sm_states.BaseState) -> None:
        prev = self.current_state
        if prev is None:
            # Không nên xảy ra, nhưng phòng hờ
            self.current_state = next_state
            self._log_state("ENTER", self.current_state)
            self.current_state.enter(self.ctx)
            return

        self._log_state("EXIT", prev)
        try:
            prev.exit(self.ctx)
        finally:
            self.current_state = next_state
            self._log_state("ENTER", self.current_state)
            self.current_state.enter(self.ctx)

    # --- Logging helpers ---
    def _log_state(self, action: str, state: sm_states.BaseState) -> None:
        logger = getattr(self.ctx, "logger", None)
        if logger:
            logger.info("FSM %s: %s", action, getattr(state, "id", state.__class__.__name__))

    def _log_event(self, ev: Event) -> None:
        logger = getattr(self.ctx, "logger", None)
        if logger:
            logger.debug("FSM EVENT: %s payload=%s", ev.type, getattr(ev, "payload", None))

    def _log_error(self, where: str, ev: Event) -> None:
        logger = getattr(self.ctx, "logger", None)
        if logger:
            logger.exception("FSM ERROR at %s, event=%s", where, ev.type)
