"""Tiện ích mã hóa/giải mã khung dữ liệu nối tiếp từ MCU."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Sequence

logger = logging.getLogger("serial.codec")


@dataclass(frozen=True)
class DecodedFrame:
    """Đại diện cho một khung đã giải mã từ luồng nối tiếp."""

    raw: bytes
    group: int
    payload: bytes
    declared_length: int
    crc_ok: bool

    def payload_as_ints(self) -> tuple[int, ...]:
        """Trả về payload dưới dạng tuple số nguyên thuận tiện cho so sánh."""
        return tuple(b for b in self.payload)


class FrameCodec:
    """Mã hóa và giải mã khung dựa trên giao thức MCU đã công bố."""

    HEADER = b"\x24\x24"
    FOOTER = b"\x23\x23"
    MIN_FRAME_SIZE = len(HEADER) + 1 + 1 + 1 + len(FOOTER)  # header + len + group + crc + footer

    @classmethod
    def compute_crc(cls, data: Sequence[int]) -> int:
        """Tính tổng kiểm tra CRC đơn giản cho một chuỗi byte."""
        crc = 0
        for byte in data:
            crc = (crc + (byte & 0xFF)) & 0xFF
        return crc

    @classmethod
    def encode(cls, payload: Sequence[int], length: int | None = None) -> bytes:
        """Đóng gói payload thành khung hợp lệ kèm header, CRC và footer."""
        payload_bytes = [byte & 0xFF for byte in payload]
        if length is None:
            length = len(payload_bytes) + 3  # payload + crc + footer(2)
        frame_bytes = bytearray()
        frame_bytes.extend(cls.HEADER)
        frame_bytes.append(length & 0xFF)
        frame_bytes.extend(payload_bytes)
        crc_source = list(cls.HEADER) + [length & 0xFF] + payload_bytes
        crc = cls.compute_crc(crc_source)
        frame_bytes.append(crc)
        frame_bytes.extend(cls.FOOTER)
        return bytes(frame_bytes)

    @classmethod
    def extract_frames(cls, buffer: bytearray) -> list[DecodedFrame]:
        """Tách các khung hoàn chỉnh khỏi bộ đệm nhận."""
        frames: list[DecodedFrame] = []
        while True:
            if len(buffer) < cls.MIN_FRAME_SIZE:
                break

            header_index = cls._find_header(buffer)
            if header_index < 0:
                buffer.clear()
                break
            if header_index > 0:
                del buffer[:header_index]
                if len(buffer) < cls.MIN_FRAME_SIZE:
                    break

            declared_length = buffer[2]
            total_length = 3 + declared_length  # header(2) + length byte + declared_length
            if total_length < cls.MIN_FRAME_SIZE:
                logger.debug("Declared length %d shorter than minimum frame size, dropping byte.", declared_length)
                del buffer[0]
                continue

            if len(buffer) < total_length:
                # Wait for additional data.
                break

            frame_bytes = bytes(buffer[:total_length])
            if frame_bytes[-2:] != cls.FOOTER:
                # Attempt recovery by looking for an actual footer in the buffered data.
                tail_start = cls._find_footer(buffer, start=3)
                if tail_start < 0:
                    logger.debug("Footer not yet present for frame, waiting for more data.")
                    break
                total_length = tail_start + len(cls.FOOTER)
                if len(buffer) < total_length:
                    break
                frame_bytes = bytes(buffer[:total_length])
                actual_declared = total_length - 3
                logger.debug(
                    "Length mismatch detected (declared=%d, actual=%d). Using recovered frame.",
                    declared_length,
                    actual_declared,
                )
                declared_length = actual_declared

            crc_index = len(frame_bytes) - len(cls.FOOTER) - 1
            if crc_index <= 3:
                logger.debug("Frame too short after footer validation; discarding.")
                del buffer[0]
                continue

            crc_byte = frame_bytes[crc_index]
            crc_domain = frame_bytes[:crc_index]
            computed_crc = cls.compute_crc(crc_domain)
            payload_bytes = frame_bytes[3:crc_index]
            group = payload_bytes[0] if payload_bytes else 0
            payload = payload_bytes[1:] if len(payload_bytes) > 1 else b""
            frames.append(
                DecodedFrame(
                    raw=frame_bytes,
                    group=group,
                    payload=payload,
                    declared_length=declared_length,
                    crc_ok=(crc_byte == computed_crc),
                )
            )
            del buffer[:total_length]

        return frames

    @classmethod
    def _find_header(cls, buffer: bytearray) -> int:
        """Tìm vị trí header trong bộ đệm; trả về -1 nếu không thấy."""
        for idx in range(len(buffer) - 1):
            if buffer[idx] == cls.HEADER[0] and buffer[idx + 1] == cls.HEADER[1]:
                return idx
        return -1

    @classmethod
    def _find_footer(cls, buffer: bytearray, start: int) -> int:
        """Tìm vị trí footer kể từ chỉ số start; trả về -1 nếu không tồn tại."""
        for idx in range(start, len(buffer) - 1):
            if buffer[idx] == cls.FOOTER[0] and buffer[idx + 1] == cls.FOOTER[1]:
                return idx
        return -1
