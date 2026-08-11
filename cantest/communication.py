import can
import time
import threading
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

        # Boards confirmed present. Populated by scan_boards()/poll_presence();
        # empty (== "unknown") means send_positions falls back to sending to everyone.
        self.active_boards = set()
        self._scanned = False
        self._miss_counts = {}
        self._monitor_cursor = 0

        # scan_boards() and poll_presence() both listen on the same socket for
        # pongs; without this lock a background presence check and a manual
        # scan can steal each other's replies, producing false "missing" boards.
        self._bus_lock = threading.RLock()

        self._send_fail_count = 0
        self._last_fail_warning_time = time.monotonic()

        if not self.demo:
            try:
                self.bus = can.interface.Bus(channel=channel, interface="socketcan")
            except OSError:
                print("CAN open failed, switching to demo mode")
                self.demo = True

    def send_frame(self, data, board_id, verbose=False):
        if self.demo:
            if verbose:
                print(f"DEMO -> board {board_id:2d}: [{' '.join(f'{b:3d}' for b in data)}]")
            return

        msg = can.Message(
            arbitration_id=board_id + 0x100,
            data=data,
            is_extended_id=False,
        )
        try:
            self.bus.send(msg, timeout=0.1)
            if verbose:
                print(f"CAN -> board {board_id:2d}: [{' '.join(f'{b:3d}' for b in data)}]")
        except can.CanError as e:
            # A wedged/unterminated bus fails every single frame — without
            # throttling this becomes an unreadable flood within seconds.
            self._send_fail_count += 1
            now = time.monotonic()
            if now - self._last_fail_warning_time > 1.0:
                print(
                    f"CAN send failed ({self._send_fail_count} time(s) in the "
                    f"last {now - self._last_fail_warning_time:.1f}s): {e}"
                )
                self._last_fail_warning_time = now
                self._send_fail_count = 0

    def _drain_rx(self):
        """Discard anything already queued on the socket (stale pongs, leftover
        telemetry) so a fresh listen window isn't polluted and the kernel's
        receive buffer doesn't quietly build up between scans."""
        if self.demo or self.bus is None:
            return
        while self.bus.recv(timeout=0) is not None:
            pass

    def _listen_for_pongs(self, targets, timeout):
        """Listen up to `timeout` seconds for 0xA1 pongs from `targets`.
        Returns as soon as every target has replied instead of always
        waiting out the full window."""
        found = set()
        remaining_targets = set(targets)
        deadline = time.monotonic() + timeout
        with self._bus_lock:
            while remaining_targets:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                msg = self.bus.recv(timeout=remaining)
                if msg is None:
                    break
                if len(msg.data) >= 2 and msg.data[0] == 0xA1:
                    responder = msg.arbitration_id - 0x100
                    if responder in remaining_targets:
                        found.add(responder)
                        remaining_targets.discard(responder)
        return found

    def scan_boards(self, board_count, timeout=0.3, retries=1):
        """Ping every board and return the ones that answer. A single dropped
        ping or pong shouldn't permanently brand a live board as missing, so
        boards that don't answer the first round get a couple more tries —
        only the still-missing ones are re-pinged, not the whole bus."""
        if self.demo:
            print("DEMO: assuming all boards present")
            self.active_boards = set(range(1, board_count + 1))
            self._scanned = True
            return sorted(self.active_boards)

        with self._bus_lock:
            self._drain_rx()

        pending = set(range(1, board_count + 1))
        found = set()

        for attempt in range(retries + 1):
            if not pending:
                break
            for board_id in sorted(pending):
                self.send_frame(bytes([0x06]), board_id)

            replied = self._listen_for_pongs(pending, timeout)
            found |= replied
            pending -= replied

        self.active_boards = found
        self._miss_counts = {board_id: 0 for board_id in found}
        self._scanned = True
        return sorted(found)

    def poll_presence(self, board_count, subset_size=5, timeout=0.15, miss_threshold=3):
        """Lightweight incremental presence check meant to run periodically in
        the background (see engine.py). Every call re-pings all currently
        missing boards (cheap — usually few or none) plus a rotating slice of
        already-active boards, so a full 30-board sweep happens over several
        calls instead of one large burst. A board is only dropped from
        active_boards after `miss_threshold` consecutive missed pongs, so one
        lost frame on a busy 30-board bus doesn't flap its status."""
        if self.demo:
            return sorted(self.active_boards)

        all_boards = list(range(1, board_count + 1))
        missing = [b for b in all_boards if b not in self.active_boards]

        active_list = sorted(self.active_boards)
        recheck = []
        if active_list and subset_size > 0:
            n = len(active_list)
            start = self._monitor_cursor % n
            recheck = [active_list[(start + i) % n] for i in range(min(subset_size, n))]
            self._monitor_cursor = (start + len(recheck)) % n

        targets = set(missing) | set(recheck)
        if not targets:
            self._scanned = True
            return sorted(self.active_boards)

        with self._bus_lock:
            self._drain_rx()
        for board_id in sorted(targets):
            self.send_frame(bytes([0x06]), board_id)

        replied = self._listen_for_pongs(targets, timeout)

        for board_id in targets:
            if board_id in replied:
                self._miss_counts[board_id] = 0
                self.active_boards.add(board_id)
            else:
                misses = self._miss_counts.get(board_id, 0) + 1
                self._miss_counts[board_id] = misses
                if misses >= miss_threshold:
                    self.active_boards.discard(board_id)

        self._scanned = True
        return sorted(self.active_boards)

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

            # Skip boards we know are absent — once we've scanned at least
            # once, don't waste bus time/cycle budget writing into the void.
            if self._scanned and board_id not in self.active_boards:
                continue

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

    def send_board_config(self, board_id, kp, ki, kd, alpha, limit_signal, deadband, min_pwm=20):
        data = bytes([
            3,
            clamp8(kp),
            clamp8(ki),
            clamp8(kd),
            clamp8(alpha),
            clamp8(limit_signal),
            clamp8(deadband),
            clamp8(min_pwm),
        ])
        self.send_frame(data, board_id)