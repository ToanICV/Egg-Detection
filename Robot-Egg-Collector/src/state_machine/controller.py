"""Điều phối máy trạng thái điều khiển Robot Egg Collector."""

from __future__ import annotations

import logging
import threading
from typing import Optional

from statemachine import State, StateMachine

from services import (
    ActorStatusEvent,
    ArmStatusEvent,
    CommandResultEvent,
    DetectionEvent,
    EventBus,
    EventType,
    StopEvent,
    TimerEvent,
    TimerId,
)
from state_machine.context import ControlContext


logger = logging.getLogger("control.state_machine")


class ControlStateMachine(StateMachine):
    """Máy trạng thái điều phối toàn bộ chu trình tuần tra và nhặt trứng."""

    idle = State("Idle", initial=True)
    scan_and_move = State("ScanAndMove")
    pick_up_egg = State("PickUpEgg")
    turn_first = State("TurnFirst")
    scan_only = State("ScanOnly")
    move_only = State("MoveOnly")
    turn_second = State("TurnSecond")

    start_patrol = idle.to(scan_and_move)
    commence_pick = (
        scan_and_move.to(pick_up_egg)
        | scan_only.to(pick_up_egg)
        | move_only.to(pick_up_egg)
    )
    finish_picking = pick_up_egg.to(scan_and_move)
    start_first_turn = scan_and_move.to(turn_first)
    first_turn_complete = turn_first.to(scan_only)
    scan_timeout = scan_only.to(move_only)
    move_timer_elapsed = move_only.to(turn_second)
    second_turn_complete = turn_second.to(scan_and_move)

    def before_transition(self, event: str, source: object, target: object) -> None:
        """Ghi log trước khi chuyển trạng thái để tiện truy vết."""
        source_name = getattr(source, "id", str(source))
        target_name = getattr(target, "id", str(target))
        logger.info("🔄 STATE TRANSITION: %s → %s (trigger: %s)", source_name, target_name, event)

    def after_transition(self, event: str, source: object, target: object) -> None:
        """Ghi nhận trạng thái mới sau mỗi lần chuyển để giám sát vòng đời."""
        current_state = getattr(target, "id", str(target))
        logger.info("📍 CURRENT STATE: %s", current_state)

    def __init__(self, context: ControlContext):
        """Lưu ngữ cảnh điều khiển được chia sẻ cho toàn bộ máy trạng thái."""
        self.context = context
        super().__init__()

    # State entry hooks -----------------------------------------------------

    def on_enter_scan_and_move(self) -> None:
        """Chuẩn bị xe quay lại chế độ vừa quét vừa di chuyển liên tục."""
        logger.info("Entering state: ScanAndMove")
        self.context.cancel_scan_only_timer()
        self.context.cancel_move_only_timer()
        self.context.clear_pick_cycle()
        if not self.context.command_move_forward():
            logger.warning("Failed to command actor to move forward in ScanAndMove.")

    def on_enter_pick_up_egg(self) -> None:
        """Thiết lập hàng đợi và khởi động chu trình nhặt trứng."""
        logger.info("Entering state: PickUpEgg")
        self.context.cancel_scan_only_timer()
        self.context.cancel_move_only_timer()
        if not self.context.prepare_pick_queue():
            logger.info("No pick targets available on enter PickUpEgg; resuming patrol.")
            self.finish_picking()
            return
        if not self.context.command_next_pick():
            logger.info("Unable to start pick sequence; resuming patrol.")
            self.finish_picking()

    def on_exit_pick_up_egg(self) -> None:
        """Xóa trạng thái liên quan đến nhặt trứng khi rời khỏi state."""
        self.context.clear_pick_cycle()

    def on_enter_turn_first(self) -> None:
        """Ra lệnh quay đầu lần thứ nhất khi phát hiện vật cản phía trước."""
        logger.info("Entering state: TurnFirst")
        if not self.context.command_turn():
            logger.error("Failed to send first turn command; reverting to scan-only.")
            self.first_turn_complete()

    def on_enter_scan_only(self) -> None:
        """Dừng xe để quét tại chỗ nhằm tìm kiếm mục tiêu mới."""
        logger.info("Entering state: ScanOnly")
        self.context.cancel_move_only_timer()
        self.context.start_scan_only_timer()
        if not self.context.ensure_actor_stopped():
            logger.warning("ScanOnly: actor failed to hold position.")

    def on_exit_scan_only(self) -> None:
        """Hủy timer và dọn dẹp khi rời trạng thái quét tại chỗ."""
        self.context.cancel_scan_only_timer()

    def on_enter_move_only(self) -> None:
        """Cho phép xe tiến thẳng trong thời gian ngắn để tìm ô quét mới."""
        logger.info("Entering state: MoveOnly")
        self.context.start_move_only_timer()
        if not self.context.command_move_forward():
            logger.warning("MoveOnly: failed to command forward motion.")

    def on_exit_move_only(self) -> None:
        """Dừng đếm thời gian khi kết thúc pha di chuyển đơn thuần."""
        self.context.cancel_move_only_timer()

    def on_enter_turn_second(self) -> None:
        """Thực hiện cú quay thứ hai để hoàn tất thao tác tránh vật cản."""
        logger.info("Entering state: TurnSecond")
        if not self.context.command_turn():
            logger.error("Failed to send second turn command; resuming patrol.")
            self.second_turn_complete()

    # Event handling --------------------------------------------------------

    def handle_detection(self, event: DetectionEvent) -> None:
        """Xử lý luồng phát hiện hình ảnh để quyết định chuyển sang nhặt trứng."""
        self.context.update_detections(event.detections, event.frame)

        if self.is_pickup_active:
            if not event.detections and not self.context.is_waiting_for_arm():
                logger.info("Detections cleared while picking; completing cycle.")
                self.finish_picking()
            else:
                self.context.refresh_pick_queue()
            return

        if not self.context.has_pick_candidates():
            return

        if not self.context.ensure_actor_stopped():
            logger.warning("Unable to stop actor for pick transition.")
            return

        self.commence_pick()

    def handle_actor_status(self, event: ActorStatusEvent) -> None:
        """Cập nhật trạng thái xe và điều phối các pha quay hoặc tuần tra."""
        self.context.update_actor_status(event.status)

        if self.is_turn_first and not event.status.is_moving:
            self.first_turn_complete()
            return

        if self.is_turn_second and not event.status.is_moving:
            self.second_turn_complete()
            return

        if self.is_scan_and_move and self.context.should_rotate_due_to_obstacle():
            if not self.context.ensure_actor_stopped():
                logger.warning("Failed to stop actor before initiating turn.")
                return
            self.start_first_turn()

    def handle_arm_status(self, event: ArmStatusEvent) -> None:
        """Theo dõi tiến độ của cánh tay để tiếp tục hoặc kết thúc chu kỳ nhặt."""
        waiting_before = self.context.is_waiting_for_arm()
        self.context.update_arm_status(event.status)

        if not self.is_pickup_active:
            return

        if event.status.is_busy:
            return

        if waiting_before:
            self.context.complete_current_pick()

        if self.context.command_next_pick():
            return

        if self.context.current_pick_queue_empty() and not self.context.is_waiting_for_arm():
            self.finish_picking()

    def handle_timer(self, event: TimerEvent) -> None:
        """Phản ứng với các bộ hẹn giờ nội bộ phục vụ tuần tra và nhặt."""
        if event.timer_id == TimerId.SCAN_ONLY_TIMEOUT and self.is_scan_only:
            self.scan_timeout()
            return

        if event.timer_id == TimerId.MOVE_ONLY_COUNTDOWN and self.is_move_only:
            if not self.context.ensure_actor_stopped():
                logger.warning("MoveOnly countdown: failed to stop before turning.")
            self.move_timer_elapsed()

    # Convenience predicates ------------------------------------------------

    @property
    def is_pickup_active(self) -> bool:
        """Cho biết máy trạng thái hiện ở trong chu trình nhặt trứng hay không."""
        return self.current_state == self.pick_up_egg


