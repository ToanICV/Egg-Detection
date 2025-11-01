import argparse
import sys
from typing import Optional

from serial_comm import SerialComm


def to_hex(b: bytes) -> str:
    return " ".join(f"{x:02X}" for x in b)


def build_command(args: argparse.Namespace) -> bytes:
    try:
        return SerialComm.build_command(
            args.command,
            x=args.x if args.command == "pickup" else None,
            y=args.y if args.command == "pickup" else None,
            hex_str=args.hex if args.command == "raw_hex" else None,
        )
    except ValueError as e:
        print(str(e))
        sys.exit(2)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Test serial communication with robot protocols")
    parser.add_argument("--port", default="COM14", help="Serial port (default: COM14)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 9600)")
    parser.add_argument(
        "--command",
        default="base_read_state",
        choices=[
            "base_forward",
            "base_backward",
            "base_stop",
            "base_turn90",
            "base_read_state",
            "arm_read_state",
            "pickup",
            "raw_hex",
        ],
        help="Protocol command to send",
    )
    parser.add_argument("--x", type=int, help="X coordinate (mm) for pickup")
    parser.add_argument("--y", type=int, help="Y coordinate (mm) for pickup")
    parser.add_argument("--hex", type=str, help="Raw hex bytes for raw_hex command (e.g. '24 24 05 04 01 52 23 23')")
    parser.add_argument("--no-wait", action="store_true", help="Do not wait for response")

    args = parser.parse_args(argv)

    comm = SerialComm(args.port, args.baud)
    if not comm.is_open():
        print("Failed to open serial port.")
        return 1

    try:
        payload = build_command(args)
        print(f"Sending ({len(payload)} bytes): {to_hex(payload)}")
        written = comm.send(payload)
        print(f"Wrote {written} bytes")

        if not args.no_wait:
            resp = comm.receive()
            if resp:
                print(f"Response ({len(resp)} bytes): {to_hex(resp)}")
            else:
                print("No response received (within timeout).")
    finally:
        comm.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())