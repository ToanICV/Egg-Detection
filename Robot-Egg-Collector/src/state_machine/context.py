"""Runtime context and helper utilities for the control state machine."""

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
    STOPPED = "stopped"
    FORWARD = "forward"
    TURNING = "turning"


@dataclass
class ControlContext:
    """Holds shared state and provides command helpers for the control FSM."""

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
        self.latest_arm_status = status
        if not status.is_busy and self._waiting_for_arm:
            # Arm finished current operation.
            self._waiting_for_arm = False

    def has_pick_candidates(self) -> bool:
        return bool(self._filter_candidates())

    def prepare_pick_queue(self) -> bool:
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
        if not self._pick_queue:
            self.prepare_pick_queue()

    def command_next_pick(self) -> bool:
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
        if self._current_target:
            self.logger.info("Target %s picked successfully.", self._current_target.id)
        self._current_target = None
        self._waiting_for_arm = False

    def clear_pick_cycle(self) -> None:
        self._pick_queue.clear()
        self._current_target = None
        self._waiting_for_arm = False

    def should_rotate_due_to_obstacle(self) -> bool:
        status = self.latest_actor_status
        if status is None or status.distance_cm is None:
            return False
        if self._actor_motion == ActorMotion.TURNING:
            return False
        return status.distance_cm <= self.config.behaviour.distance_stop_threshold_cm

    def ensure_actor_stopped(self) -> bool:
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
        self.logger.info("🔄 MOTION: commanding turn 90°")
        success = self.actor.turn_90()
        if success:
            self._actor_motion = ActorMotion.TURNING
            self.logger.info("✅ MOTION: turn 90° command sent")
        else:
            self.logger.error("❌ MOTION: turn 90° command failed")
        return success

    def is_waiting_for_arm(self) -> bool:
        return self._waiting_for_arm

    def current_pick_queue_empty(self) -> bool:
        return not self._pick_queue

    def start_scan_only_timer(self) -> None:
        self.scheduler.schedule_once(
            TimerId.SCAN_ONLY_TIMEOUT,
            self.config.scheduler.scan_only_timeout_ms / 1000.0,
        )

    def cancel_scan_only_timer(self) -> None:
        self.scheduler.cancel(TimerId.SCAN_ONLY_TIMEOUT)

    def start_move_only_timer(self) -> None:
        self.scheduler.schedule_once(
            TimerId.MOVE_ONLY_COUNTDOWN,
            self.config.scheduler.move_only_duration_ms / 1000.0,
        )

    def cancel_move_only_timer(self) -> None:
        self.scheduler.cancel(TimerId.MOVE_ONLY_COUNTDOWN)

    def _filter_candidates(self) -> list[Detection]:
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
        """Placeholder mapping: use pixel coordinates until calibration is provided."""
        if not self.current_frame:
            return 0, 0
        cx, cy = detection.center()
        return int(round(cx)), int(round(cy))
