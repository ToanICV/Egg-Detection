"""Ngữ cảnh thời gian chạy và các tiện ích hỗ trợ máy trạng thái điều khiển."""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, Iterable, Optional

import numpy as np

from config.models import BehaviourConfig, ControlConfig, SchedulerConfig
from core.entities import Detection, FrameData
from serial_io import ActorLink, ArmLink, ActorStatus, ArmStatus
from services import CommandScheduler, EventBus, TimerId


class ActorMotion(Enum):
    """Liệt kê các trạng thái chuyển động cơ bản của khung gầm."""

    STOPPED = "stopped"
    FORWARD = "forward"
    TURNING = "turning"


@dataclass
class ControlContext:
    """Tập hợp trạng thái thời gian thực và các tiện ích điều khiển cho FSM.

    ControlStateMachine sử dụng đối tượng này để đọc dữ liệu cảm biến, lưu
    kết quả xử lý và phát lệnh tới xe tự hành cũng như cánh tay nhặt trứng.
    Các bộ đếm thời gian và hàng đợi nhặt đều được quản lý tập trung tại đây.
    """

    actor: ActorLink
    arm: ArmLink
    scheduler: CommandScheduler
    bus: EventBus
    config: ControlConfig
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("control.context"))

    current_frame: Optional[FrameData] = None
    current_detections: list[Detection] = field(default_factory=list)
    latest_actor_status: Optional[ActorStatus] = None
    latest_arm_status: Optional[ArmStatus] = None

    _pick_queue: Deque[Detection] = field(default_factory=deque)
    _pick_attempts: Dict[int, int] = field(default_factory=dict)
    _current_target: Optional[Detection] = None
    _waiting_for_arm: bool = False
    _actor_motion: ActorMotion = ActorMotion.STOPPED

    def update_detections(self, detections: Iterable[Detection], frame: FrameData) -> None:
        """Lưu kết quả nhận diện mới nhất để chuẩn bị cho bước lập kế hoạch nhặt.

        Hàm được gọi mỗi khi DetectionEvent xuất hiện, giúp máy trạng thái quyết
        định có chuyển sang chu trình nhặt trứng hay không.
        """
        self.current_detections = list(detections)
        self.current_frame = frame
        detection_count = len(self.current_detections)
        if detection_count > 0:
            self.logger.info("🎯 DETECTIONS: %d eggs found (frame %s)", detection_count, frame.frame_id)
            for i, det in enumerate(self.current_detections):
                cx, cy = det.center()
                self.logger.debug("  📍 Egg %d: center=(%.1f, %.1f), conf=%.2f", i+1, cx, cy, det.confidence)
        else:
            self.logger.debug("🔍 DETECTIONS: no eggs found (frame %s)", frame.frame_id)

    def update_actor_status(self, status: ActorStatus) -> None:
        """Ghi nhận phản hồi từ bộ điều khiển xe và suy ra trạng thái chuyển động.

        Được máy trạng thái gọi khi có bản tin trạng thái mới để phát hiện đã
        hoàn thành việc quay đầu, có vật cản ở phía trước hay xe hoạt động bất
        thường.
        """
        self.latest_actor_status = status
        if status.is_moving:
            if self._actor_motion == ActorMotion.STOPPED:
                # MCU started moving although we thought it was stopped -> assume forward motion.
                self._actor_motion = ActorMotion.FORWARD
        else:
            if self._actor_motion == ActorMotion.TURNING:
                self.logger.debug("Actor reported stationary after turn.")
            self._actor_motion = ActorMotion.STOPPED

    def update_arm_status(self, status: ArmStatus) -> None:
        """Theo dõi tiến trình của cánh tay và hủy trạng thái chờ khi hoàn tất.

        Chạy khi nhận ArmStatusEvent để vòng lặp nhặt tiếp tục hoặc kết thúc khi
        cơ cấu gắp không còn bận.
        """
        self.latest_arm_status = status
        if not status.is_busy and self._waiting_for_arm:
            # Arm finished current operation.
            self._waiting_for_arm = False

    def has_pick_candidates(self) -> bool:
        """Xác định các phát hiện hiện tại có mục tiêu hợp lệ để nhặt hay không.

        Được gọi trong các trạng thái quét nhằm quyết định có chuyển sang chu
        kỳ nhặt hay tiếp tục tuần tra.
        """
        return bool(self._filter_candidates())

    def prepare_pick_queue(self) -> bool:
        """Tạo hàng đợi mục tiêu phục vụ chu kỳ nhặt tiếp theo.

        Được kích hoạt khi máy trạng thái vào `pick_up_egg` để cánh tay thao
        tác theo trật tự ưu tiên (gần tâm ảnh trước). Trả về True nếu có ít nhất
        một mục tiêu sẵn sàng.
        """
        candidates = self._filter_candidates()
        if not candidates:
            self._pick_queue.clear()
            return False
        if not self.current_frame:
            self.logger.debug("No frame available for pick planning.")
            return False

        frame = self.current_frame.image
        height, width = frame.shape[:2]
        center_x = width / 2.0
        # Sort by proximity to frame centre.
        candidates.sort(key=lambda det: abs(det.center()[0] - center_x), reverse=False)
        self._pick_queue = deque(candidates)
        self.logger.info("Prepared pick queue with %d targets.", len(self._pick_queue))
        return True

    def refresh_pick_queue(self) -> None:
        """Cập nhật lại hàng đợi khi giữa chu kỳ nhặt xuất hiện phát hiện mới.

        Hàm được handler phát hiện gọi để đảm bảo cánh tay luôn có mục tiêu.
        """
        if not self._pick_queue:
            self.prepare_pick_queue()

    def command_next_pick(self) -> bool:
        """Gửi lệnh nhặt tiếp theo và quản lý số lần thử cho từng mục tiêu.

        Được gọi khi cánh tay rảnh trong trạng thái `pick_up_egg`. Trả về True
        nếu đã phát lệnh thành công xuống bộ điều khiển cánh tay.
        """
        if not self._pick_queue:
            self.logger.debug("🤖 PICK: no targets in queue")
            return False

        while self._pick_queue:
            target = self._pick_queue.popleft()
            attempts = self._pick_attempts.get(target.id, 0)
            if attempts >= self.config.behaviour.max_arm_pick_attempts:
                self.logger.warning("🤖 PICK: target %s skipped after %d failed attempts", target.id, attempts)
                continue

            coords = self._map_detection_to_mm(target)
            cx, cy = target.center()
            self.logger.info("🤖 PICK: targeting egg %s at pixel(%.1f,%.1f) → mm(%d,%d)", 
                           target.id, cx, cy, coords[0], coords[1])
            success = self.arm.pick(*coords)
            self._pick_attempts[target.id] = attempts + 1
            if success:
                self._current_target = target
                self._waiting_for_arm = True
                self.logger.info("✅ PICK: arm command sent, waiting for completion")
                return True
            self.logger.warning("❌ PICK: arm command failed for target %s (attempt %d/%d)", 
                              target.id, attempts + 1, self.config.behaviour.max_arm_pick_attempts)
        
        self.logger.info("🤖 PICK: no more valid targets")
        self._current_target = None
        return False

    def complete_current_pick(self) -> None:
        """Xóa thông tin mục tiêu hiện tại sau khi cánh tay báo hoàn tất.

        Thường được gọi sau khi update_arm_status phát hiện cơ cấu gắp đã rảnh.
        """
        if self._current_target:
            self.logger.info("Target %s picked successfully.", self._current_target.id)
        self._current_target = None
        self._waiting_for_arm = False

    def clear_pick_cycle(self) -> None:
        """Đặt lại toàn bộ trạng thái liên quan đến chu kỳ nhặt trước khi thoát."""
        self._pick_queue.clear()
        self._current_target = None
        self._waiting_for_arm = False

    def should_rotate_due_to_obstacle(self) -> bool:
        """Quyết định có cần dừng tiến và xoay tránh vật cản hay không."""
        status = self.latest_actor_status
        if status is None or status.distance_cm is None:
            return False
        if self._actor_motion == ActorMotion.TURNING:
            return False
        return status.distance_cm <= self.config.behaviour.distance_stop_threshold_cm

    def ensure_actor_stopped(self) -> bool:
        """Đảm bảo xe đã dừng hẳn trước khi gửi lệnh tiếp theo."""
        if self._actor_motion == ActorMotion.STOPPED:
            self.logger.debug("🛑 MOTION: already stopped")
            return True
        self.logger.info("🛑 MOTION: commanding stop")
        success = self.actor.stop_motion()
        if success:
            self._actor_motion = ActorMotion.STOPPED
            self.logger.info("✅ MOTION: stop command sent")
        else:
            self.logger.error("❌ MOTION: stop command failed")
        return success

    def command_move_forward(self) -> bool:
        """Ra lệnh tiến thẳng và cập nhật trạng thái chuyển động suy luận."""
        if self._actor_motion == ActorMotion.FORWARD:
            self.logger.debug("🚗 MOTION: already moving forward")
            return True
        self.logger.info("🚗 MOTION: commanding move forward")
        success = self.actor.move_forward()
        if success:
            self._actor_motion = ActorMotion.FORWARD
            self.logger.info("✅ MOTION: move forward command sent")
        else:
            self.logger.error("❌ MOTION: move forward command failed")
        return success

    def command_turn(self) -> bool:
        """Yêu cầu xe quay 90 độ để thực hiện bước tránh vật cản."""
        self.logger.info("🔄 MOTION: commanding turn 90°")
        success = self.actor.turn_90()
        if success:
            self._actor_motion = ActorMotion.TURNING
            self.logger.info("✅ MOTION: turn 90° command sent")
        else:
            self.logger.error("❌ MOTION: turn 90° command failed")
        return success

    def is_waiting_for_arm(self) -> bool:
        """Cho biết hệ thống còn đang chờ cánh tay hoàn thành lệnh nhặt hay không."""
        return self._waiting_for_arm

    def current_pick_queue_empty(self) -> bool:
        """Trả về True nếu hàng đợi nhặt không còn mục tiêu nào."""
        return not self._pick_queue

    def start_scan_only_timer(self) -> None:
        """Khởi tạo bộ hẹn giờ giới hạn thời gian ở trạng thái chỉ quét."""
        self.scheduler.schedule_once(
            TimerId.SCAN_ONLY_TIMEOUT,
            self.config.scheduler.scan_only_timeout_ms / 1000.0,
        )

    def cancel_scan_only_timer(self) -> None:
        """Hủy hẹn giờ quét khi máy trạng thái rời khỏi chế độ này sớm."""
        self.scheduler.cancel(TimerId.SCAN_ONLY_TIMEOUT)

    def start_move_only_timer(self) -> None:
        """Bắt đầu đếm ngược cho giai đoạn chỉ di chuyển về phía trước."""
        self.scheduler.schedule_once(
            TimerId.MOVE_ONLY_COUNTDOWN,
            self.config.scheduler.move_only_duration_ms / 1000.0,
        )

    def cancel_move_only_timer(self) -> None:
        """Hủy đếm ngược khi vòng tuần tra chuyển về chế độ quét."""
        self.scheduler.cancel(TimerId.MOVE_ONLY_COUNTDOWN)

    def _filter_candidates(self) -> list[Detection]:
        """Lọc các phát hiện đạt ngưỡng độ tin cậy và nằm trong vùng cho phép.

        Hàm hỗ trợ has_pick_candidates và prepare_pick_queue trong việc tạo danh
        sách mục tiêu khả thi.
        """
        if not self.current_frame:
            return []
        behaviour: BehaviourConfig = self.config.behaviour
        frame = self.current_frame.image
        if frame is None:
            return []
        height, width = frame.shape[:2]
        center_x = width / 2.0
        tolerance_px = width * behaviour.detection_center_tolerance

        candidates: list[Detection] = []
        for det in self.current_detections:
            if det.confidence < behaviour.detection_min_confidence:
                continue
            cx, cy = det.center()
            if abs(cx - center_x) <= tolerance_px:
                candidates.append(det)
        return candidates

    def _map_detection_to_mm(self, detection: Detection) -> tuple[int, int]:
        """Chuyển tọa độ phát hiện sang đơn vị milimet để gửi cho cánh tay.

        Đây là phép nội suy tạm thời trước khi có bản hiệu chỉnh camera chính
        xác, giúp quy trình nhặt vẫn tương thích với API của cánh tay.
        """
        if not self.current_frame:
            return 0, 0
        cx, cy = detection.center()
        return int(round(cx)), int(round(cy))
