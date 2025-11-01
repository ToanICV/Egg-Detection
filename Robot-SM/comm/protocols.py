class RobotProtocol:
    """Class handling robot communication protocols."""
    
    # BASE COMMANDS REQUESTS
    CMD_BASE_MOVE_FORWARD   = bytearray([0x24, 0x24, 0x05, 0x04, 0x01, 0x52, 0x23, 0x23])
    CMD_BASE_MOVE_BACKWARD  = bytearray([0x24, 0x24, 0x05, 0x04, 0x02, 0x53, 0x23, 0x23]) 
    CMD_BASE_MOVE_STOP      = bytearray([0x24, 0x24, 0x05, 0x04, 0x03, 0x54, 0x23, 0x23])
    CMD_BASE_TURN_90        = bytearray([0x24, 0x24, 0x05, 0x04, 0x04, 0x55, 0x23, 0x23])
    CMD_BASE_READ_STATE     = bytearray([0x24, 0x24, 0x05, 0x03, 0x05, 0x55, 0x23, 0x23])

    # ARM COMMANDS REQUESTS
    CMD_ARM_READ_STATE      = bytearray([0x24, 0x24, 0x06, 0x03, 0x51, 0x23, 0x23])

    @staticmethod
    def build_pick_up_command(x: int, y: int) -> bytearray:
        """Builds a command to pick up an object at coordinates (x, y).
        Args:
            x (int): X coordinate in mm.
            y (int): Y coordinate in mm.
        Returns:
            bytearray: The command to send to the robot.
        """
        command = bytearray([0x24, 0x24, 0x06, 0x04])
        command += x.to_bytes(2, byteorder='big', signed=True)
        command += y.to_bytes(2, byteorder='big', signed=True)
        checksum = sum(command[2:]) & 0xFF
        command += bytearray([checksum, 0x23, 0x23])
        return command