class ControlEngine:
    """Điều phối vòng lặp sự kiện, bộ lập lịch và máy trạng thái điều khiển."""

    def __init__(self, context: ControlContext, bus: EventBus, state_machine: Optional[ControlStateMachine] = None):
        """Khởi tạo engine với ngữ cảnh, bus sự kiện và máy trạng thái cần điều khiển."""
        self.context = context
        self.bus = bus
        self.state_machine = state_machine or ControlStateMachine(context)
        self._loop_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        """Bật toàn bộ phần cứng và khởi chạy vòng lặp xử lý sự kiện."""
        self.context.actor.start()
        self.context.arm.start()
        scheduler_cfg = self.context.config.scheduler
        self.context.scheduler.start_interval(TimerId.ACTOR_STATUS, scheduler_cfg.actor_status_interval_ms / 1000.0)
        self.context.scheduler.start_interval(TimerId.ARM_STATUS, scheduler_cfg.arm_status_interval_ms / 1000.0)
        self.state_machine.start_patrol()
        logger.info("Control engine initial state: %s", self._state_name())
        self._loop_thread = threading.Thread(target=self._event_loop, name="ControlEventLoop", daemon=True)
        self._loop_thread.start()
        logger.info("Control engine started.")

    def stop(self) -> None:
        """Tắt engine, hủy thread sự kiện và thu hồi tài nguyên thiết bị."""
        self._stop_event.set()
        self.bus.stop("engine shutdown")
        if self._loop_thread:
            self._loop_thread.join(timeout=2.0)
        self.context.scheduler.shutdown()
        self.context.actor.shutdown()
        self.context.arm.shutdown()
        logger.info("Control engine stopped.")

    def _event_loop(self) -> None:
        """Luồng nền lấy sự kiện từ bus và chuyển tiếp cho máy trạng thái."""
        while not self._stop_event.is_set():
            try:
                event = self.bus.get(timeout=0.5)
            except Exception:
                continue

            if isinstance(event, StopEvent):
                logger.info("Control engine received stop event: %s", event.reason)
                break

            self._dispatch_event(event)

    def _dispatch_event(self, event: object) -> None:
        """Phân loại và chuyển sự kiện tới handler tương ứng."""
        state_name = self._state_name()
        event_name = type(event).__name__
        if isinstance(event, TimerEvent):
            logger.debug("Dispatching %s while in state %s", event_name, state_name)
        else:
            logger.info("Dispatching %s while in state %s", event_name, state_name)
        try:
            if isinstance(event, DetectionEvent):
                self.state_machine.handle_detection(event)
            elif isinstance(event, TimerEvent):
                self._handle_timer_event(event)
            elif isinstance(event, ActorStatusEvent):
                self.state_machine.handle_actor_status(event)
            elif isinstance(event, ArmStatusEvent):
                self.state_machine.handle_arm_status(event)
            elif isinstance(event, CommandResultEvent):
                logger.info("Command result: %s success=%s details=%s", event.command, event.success, event.details)
            else:
                logger.debug("Unhandled event type: %s", type(event).__name__)
        except Exception:
            logger.exception("Error while dispatching event: %s", event)

    def _handle_timer_event(self, event: TimerEvent) -> None:
        """Xử lý riêng các bộ hẹn giờ định kỳ và theo chu kỳ."""
        if event.timer_id == TimerId.ACTOR_STATUS:
            try:
                status = self.context.actor.read_status()
            except Exception:
                logger.exception("Actor status poll failed.")
                return
            if status:
                self.bus.publish(ActorStatusEvent(status=status))
            return

        if event.timer_id == TimerId.ARM_STATUS:
            try:
                status = self.context.arm.read_status()
            except Exception:
                logger.exception("Arm status poll failed.")
                return
            if status:
                self.bus.publish(ArmStatusEvent(status=status))
            return

        self.state_machine.handle_timer(event)

    def _state_name(self) -> str:
        """Trả về tên trạng thái hiện tại phục vụ debug và giao diện."""
        state = self.state_machine.current_state
        return getattr(state, "id", str(state))
