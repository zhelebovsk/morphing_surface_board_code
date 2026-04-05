import queue
import threading
import time

from config import BOARD_COUNT, MOTORS_PER_BOARD, REFACTORING, DYNAMIC_CYCLE_HZ, BLINK_DURATION_SEC, UPDATE_HZ
from wingcontrol import WingControl
from communication import MotorCommunication
from utils import clamp8
from function import motor_function



class ControlMotor:
    UPDATE_DT = 1.0 / UPDATE_HZ

    def __init__(self, channel, min_limits, range_of_motion,
                 board_count=BOARD_COUNT, motors_per_board=MOTORS_PER_BOARD):
        self.board_count = board_count
        self.motors_per_board = motors_per_board

        self.wing_control = WingControl(
            range_of_motion,
            board_count,
            motors_per_board,
            offset=0
        )
        self.communication = MotorCommunication(channel, min_limits)

        self.running = False
        self.step_index = 0
        self._frame_queue = queue.Queue()

        self._thread = None
        self._lock = threading.Lock()

        # dynamic-only state
        self.dynamic_t = 0.0
        self.dynamic_mu = DYNAMIC_CYCLE_HZ
        self.dynamic_phi = 0.0
        self.dynamic_N = 0
        self._blink_until = 0.0

    def displayed_value(self, board, motor):
        raw_value = self.wing_control.locations[board][motor]
        if not REFACTORING:
            return clamp8(raw_value)
        return self.communication.scale_value(board, motor, raw_value)

    def run_static(self, t):
        # static preview only; does not change dynamic timer state
        self.wing_control.fill_from_function(motor_function, t=t)
        self.communication.send_positions(self.wing_control.locations)

    def start_dynamic(self):
        if self.running:
            return

        self.running = True
        self._frame_queue = queue.Queue()

        self._thread = threading.Thread(target=self._send_loop, daemon=True)
        self._thread.start()

    def _send_loop(self):
        next_time = time.perf_counter()

        while self.running:
            with self._lock:
                t = self.step_index * self.UPDATE_DT
                self.dynamic_t = t

                cycles = t * self.dynamic_mu
                cycle_index = int(cycles)
                phi = cycles - cycle_index

                # blink at the start of every new cycle
                if cycle_index != self.dynamic_N:
                    self._blink_until = time.perf_counter() + BLINK_DURATION_SEC

                self.dynamic_N = cycle_index
                self.dynamic_phi = phi

            self.wing_control.fill_from_function(motor_function, t=t)
            locations = self.wing_control.locations

            t0 = time.perf_counter()
            self.communication.send_positions(locations)
            send_ms = (time.perf_counter() - t0) * 1000.0

            if send_ms > self.UPDATE_DT * 1000.0:
                print(
                    f"\033[91mWARNING: send_positions took {send_ms:.1f} ms, "
                    f"exceeds cycle period {self.UPDATE_DT * 1000.0:.1f} ms\033[0m"
                )

            self._frame_queue.put([row[:] for row in locations])

            with self._lock:
                self.step_index += 1
                self.dynamic_t = self.step_index * self.UPDATE_DT

            next_time = max(next_time + self.UPDATE_DT, time.perf_counter())
            sleep_for = next_time - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)

    def stop_dynamic(self):
        self.running = False

    def reset_dynamic(self):
        # stop first, then reset dynamic-only state
        self.running = False

        with self._lock:
            self.step_index = 0
            self.dynamic_t = 0.0
            self.dynamic_phi = 0.0
            self.dynamic_N = 0
            self._blink_until = 0.0

        self._frame_queue = queue.Queue()

    def get_dynamic_info(self):
        with self._lock:
            return {
                "t": self.dynamic_t,
                "mu": self.dynamic_mu,
                "phi": self.dynamic_phi,
                "N": self.dynamic_N,
                "blink": time.perf_counter() < self._blink_until,
            }

    def set_dynamic_mu(self, mu):
        with self._lock:
            self.dynamic_mu = max(0.001, float(mu))


    def drain_frame_queue(self):
        latest = None
        try:
            while True:
                latest = self._frame_queue.get_nowait()
        except queue.Empty:
            pass
        return latest

    def reload_limits(self):
        from limits import load_all_limits
        min_limits, _ = load_all_limits()
        self.communication.min_limits = min_limits

    def send_config(self, board_ids, kp, ki, kd, alpha, limit_signal, deadband):
        for board_id in board_ids:
            self.communication.send_board_config(
                board_id, kp, ki, kd, alpha, limit_signal, deadband
            )