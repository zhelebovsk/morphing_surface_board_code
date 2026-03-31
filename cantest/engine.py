import queue
import threading
import time

from config import BOARD_COUNT, MOTORS_PER_BOARD, REFACTORING
from wingcontrol import WingControl
from communication import MotorCommunication
from utils import clamp8
from function import motor_function


class ControlMotor:
    UPDATE_HZ = 100.0
    UPDATE_DT = 1.0 / UPDATE_HZ

    def __init__(self, channel, min_limits, max_limits, range_of_motion,
                 board_count=BOARD_COUNT, motors_per_board=MOTORS_PER_BOARD):
        self.board_count = board_count
        self.motors_per_board = motors_per_board
        self.wing_control = WingControl(range_of_motion, board_count, motors_per_board, offset=0)
        self.communication = MotorCommunication(channel, min_limits, max_limits)
        self.running = False
        self.step_index = 0
        self._frame_queue = queue.Queue()

    def displayed_value(self, board, motor):
        raw_value = self.wing_control.locations[board][motor]
        if not REFACTORING:
            return clamp8(raw_value)
        return self.communication.scale_value(board, motor, raw_value)

    def run_static(self, t):
        self.wing_control.fill_from_function(motor_function, t=t)
        self.communication.send_positions(self.wing_control.locations)

    def start_dynamic(self):
        if self.running:
            return
        self.running = True
        self.step_index = 0
        self._frame_queue = queue.Queue()
        threading.Thread(target=self._send_loop, daemon=True).start()

    def _send_loop(self):
        next_time = time.perf_counter()
        while self.running:
            t = self.step_index * self.UPDATE_DT
            self.wing_control.fill_from_function(motor_function, t)
            locations = self.wing_control.locations
            t0 = time.perf_counter()
            self.communication.send_positions(locations)
            send_ms = (time.perf_counter() - t0) * 1000
            if send_ms > self.UPDATE_DT * 1000:
                print(f"\033[91mWARNING: send_positions took {send_ms:.1f} ms, "
                      f"exceeds cycle period {self.UPDATE_DT*1000:.1f} ms\033[0m")
            self._frame_queue.put([row[:] for row in locations])
            self.step_index += 1
            next_time = max(next_time + self.UPDATE_DT, time.perf_counter())
            sleep_for = next_time - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)

    def stop_dynamic(self):
        self.running = False

    def drain_frame_queue(self):
        """Return the latest frame from the queue, or None if empty."""
        latest = None
        try:
            while True:
                latest = self._frame_queue.get_nowait()
        except queue.Empty:
            pass
        return latest

    def send_config(self, board_ids, kp, ki, kd, alpha, limit_signal, deadband):
        for board_id in board_ids:
            self.communication.send_board_config(board_id, kp, ki, kd, alpha, limit_signal, deadband)
