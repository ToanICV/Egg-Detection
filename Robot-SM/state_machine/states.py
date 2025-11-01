"""
Bộ lớp Trạng thái (State) triển khai máy trạng thái điều khiển theo sự kiện
cho robot nhặt trứng.

Chức năng:
- Cung cấp các lớp trạng thái cụ thể (Idle, ScanAndMove, PickUpEgg, TurnFirst, ScanOnly, MoveOnly, TurnSecond)
  với các hook enter(ctx), handle(ctx, event), exit(ctx) để điều phối hành vi robot.
- Hỗ trợ mô hình xử lý theo sự kiện: mỗi state nhận event và có thể yêu cầu chuyển
  state bằng cách trả về instance state mới từ handle(); trả về None để giữ nguyên state.
- Phối hợp cùng Context (gói các dịch vụ như SerialComm, Vision, Scheduler) để gửi lệnh,
  bật/tắt polling, đặt/hủy timer theo đúng quy trình trong docs/workflows.md.

Ngữ cảnh sử dụng:
- Được dùng bởi Controller của máy trạng thái: Controller giữ current_state, gọi
  current_state.enter() khi kích hoạt, chuyển tiếp event vào current_state.handle(),
  và khi handle() trả về state mới thì gọi exit() của state cũ và enter() của state mới.
- Tầng Context cần hiện thực các API tối thiểu (gửi lệnh, polling, timer, logger) để các state sử dụng.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Protocol


class Event(Protocol):
    """Giao diện sự kiện tối thiểu.

    Chức năng:
    - Chuẩn hóa một event có 'type' (tên loại sự kiện) và 'payload' (dữ liệu đi kèm).

    Ngữ cảnh sử dụng:
    - Được các state sử dụng trong handle(ctx, event) để quyết định hành động/chuyển trạng thái.
    - Controller và các nguồn (Vision/Sensor/Serial/Timer) tạo và gửi Event này vào FSM.
    """

    type: str
    payload: Any


class Context(Protocol):
    """Giao diện Context mong đợi (tham chiếu đến context.py).

    Chức năng:
    - Cung cấp các API mà state cần để gửi lệnh, bật/tắt polling, đặt/hủy timer, và logging.

    Ngữ cảnh sử dụng:
    - Được Controller truyền vào các state trong enter/handle/exit.
    - Cụ thể hóa bằng implementation thực tế (bọc SerialComm, Vision, Scheduler...).
    """

    # Logging
    @property
    def logger(self): ...

    # Serial commands (wrap your SerialComm or Actor facade)
    def cmd_base_forward(self) -> bool: ...
    def cmd_base_stop(self) -> bool: ...
    def cmd_base_turn90(self) -> bool: ...
    def cmd_base_read_state(self) -> bool: ...
    def cmd_arm_pick(self, x_mm: int, y_mm: int) -> bool: ...
    def cmd_arm_read_state(self) -> bool: ...

    # Vision and sensors data storage
    last_detections: list
    obstacle_cm: Optional[float]

    # Timers/scheduler
    def start_timer(self, name: str, seconds: float) -> None: ...
    def cancel_timer(self, name: str) -> None: ...

    # Utility
    def set_polling(self, topic: str, enable: bool, interval_s: float = 1.0) -> None: ...


class BaseState:
    """Lớp cơ sở cho mọi trạng thái.

    Chức năng:
    - Định nghĩa khung enter/handle/exit và logging mặc định.

    Ngữ cảnh sử dụng:
    - Các state cụ thể kế thừa để cài đặt logic riêng.
    - Controller gọi enter/handle/exit tương ứng.
    """
    id: str = "base"

    def enter(self, ctx: Context) -> None:
        """Hook khi vào trạng thái.

        Chức năng: Khởi tạo tài nguyên cho state (ví dụ: bật polling/timer, gửi lệnh ban đầu).
        Ngữ cảnh: Được Controller gọi ngay sau khi state trở thành current_state.
        """
        ctx.logger.debug("Enter: %s", self.id)

    def handle(self, ctx: Context, event: Event) -> Optional[BaseState]:
        """Xử lý một sự kiện.

        Chức năng: Quyết định giữ nguyên hay chuyển sang state khác bằng cách trả về instance state mới.
        Ngữ cảnh: Được Controller gọi cho mọi event; trả về None để ở lại state hiện tại.
        """
        ctx.logger.debug("Unhandled event in %s: %s", self.id, getattr(event, "type", event))
        return None

    def exit(self, ctx: Context) -> None:
        """Hook khi rời trạng thái.

        Chức năng: Dọn tài nguyên do state thiết lập (tắt polling, hủy timer...).
        Ngữ cảnh: Được Controller gọi trước khi chuyển sang state mới.
        """
        ctx.logger.debug("Exit: %s", self.id)


class IdleState(BaseState):
    """Trạng thái chờ (Idle).

    Chức năng: Đứng yên, chờ tín hiệu khởi động hệ thống.
    Ngữ cảnh: State khởi đầu khi hệ thống bật hoặc sau lỗi cần dừng an toàn.
    """
    id = "Idle"

    def enter(self, ctx: Context) -> None:
        """Không thực hiện hành động; chờ sự kiện 'start'."""
        super().enter(ctx)

    def handle(self, ctx: Context, event: Event) -> Optional[BaseState]:
        """Chuyển sang ScanAndMove khi nhận event 'start'."""
        if event.type == "start":
            return ScanAndMoveState()
        return super().handle(ctx, event)


class ScanAndMoveState(BaseState):
    """Trạng thái quét và di chuyển.

    Chức năng: Cho base tiến về trước, quét bằng camera, chờ tiêu chí phát hiện trứng
    hoặc chướng ngại gần để quyết định dừng/nhặt/đổi hướng.
    Ngữ cảnh: Sau khi start hoặc sau một vòng quay/dò.
    """
    id = "ScanAndMove"

    def enter(self, ctx: Context) -> None:
        """Gửi lệnh tiến, bật polling trạng thái base mỗi 1s."""
        super().enter(ctx)
        ctx.cmd_base_forward()
        ctx.set_polling("base_state", True, interval_s=1.0)

    def handle(self, ctx: Context, event: Event) -> Optional[BaseState]:
        """Khi phát hiện trứng ở vùng giữa → dừng và sang PickUpEgg.
        Khi chướng ngại gần → dừng, quay 90° và sang TurnFirst.
        """
        if event.type == "eggs_detected":
            eggs = event.payload or []
            ctx.last_detections = eggs
            # Điều kiện chọn ứng viên theo ngưỡng cấu hình từ context
            th = getattr(ctx, "pick_thresholds", {}) or {}
            y_min = float(th.get("y_min_norm", 0.25))
            x_min = float(th.get("x_min_norm", 0.05))
            x_max = float(th.get("x_max_norm", 0.95))
            candidates = [
                e for e in eggs
                if (e.get("y_norm", 0.0) > y_min) and (x_min < e.get("x_norm", 0.0) < x_max)
            ]
            print(f"candidates: {candidates}")
            if candidates:
                ctx.cmd_base_stop()
                return PickUpEggState(target=candidates[0])
            
        if event.type == "obstacle_dist" and ctx.last_detections == []:
            # ctx.cmd_base_stop() # nếu gặp vật cản thì base đã dừng sẵn rồi
            ctx.cmd_base_turn90()
            return TurnFirstState()
        return super().handle(ctx, event)

    def exit(self, ctx: Context) -> None:
        """Tắt polling trạng thái base."""
        ctx.set_polling("base_state", False)
        super().exit(ctx)


@dataclass
class PickUpEggState(BaseState):
    """Trạng thái nhặt trứng.

    Chức năng: Điều khiển tay máy nhặt quả trứng mục tiêu và theo dõi tiến trình.
    Ngữ cảnh: Được kích hoạt khi phát hiện trứng ở vùng phù hợp và base đã dừng.
    """
    id: str = "PickUpEgg"
    target: Optional[dict] = None  # expects keys like x_mm, y_mm or convert from pixels

    def enter(self, ctx: Context) -> None:
        """Gửi lệnh nhặt tại (x_mm, y_mm) và bật polling trạng thái arm."""
        super().enter(ctx)

        scara = getattr(ctx, "scara", {}) or {}
        height_px = float(scara.get("height_px", 480))
        width_px = float(scara.get("width_px", 640))
        height_mm = float(scara.get("height_mm", 240))
        width_mm = float(scara.get("width_mm", 320))
        dx = float(scara.get("dx", 100))
        dy = float(scara.get("width_mm", 50))

        x_px = int(self.target.get("x_px", 0) if self.target else 0)
        y_px = int(self.target.get("y_px", 0) if self.target else 0)

        x_mm = int((width_mm / width_px) * x_px + dx)
        y_mm = int((height_mm / height_px) * y_px + dy)

        ctx.cmd_arm_pick(x_mm, y_mm)
        ctx.set_polling("arm_state", True, interval_s=1.0)

    def handle(self, ctx: Context, event: Event) -> Optional[BaseState]:
        """Khi arm báo 'done' → quay lại ScanAndMove; nếu 'busy' → tiếp tục chờ."""
        if event.type == "arm_state":
            state = event.payload
            if state == "done":
                return ScanAndMoveState()
        return super().handle(ctx, event)

    def exit(self, ctx: Context) -> None:
        """Tắt polling trạng thái arm."""
        ctx.set_polling("arm_state", False)
        super().exit(ctx)


class TurnFirstState(BaseState):
    """Trạng thái quay lần 1 (sau ScanAndMove gặp chướng ngại/không thấy trứng)."""
    id = "TurnFirst"

    def enter(self, ctx: Context) -> None:
        """Bật polling base_state và đặt timer timeout 10s cho thao tác quay."""
        super().enter(ctx)
        ctx.set_polling("base_state", True, interval_s=1.0)
        ctx.start_timer("turn1_timeout", 10.0)  # Dùng để giả lập tự động

    def handle(self, ctx: Context, event: Event) -> Optional[BaseState]:
        """Khi base dừng → sang ScanOnly; quá thời gian → cũng sang ScanOnly."""
        if event.type == "base_state":
            state = event.payload
            if state == "stopped":
                print("Chuyển sang ScanOnly do Base đã dừng")
                return ScanOnlyState()
        if event.type == "timer" and event.payload == "turn1_timeout":
            print("Chuyển sang ScanOnly do timeout của TurnFirstState")
            return ScanOnlyState()
        return super().handle(ctx, event)

    def exit(self, ctx: Context) -> None:
        """Hủy timer và tắt polling base_state."""
        ctx.cancel_timer("turn1_timeout")
        ctx.set_polling("base_state", False)
        super().exit(ctx)


class ScanOnlyState(BaseState):
    """Trạng thái chỉ quét (không di chuyển)."""
    id = "ScanOnly"

    def enter(self, ctx: Context) -> None:
        """Đặt timer 5s: nếu không thấy trứng → chuyển MoveOnly."""
        super().enter(ctx)
        ctx.start_timer("no_egg_timeout", 5.0)

    def handle(self, ctx: Context, event: Event) -> Optional[BaseState]:
        """Có trứng → sang PickUpEgg; hết 5s không thấy → sang MoveOnly."""
        if event.type == "eggs_detected":
            eggs = event.payload or []
            if eggs:
                return PickUpEggState(target=eggs[0])
        if event.type == "timer" and event.payload == "no_egg_timeout":
            return MoveOnlyState()
        return super().handle(ctx, event)

    def exit(self, ctx: Context) -> None:
        """Hủy timer no_egg_timeout."""
        ctx.cancel_timer("no_egg_timeout")
        super().exit(ctx)


class MoveOnlyState(BaseState):
    """Trạng thái chỉ di chuyển (không quét)."""
    id = "MoveOnly"

    def enter(self, ctx: Context) -> None:
        """Gửi lệnh tiến và đặt timer 5s; hết thời gian → dừng và quay 90°."""
        super().enter(ctx)
        ctx.cmd_base_forward()
        ctx.start_timer("move_duration", 5.0)

    def handle(self, ctx: Context, event: Event) -> Optional[BaseState]:
        """Hết 5s → dừng + quay 90° và sang TurnSecond."""
        if event.type == "timer" and event.payload == "move_duration":
            # ctx.cmd_base_stop() # khi gửi lệnh turn90 thì base thay vì tịnh tiến sẽ xoay luôn, không dừng
            ctx.cmd_base_turn90()
            return TurnSecondState()
        return super().handle(ctx, event)

    def exit(self, ctx: Context) -> None:
        """Hủy timer move_duration."""
        ctx.cancel_timer("move_duration")
        super().exit(ctx)


class TurnSecondState(BaseState):
    """Trạng thái quay lần 2 (sau MoveOnly)."""
    id = "TurnSecond"

    def enter(self, ctx: Context) -> None:
        """Bật polling base_state và đặt timer 10s cho thao tác quay."""
        super().enter(ctx)
        ctx.set_polling("base_state", True, interval_s=1.0)
        ctx.start_timer("turn2_timeout", 10.0)  # Dùng để giả lập tự động

    def handle(self, ctx: Context, event: Event) -> Optional[BaseState]:
        """Base dừng hoặc quá thời gian → quay lại ScanAndMove."""
        if event.type == "base_state":
            state = event.payload
            if state == "stopped":
                print("Chuyển sang ScanAndMove do Base đã dừng")
                return ScanAndMoveState()
        if event.type == "timer" and event.payload == "turn2_timeout":
            print("Chuyển sang ScanAndMove do timeout của TurnSecondState")
            return ScanAndMoveState()
        return super().handle(ctx, event)

    def exit(self, ctx: Context) -> None:
        """Hủy timer và tắt polling base_state."""
        ctx.cancel_timer("turn2_timeout")
        ctx.set_polling("base_state", False)
        super().exit(ctx)
