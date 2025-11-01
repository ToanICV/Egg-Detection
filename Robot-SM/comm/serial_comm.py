import serial
import time
from typing import Optional


class SerialComm:
    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 1.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.connection: Optional[serial.Serial] = None
        self._rx_buf = bytearray()
        self.connect()

    def connect(self) -> None:
        try:
            self.connection = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
            # Clear buffers on start
            try:
                self.connection.reset_input_buffer()
                self.connection.reset_output_buffer()
            except Exception:
                pass
            print(f"Connected to {self.port} at {self.baudrate} baud.")
        except serial.SerialException as e:
            print(f"Error connecting to serial port: {e}")

    def is_open(self) -> bool:
        return bool(self.connection and self.connection.is_open)

    def close(self) -> None:
        if self.connection and self.connection.is_open:
            try:
                self.connection.close()
                print("Serial port closed.")
            except Exception as e:
                print(f"Error closing serial port: {e}")

    def send(self, data: bytes) -> int:
        """Send raw bytes to the serial port."""
        if not self.is_open():
            print("Connection is not open.")
            return 0
        if isinstance(data, bytearray):
            data = bytes(data)
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError("send() expects bytes or bytearray")
        written = self.connection.write(data)
        return int(written)

    def receive(self, size: Optional[int] = None, wait_time: float = 0.05) -> bytes:
        """Receive bytes from the serial port.
        If size is None, read whatever is available after a short wait.
        """
        if not self.is_open():
            print("Connection is not open.")
            return b""

        if size is None:
            time.sleep(wait_time)
            available = getattr(self.connection, "in_waiting", 0)
            if available:
                data = self.connection.read(available)
                self._rx_buf.extend(data)
                return bytes(data)
            # fallback: try to read 1 byte within timeout
            first = self.connection.read(1)
            if not first:
                return b""
            self._rx_buf.extend(first)
            time.sleep(wait_time)
            more = getattr(self.connection, "in_waiting", 0)
            if more:
                rest = self.connection.read(more)
                self._rx_buf.extend(rest)
                first += rest
            return bytes(first)
        else:
            data = self.connection.read(size)
            self._rx_buf.extend(data)
            return bytes(data)

    # --- Protocol parsing ---
    def _try_extract_frame(self) -> Optional[bytes]:
        """Extract a single protocol frame from internal buffer if available.

        Frame format (theo RobotProtocol ví dụ):
        - Start: 0x24 0x24 ('$$')
        - Sau đó: 1 byte length? (protocol hiện tại có len/loại lệnh khác nhau)
        - Kết thúc: 0x23 0x23 ('##')

        Ở đây ta dùng chiến lược: tìm header '$$', tìm footer '##' tiếp theo và cắt ra.
        Nếu muốn chính xác hơn theo length/checksum, có thể mở rộng dựa trên specs.
        """
        buf = self._rx_buf
        if len(buf) < 4:
            return None
        # tìm header
        try:
            start = buf.index(0x24)
            if start + 1 >= len(buf) or buf[start + 1] != 0x24:
                # không đủ '$$' liên tiếp, bỏ byte đầu
                del buf[: start + 1]
                return None
        except ValueError:
            # không có '$' → xóa buffer
            buf.clear()
            return None

        # tìm footer sau header
        try:
            end = buf.index(0x23, start + 2)
            # cần 2 byte '##'
            while end + 1 < len(buf) and buf[end + 1] != 0x23:
                end = buf.index(0x23, end + 1)
            if end + 1 >= len(buf):
                return None  # chưa đủ '##'
        except ValueError:
            return None

        frame = bytes(buf[start : end + 2])
        # cắt buffer đến sau frame
        del buf[: end + 2]
        return frame

    def read_frame(self, timeout_s: float = 0.5) -> Optional[bytes]:
        """Đọc một frame hoàn chỉnh theo giao thức trong khoảng thời gian timeout."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            # cố gắng rút trích từ buffer hiện có
            frame = self._try_extract_frame()
            if frame:
                return frame
            # nếu chưa có, đọc thêm dữ liệu
            self.receive()
            frame = self._try_extract_frame()
            if frame:
                return frame
        return None

    @staticmethod
    def _compute_crc(data: bytes) -> int:
        """Tính CRC theo mô tả: CRC = (tổng từ Header đến hết payload) & 0xFF.
        Lưu ý: không bao gồm CRC và Footer trong phép tính."""
        return sum(data) & 0xFF

    def parse_frame(self, frame: bytes) -> Optional[dict]:
        """Giải mã frame theo docs/protocols.md.

        Cấu trúc chung:
        - Header: 0x24 0x24
        - Source: 0x06 Arm, 0x05 Actor
        - Type:   0x04 ACK, 0x03 State
        - Payload: biến độ dài tùy loại
        - CRC:    1 byte
        - Footer: 0x23 0x23
        """
        if len(frame) < 8:
            return None
        if not (frame[0] == 0x24 and frame[1] == 0x24 and frame[-2] == 0x23 and frame[-1] == 0x23):
            return None
        src = frame[2]
        typ = frame[3]
        # payload = bytes từ index 4 đến trước CRC (len-3)
        payload = frame[4:-3]
        crc = frame[-3]
        calc_crc = self._compute_crc(frame[:-3])
        if crc != calc_crc:
            # CRC sai → vẫn trả về raw để debug
            return {
                "ok": False,
                "raw": frame,
                "error": "crc_mismatch",
                "crc_calc": calc_crc,
                "crc_recv": crc,
            }
        info = {"ok": True, "raw": frame}
        info["source"] = "arm" if src == 0x06 else ("actor" if src == 0x05 else f"0x{src:02X}")
        info["type"] = "ack" if typ == 0x04 else ("state" if typ == 0x03 else f"0x{typ:02X}")

        # Giải payload theo bảng mẫu
        if src == 0x05 and typ == 0x04:  # Actor ACK
            # payload 1 byte 0xFF
            info["ack"] = True if payload and payload[0] == 0xFF else False
        elif src == 0x05 and typ == 0x03:  # Actor State
            # payload: [moving_flag, obstacle_cm]
            if len(payload) >= 2:
                info["moving"] = bool(payload[0])
                info["obstacle_cm"] = int(payload[1])
        elif src == 0x06 and typ == 0x04:  # Arm ACK
            # payload: 0xFF 0xFF
            info["ack"] = True if len(payload) >= 2 and payload[0] == 0xFF and payload[1] == 0xFF else False
        elif src == 0x06 and typ == 0x03:  # Arm State
            # payload: [busy_flag]
            if len(payload) >= 1:
                info["arm_busy"] = bool(payload[0])
        else:
            info["payload"] = payload
        return info

    def read_parsed(self, timeout_s: float = 0.5) -> Optional[dict]:
        frame = self.read_frame(timeout_s=timeout_s)
        if not frame:
            return None
        return self.parse_frame(frame)

    @staticmethod
    def build_command(command: str, x: Optional[int] = None, y: Optional[int] = None, hex_str: Optional[str] = None) -> bytes:
        """Build a binary command payload using RobotProtocol or raw hex.

        Parameters:
        - command: one of
            'base_forward', 'base_backward', 'base_stop', 'base_turn90',
            'base_read_state', 'arm_read_state', 'pickup', 'raw_hex'
        - x, y: coordinates (mm) for 'pickup' command
        - hex_str: space-separated hex bytes for 'raw_hex' command

        Returns:
        - bytes payload to send over serial

        Raises:
        - ValueError for invalid inputs
        """
        try:
            from .protocols import RobotProtocol  # type: ignore
        except Exception:
            from protocols import RobotProtocol  # type: ignore

        cmd = command
        if cmd == "base_forward":
            return bytes(RobotProtocol.CMD_BASE_MOVE_FORWARD)
        if cmd == "base_backward":
            return bytes(RobotProtocol.CMD_BASE_MOVE_BACKWARD)
        if cmd == "base_stop":
            return bytes(RobotProtocol.CMD_BASE_MOVE_STOP)
        if cmd == "base_turn90":
            return bytes(RobotProtocol.CMD_BASE_TURN_90)
        if cmd == "base_read_state":
            return bytes(RobotProtocol.CMD_BASE_READ_STATE)
        if cmd == "arm_read_state":
            return bytes(RobotProtocol.CMD_ARM_READ_STATE)
        if cmd == "pickup":
            if x is None or y is None:
                raise ValueError("pickup command requires x and y (in mm)")
            return bytes(RobotProtocol.build_pick_up_command(int(x), int(y)))
        if cmd == "raw_hex":
            if not hex_str:
                raise ValueError("raw_hex command requires hex_str like '24 24 05 04 01 52 23 23'")
            parts = hex_str.replace(",", " ").split()
            try:
                return bytes(int(p, 16) for p in parts)
            except ValueError as e:
                raise ValueError("Invalid hex sequence. Use space-separated hex bytes, e.g. '24 24 05 04 01 52 23 23'") from e

        raise ValueError(f"Unknown command: {cmd}")


