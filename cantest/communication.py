import can
from config import REFACTORING, MOTOR_RANGE
from utils import clamp8
import os

def can_search():
    channels = ["DEMO-MODE"]
    try:
        for name in os.listdir("/sys/class/net"):
            if name.startswith(("can", "vcan", "slcan")):
                channels.append(name)
    except OSError:
        pass
    return channels

class MotorCommunication:
    def __init__(self, channel, min_limits):
        self.bus = None
        self.demo = (channel == "DEMO-MODE")
        self.min_limits = min_limits

        if not self.demo:
            try:
                self.bus = can.interface.Bus(channel=channel, interface="socketcan")
            except OSError:
                print("CAN open failed, switching to demo mode")
                self.demo = True

    def send_frame(self, data, board_id):
        if self.demo:
            print(f"DEMO -> board {board_id:2d}: [{' '.join(f'{b:3d}' for b in data)}]")
            return

        msg = can.Message(
            arbitration_id=board_id + 0x100,
            data=data,
            is_extended_id=False
        )
        try:
            self.bus.send(msg, timeout=0.1)
            print(f"CAN -> board {board_id:2d}: [{' '.join(f'{b:3d}' for b in data)}]")
        except can.CanError as e:
            print(f"CAN send failed: {e}")

    def scale_value(self, board_index, motor_index, destination):
        if not REFACTORING:
            return clamp8(destination)

        motor_min = self.min_limits[board_index][motor_index]
        motor_max = min(motor_min + MOTOR_RANGE, 255)

        mapped = motor_min + destination * (motor_max - motor_min) / 255.0
        return clamp8(mapped)

    def send_positions(self, locations):
        board_count = len(locations)
        motors_per_board = len(locations[0])

        if motors_per_board != 14:
            print(f"ERROR: expected 14 motors per board, got {motors_per_board}")
            return

        for board_index in range(board_count):
            board_id = board_index + 1

            data_low = bytes(
                [1] +
                [self.scale_value(board_index, m, locations[board_index][m]) for m in range(7)]
            )
            data_high = bytes(
                [2] +
                [self.scale_value(board_index, m, locations[board_index][m]) for m in range(7, 14)]
            )

            self.send_frame(data_high, board_id)
            self.send_frame(data_low, board_id)

    def send_board_config(self, board_id, kp, ki, kd, alpha, limit_signal, deadband):
        data = bytes([
            3,
            clamp8(kp),
            clamp8(ki),
            clamp8(kd),
            clamp8(alpha),
            clamp8(limit_signal),
            clamp8(deadband),
            0
        ])
        self.send_frame(data, board_id)