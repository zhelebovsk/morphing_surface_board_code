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
        self.communication.scan_boards(board_count)

        from limits import load_all_limits
        _, _, self.min_pwm_by_board = load_all_limits()

        # Config last sent to each board via send_config(), re-sent by the
        # monitor loop to any board that reset since. A board that never got
        # one (e.g. connected later) gets the most recent config sent to any
        # board. Empty until the user first sends one — until then every
        # board is on firmware defaults anyway.
        self._config_by_board = {}
        self._last_config = None

        self.running = False
        self.step_index = 0
        self._frame_queue = queue.Queue()

        self._thread = None
        self._lock = threading.Lock()

        self._last_warning_time = time.perf_counter()
        self._overbudget_count = 0

        # Presence isn't just checked once at startup: boards can drop off or
        # come back over a long run, so keep re-checking in the background at
        # the full 30-board scale instead of trusting a single boot-time scan.
        self._monitor_running = True
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

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
                self._overbudget_count += 1
                now = time.perf_counter()
                if now - self._last_warning_time > 1.0:
                    print(
                        f"\033[91mWARNING: send_positions took {send_ms:.1f} ms, "
                        f"exceeds cycle period {self.UPDATE_DT * 1000.0:.1f} ms "
                        f"({self._overbudget_count} time(s) in the last "
                        f"{now - self._last_warning_time:.1f}s)\033[0m"
                    )
                    self._last_warning_time = now
                    self._overbudget_count = 0

            self._frame_queue.put([row[:] for row in locations])

            with self._lock:
                self.step_index += 1
                self.dynamic_t = self.step_index * self.UPDATE_DT

            next_time = max(next_time + self.UPDATE_DT, time.perf_counter())
            sleep_for = next_time - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)

    def _monitor_loop(self, interval=1.0, max_interval=10.0):
        current_interval = interval
        while self._monitor_running:
            try:
                self.communication.poll_presence(self.board_count)
                self._resend_config_where_needed()
                # Nothing answered at all -> the bus itself is likely down
                # (unterminated/disconnected), not just one flaky board.
                # Back off instead of hammering a dead bus every second.
                if self.communication.active_boards:
                    current_interval = interval
                else:
                    current_interval = min(current_interval * 2, max_interval)
            except Exception as e:
                print(f"presence check failed: {e}")
                current_interval = min(current_interval * 2, max_interval)
            time.sleep(current_interval)

    def _resend_config_where_needed(self):
        if self._last_config is None:
            return
        boards = sorted(self.communication.needs_config & self.communication.active_boards)
        if not boards:
            return
        print(f"Re-sending controller config to board(s) {boards} (reset since last config)")
        for board_id in boards:
            self.send_config([board_id], *self._config_by_board.get(board_id, self._last_config))

    def shutdown(self):
        self.running = False
        self._monitor_running = False

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
        min_limits, _, min_pwm_by_board = load_all_limits()
        self.communication.min_limits = min_limits
        self.min_pwm_by_board = min_pwm_by_board

    def send_config(self, board_ids, kp, ki, kd, alpha, limit_signal, deadband, min_pwm=None):
        # min_pwm=None (the default) means "use each board's own calibrated
        # value from HW_tests" instead of forcing one number on every board.
        self._last_config = (kp, ki, kd, alpha, limit_signal, deadband, min_pwm)
        for board_id in board_ids:
            self._config_by_board[board_id] = self._last_config
            self.communication.needs_config.discard(board_id)
            pwm = min_pwm if min_pwm is not None else self.min_pwm_by_board[board_id - 1]
            self.communication.send_board_config(
                board_id, kp, ki, kd, alpha, limit_signal, deadband, pwm
            )