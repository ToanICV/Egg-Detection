"""Serial link wrapper for the mobile actor platform."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from config.models import SerialLinkConfig

from .bus import SharedSerialBus
from .codec import DecodedFrame
from .protocol import (
    ACTOR_GROUP_COMMAND,
    ACTOR_GROUP_STATUS,
    ActorCommand,
    ActorStatus,
    build_actor_command,
    build_actor_status_request,
    parse_actor_status,
)

logger = logging.getLogger("serial.actor")


class ActorLink:
    """High-level controller for Actor serial commands."""

    def __init__(
        self,
        bus: SharedSerialBus,
        config: SerialLinkConfig,
        on_status: Optional[Callable[[ActorStatus], None]] = None,
    ) -> None:
        self._bus = bus
        self.config = config
        self._status_callback = on_status
        self._last_status: ActorStatus | None = None
        self._listener_id = self._bus.register_listener(self._handle_frame)

    def start(self) -> None:
        self._bus.start()

    def shutdown(self) -> None:
        self._bus.stop()

    def move_forward(self) -> bool:
        return self._send_command(ActorCommand.MOVE_FORWARD)

    def move_backward(self) -> bool:
        return self._send_command(ActorCommand.MOVE_BACKWARD)

    def stop_motion(self) -> bool:
        return self._send_command(ActorCommand.STOP)
    halt = stop_motion

    def turn_90(self) -> bool:
        return self._send_command(ActorCommand.TURN_90)

    def read_status(self, timeout_s: Optional[float] = None) -> Optional[ActorStatus]:
        frame = build_actor_status_request()
        timeout = timeout_s if timeout_s is not None else self.config.response_timeout_ms / 1000.0
        logger.debug("📤 ACTOR STATUS: requesting → COM%s", self.config.port)
        response = self._bus.request(
            frame,
            predicate=lambda f: f.group == ACTOR_GROUP_STATUS,
            timeout_s=timeout,
        )
        if response is None:
            logger.warning("❌ ACTOR STATUS: timeout (%.1fs)", timeout)
            return None
        if not response.crc_ok:
            logger.warning("❌ ACTOR STATUS: invalid CRC")
            return None
        status = parse_actor_status(response)
        logger.debug("📥 ACTOR STATUS: moving=%s, distance=%s", status.is_moving, status.distance_cm)
        self._update_status(status)
        return status

    def last_status(self) -> Optional[ActorStatus]:
        return self._last_status

    def _send_command(self, command: ActorCommand) -> bool:
        frame = build_actor_command(command)
        timeout = self.config.ack_timeout_ms / 1000.0
        frame_hex = frame.hex().upper()
        logger.info("📤 ACTOR CMD: %s → COM%s [%s]", command.name, self.config.port, frame_hex)
        ack = self._bus.request(
            frame,
            predicate=lambda f: f.group == ACTOR_GROUP_COMMAND and f.payload_as_ints()[:1] == (ActorCommand.ACK,),
            timeout_s=timeout,
        )
        if ack is None:
            logger.warning("❌ ACTOR CMD: %s timeout (no ACK after %.1fs)", command.name, timeout)
            return False
        if not ack.crc_ok:
            logger.warning("❌ ACTOR CMD: %s ACK failed CRC validation", command.name)
            return False
        logger.info("✅ ACTOR CMD: %s acknowledged", command.name)
        return True

    def _handle_frame(self, frame: DecodedFrame) -> None:
        if frame.group != ACTOR_GROUP_STATUS:
            return
        if not frame.crc_ok:
            logger.debug("ActorLink: ignoring status frame with invalid CRC.")
            return
        try:
            status = parse_actor_status(frame)
        except Exception:  # pragma: no cover - defensive parsing
            logger.exception("ActorLink: failed to parse status frame.")
            return
        self._update_status(status)

    def _update_status(self, status: ActorStatus) -> None:
        self._last_status = status
        if self._status_callback:
            try:
                self._status_callback(status)
            except Exception:
                logger.exception("ActorLink: status callback failed.")
