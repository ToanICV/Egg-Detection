"""
Chạy thử FSM mô phỏng cho robot nhặt trứng.

- Khởi tạo StateController với RobotContext mô phỏng.
- Chạy luồng: Idle -> (start) -> ScanAndMove -> (eggs_detected) -> PickUpEgg -> (arm done) -> ScanAndMove
- Sau đó mô phỏng nhánh quay: ScanAndMove -> (obstacle_too_close) -> TurnFirst -> (base stopped) -> ScanOnly -> (timeout) -> MoveOnly -> (timeout) -> TurnSecond -> ScanAndMove

Cách chạy:
    python -m Robot-SM.state-machine.run_demo
"""
from __future__ import annotations

import logging
import threading
import time

from .controller import StateController, Event
from .context import RobotContext
from . import states as sm_states


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logger = logging.getLogger("demo_runner")

    # Tạo controller trước, sau đó gán ctx (RobotContext cần controller để đẩy event timer/polling)
    fsm = StateController(ctx=None)  # type: ignore[arg-type]
    ctx = RobotContext(controller=fsm, logger=logging.getLogger("robot_sm"))
    fsm.ctx = ctx  # gắn context thực

    # Bắt đầu ở Idle, sau đó start để vào ScanAndMove
    fsm.start(sm_states.IdleState())
    fsm.dispatch(Event(type="start"))

    # Mô phỏng phát hiện trứng sau 1.5 giây
    def simulate_pick_flow():
        time.sleep(1.5)
        ctx.simulate_eggs_detected([
            {"x_mm": 120, "y_mm": -45, "y_norm": 0.5},
        ])
        # Arm sẽ báo busy 2 lần (polling mock) rồi done → quay lại ScanAndMove

    # Mô phỏng nhánh quay sau luồng nhặt
    def simulate_turn_flow():
        # đợi cho luồng pick kết thúc ~4s
        time.sleep(4.0)
        # phát obstacle gần để kích hoạt quay từ ScanAndMove
        ctx.simulate_obstacle_close(20)
        # TurnFirst sẽ bật polling base_state và timer 10s; polling mock báo 'stopped' → ScanOnly
        # ScanOnly đặt timer 5s; hết thời gian → MoveOnly
        # MoveOnly đặt timer 5s; hết thời gian → TurnSecond → ScanAndMove

    threading.Thread(target=simulate_pick_flow, daemon=True).start()
    threading.Thread(target=simulate_turn_flow, daemon=True).start()

    # Giữ chương trình chạy một lúc để quan sát log
    logger.info("Demo đang chạy trong ~15 giây...")
    time.sleep(15)
    logger.info("Kết thúc demo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
