"""
motion_timing_test.py — measure how fast one motor really moves.

Modes:
  step   one move from the current position to --to
  stroke edge to edge: --low -> --high -> --low (both directions, incl. reversal)
  sine   track a sine between --low and --high at each μ in --mu (cycles/s), 100 Hz setpoints

Measures (from the board's own telemetry stream, ~1 kHz, board timestamps):
  first motion (8 counts), time to cruise (90 % of cruise speed, ±12 ms), cruise speed (median
  speed while the PID is saturated at u_limit), average speed over 10–90 %, rise
  time, travel time (first within the deadband), overshoot (coast past target), parked time
  (stays within deadband+5), settle time (stays within the deadband), final error;
  for sine: amplitude ratio and phase/time lag per μ.

No ST-LINK needed. Positions are ADC counts (pass --mm-per-count to also get mm).

Usage (from hostCan/HW_tests, CAN up, main GUI closed):
  python3 motion_timing_test.py BOARD MOTOR stroke --low 1100 --high 2100 [--u-limit 65]
  python3 motion_timing_test.py BOARD MOTOR step --to 1800
  python3 motion_timing_test.py BOARD MOTOR sine --low 1300 --high 1900 --mu 0.1,0.3,0.5
  MOTOR is the host number m1..m14 (hardware channel = MOTOR + 1).

Notes:
  - Targets are quantised to the protocol's 7-count steps (ADC 1048 + 7·byte, up to 2833).
  - A position frame sets 7 motors; the other 6 in that frame are re-sent at their current
    positions so they hold still. The test refuses to run if one of them can't be held, unless
    you state that channel has no motor (--no-motor 13,14).
  - The board is left with the GUI's default controller config (u_limit 65); press
    "Send to all boards" in the GUI afterwards to apply your own settings.
"""

import argparse
import json
import math
import os
import sys
import time
from datetime import datetime

import can

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import CALIBRATION_FILE  # noqa: E402
from common import reply_ids  # noqa: E402

POT_ZERO, STEP, BYTE_MAX = 1048, 7, 255          # firmware: desired = 1048 + 7·byte
REACHABLE = (POT_ZERO, POT_ZERO + STEP * BYTE_MAX)
FW_LIMITS = (680, 3415)                            # firmware hard stop
GUI_CONFIG = dict(kp=51, ki=26, kd=0, alpha=51, u_limit=65, deadband=10)
STREAM_MS = 1                                      # telemetry interval
NOISE = 8                                          # counts: "has started moving"
SETTLE_HOLD_S = 0.3                                # inside band this long = settled
SPEED_WINDOW_S = 0.025                             # window for speed estimates
UPDATE_HZ = 100.0                                  # sine setpoint rate (= GUI)
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")


class Board:
    def __init__(self, bus, board):
        self.bus, self.id = bus, 0x100 + board
        self._ts_last = None
        self._ts_acc = 0

    def send(self, data):
        self.bus.send(can.Message(arbitration_id=self.id, data=bytes(data), is_extended_id=False))

    def config(self, kp, ki, kd, alpha, u_limit, deadband, min_pwm):
        self.send([0x03, kp, ki, kd, alpha, u_limit, deadband, min_pwm])

    def stream(self, fw_index):
        self._ts_last, self._ts_acc = None, 0
        self.send([0x04, fw_index, STREAM_MS])

    def stop_stream(self):
        self.send([0x05])

    def recv(self, timeout, fw_index):
        """Next telemetry sample of fw_index as (board_time_s, host_time_s, filtered), or None."""
        deadline = time.perf_counter() + timeout
        while True:
            left = deadline - time.perf_counter()
            if left <= 0:
                return None
            msg = self.bus.recv(timeout=left)
            if msg is None:
                return None
            d = msg.data
            if msg.arbitration_id not in reply_ids(self.id) or len(d) < 8 or d[0] != 0xA0 or d[1] != fw_index:
                continue
            filt = d[4] | (d[5] << 8)
            filt = filt - 65536 if filt >= 32768 else filt
            ts = d[6] | (d[7] << 8)                       # µs, wraps every 65.536 ms
            if self._ts_last is not None:
                self._ts_acc += (ts - self._ts_last) & 0xFFFF
            self._ts_last = ts
            return self._ts_acc / 1e6, time.perf_counter(), filt


def to_byte(adc):
    return max(0, min(BYTE_MAX, round((adc - POT_ZERO) / STEP)))


def read_position(board, fw_index, n=25):
    board.stream(fw_index)
    vals = []
    end = time.perf_counter() + 0.4
    while len(vals) < n and time.perf_counter() < end:
        s = board.recv(0.1, fw_index)
        if s:
            vals.append(s[2])
    return sorted(vals)[len(vals) // 2] if vals else None


def calibration_for(board, hw_channel):
    try:
        with open(CALIBRATION_FILE) as f:
            b = json.load(f)["boards"].get(str(board), {})
    except (OSError, ValueError):
        return None, None
    return b.get("recommended_min_pwm"), b.get("motors", {}).get(str(hw_channel), {})


class Mover:
    """Sends the position frame for the motor's half, holding the other 6 motors still."""

    def __init__(self, board, slot, park_bytes):
        self.board, self.slot = board, slot
        self.op, self.first = (0x01, 0) if slot < 7 else (0x02, 7)
        self.bytes = list(park_bytes)

    def go(self, byte):
        self.bytes[self.slot] = byte
        self.board.send([self.op] + self.bytes[self.first:self.first + 7])


def record_move(board, mover, fw, target_byte, deadband, timeout):
    """Command one move and record until settled or timeout. Returns samples + host send time."""
    target = POT_ZERO + STEP * target_byte
    samples = []
    for _ in range(20):                                   # baseline before the command
        s = board.recv(0.1, fw)
        if s:
            samples.append(s)
    t_cmd = time.perf_counter()
    mover.go(target_byte)
    inside_since = None
    while time.perf_counter() - t_cmd < timeout:
        s = board.recv(0.5, fw)
        if s is None:
            raise RuntimeError("telemetry stopped — check the board and the bus")
        samples.append(s)
        if abs(s[2] - target) <= deadband:
            inside_since = inside_since or s[1]
            if s[1] - inside_since >= SETTLE_HOLD_S:
                break
        else:
            inside_since = None
    return samples, t_cmd, target


def board_timeline(samples):
    """Board-time samples plus the offset that maps host time onto board time."""
    offset = min(h - b for b, h, _ in samples)            # smallest transport delay
    return [(b, p) for b, _, p in samples], offset


def analyse_move(samples, t_cmd, target, deadband, sat_err, mm):
    pts, offset = board_timeline(samples)
    t0 = t_cmd - offset                                   # command time on board clock
    before = [p for t, p in pts if t < t0] or [pts[0][1]]
    p0 = sorted(before)[len(before) // 2]
    dist = target - p0
    d = 1 if dist >= 0 else -1
    after = [(t - t0, p) for t, p in pts if t >= t0]

    def first(cond):
        return next((t for t, p in after if cond(p)), None)

    moved = first(lambda p: d * (p - p0) > NOISE)
    t10 = first(lambda p: d * (p - p0) >= 0.1 * abs(dist))
    t90 = first(lambda p: d * (p - p0) >= 0.9 * abs(dist))
    arrive = first(lambda p: abs(p - target) <= deadband)
    speeds = []                                           # (window centre, mean pos, speed)
    j = 0
    for i in range(len(after)):                           # least-squares slope per window
        while j < len(after) and after[j][0] - after[i][0] < SPEED_WINDOW_S:
            j += 1
        if j < len(after):
            w = after[i:j + 1]
            speeds.append((sum(t for t, _ in w) / len(w), sum(p for _, p in w) / len(w), d * slope(w)))
    # Cruise = speed while the PID output is saturated at u_limit (|error| >= sat_err).
    # Use the second half (in time) of that period, so spin-up is excluded.
    sat = [(t, v) for t, p, v in speeds if abs(target - p) >= sat_err and moved is not None and t >= moved]
    steady = [v for t, v in sat if sat and t >= (sat[0][0] + sat[-1][0]) / 2]
    cruise = sorted(steady)[len(steady) // 2] if len(steady) >= 3 else None
    t_cruise = next((t for t, _, v in speeds if cruise and v >= 0.9 * cruise), None)
    # Overshoot from a 5-sample running median (rejects single-sample spikes, keeps short coasts).
    med = [sorted(p for _, p in after[k:k + 5])[2] for k in range(len(after) - 4)]
    overshoot = max([0.0] + [d * (m - target) for (t, _), m in zip(after, med)
                             if arrive is not None and t >= arrive])
    band = deadband + 5

    def stays_within(limit):                              # start of the final stretch inside ±limit
        start = None
        for t, p in reversed(after):
            if abs(p - target) > limit:
                break
            start = t
        return start

    tail = [p for t, p in after if t >= after[-1][0] - 0.05]
    res = {
        "start_adc": p0, "target_adc": target, "distance_adc": dist,
        "first_motion_ms": ms(moved),
        "time_to_cruise_ms": ms(t_cruise),
        "cruise_speed_counts_s": round(cruise) if cruise else None,
        "avg_speed_10_90_counts_s": round(0.8 * abs(dist) / (t90 - t10)) if t10 is not None and t90 is not None and t90 > t10 else None,
        "rise_10_90_ms": ms(t90 - t10) if t10 is not None and t90 is not None else None,
        "travel_time_ms": ms(arrive),
        "overshoot_adc": round(overshoot, 1),
        f"parked_within_{band}_ms": ms(stays_within(band)),
        "settle_time_ms": ms(stays_within(deadband)),
        "final_error_adc": round(sorted(tail)[len(tail) // 2] - target, 1) if tail else None,
        "samples": len(after),
    }
    if mm:
        res.update({"distance_mm": round(abs(dist) * mm, 2), "overshoot_mm": round(overshoot * mm, 2),
                    "cruise_speed_mm_s": round(cruise * mm, 1) if cruise else None})
    return res, [(round(t, 5), p) for t, p in after]


def slope(pts):
    n = len(pts)
    mt = sum(t for t, _ in pts) / n
    mp = sum(p for _, p in pts) / n
    den = sum((t - mt) ** 2 for t, _ in pts)
    return sum((t - mt) * (p - mp) for t, p in pts) / den if den else 0.0


def ms(t):
    return round(t * 1000, 1) if t is not None else None


def run_sine(board, mover, fw, low_b, high_b, mu, cycles):
    centre, amp = (low_b + high_b) / 2, (high_b - low_b) / 2
    warm = 1.0 / mu                                        # one cycle not analysed
    total = warm + cycles / mu
    samples, cmds = [], []
    start = time.perf_counter()
    next_send = start
    while True:
        now = time.perf_counter()
        if now - start >= total:
            break
        if now >= next_send:
            b = round(centre + amp * math.sin(2 * math.pi * mu * (now - start)))
            mover.go(b)
            cmds.append((now, POT_ZERO + STEP * b))
            next_send += 1.0 / UPDATE_HZ
        s = board.recv(max(0.0, next_send - time.perf_counter()), fw)
        if s:
            samples.append(s)
    pts, offset = board_timeline(samples)
    t_start = start - offset + warm
    meas = [(t - t_start, p) for t, p in pts if t >= t_start]
    cmd = [(h - offset - t_start, p) for h, p in cmds if h - offset >= t_start]
    am, pm = fit_sine(meas, mu)
    ac, pc = fit_sine(cmd, mu)
    lag_deg = ((pc - pm) * 180 / math.pi + 180) % 360 - 180   # + = measured lags command
    errs = []
    k = 0
    for t, p in meas:                                      # error vs held setpoint
        while k + 1 < len(cmd) and cmd[k + 1][0] <= t:
            k += 1
        if cmd and cmd[k][0] <= t:
            errs.append(abs(p - cmd[k][1]))
    return {
        "mu": mu, "cycles_analysed": cycles,
        "cmd_amplitude_adc": round(ac, 1), "meas_amplitude_adc": round(am, 1),
        "amplitude_ratio": round(am / ac, 3) if ac else None,
        "phase_lag_deg": round(lag_deg, 1), "time_lag_ms": round(lag_deg / 360 / mu * 1000, 1),
        "max_tracking_error_adc": max(errs) if errs else None, "samples": len(meas),
    }


def fit_sine(pts, f):
    """Least-squares c + a·sin(wt) + b·cos(wt); returns (amplitude, phase)."""
    w = 2 * math.pi * f
    rows = [(1.0, math.sin(w * t), math.cos(w * t), p) for t, p in pts]
    m = [[sum(r[i] * r[j] for r in rows) for j in range(3)] for i in range(3)]
    v = [sum(r[i] * r[3] for r in rows) for i in range(3)]
    for i in range(3):                                     # Gauss-Jordan, 3x3
        piv = m[i][i]
        m[i] = [x / piv for x in m[i]]
        v[i] /= piv
        for k in range(3):
            if k != i:
                fac = m[k][i]
                m[k] = [a - fac * b for a, b in zip(m[k], m[i])]
                v[k] -= fac * v[i]
    _, a, b = v
    return math.hypot(a, b), math.atan2(b, a)


def check_target(name, adc, cal, ignore_safe):
    if not (REACHABLE[0] <= adc <= REACHABLE[1]):
        sys.exit(f"{name}={adc} is outside what the protocol can command [{REACHABLE[0]}, {REACHABLE[1]}].")
    if not (FW_LIMITS[0] <= adc <= FW_LIMITS[1]):
        sys.exit(f"{name}={adc} is outside the firmware window {FW_LIMITS}.")
    lo, hi = cal.get("safe_min"), cal.get("safe_max")
    if lo is not None and hi is not None and not (lo <= adc <= hi) and not ignore_safe:
        sys.exit(f"{name}={adc} is outside this motor's calibrated safe range [{lo}, {hi}] "
                 "(use --ignore-safe-range only if you know the mechanism allows it).")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("board", type=int, help="board ID 1..30")
    ap.add_argument("motor", type=int, help="host motor m1..m14 (hardware channel = motor+1)")
    ap.add_argument("mode", choices=["step", "stroke", "sine"])
    ap.add_argument("--to", type=int, help="step: target ADC")
    ap.add_argument("--low", type=int, help="stroke/sine: low edge ADC")
    ap.add_argument("--high", type=int, help="stroke/sine: high edge ADC")
    ap.add_argument("--mu", default="0.1,0.2,0.3,0.5", help="sine: cycles/s list (default 0.1,0.2,0.3,0.5)")
    ap.add_argument("--cycles", type=int, default=3, help="sine: cycles analysed per μ (default 3)")
    ap.add_argument("--u-limit", type=int, default=GUI_CONFIG["u_limit"], help="max PWM 0..255 (default 65 = GUI)")
    ap.add_argument("--min-pwm", type=int, help="default: board's calibrated value, else 50")
    ap.add_argument("--timeout", type=float, default=10.0, help="max seconds per move (default 10)")
    ap.add_argument("--mm-per-count", type=float, help="also report mm (measure once with a ruler)")
    ap.add_argument("--channel", default="can0")
    ap.add_argument("--ignore-safe-range", action="store_true")
    ap.add_argument("--no-motor", default="", help="host motors with NO motor attached, e.g. 13,14 "
                    "(they share the frame; their floating pots are then ignored)")
    a = ap.parse_args()

    if not 1 <= a.motor <= 14 or not 1 <= a.board <= 63 or not 0 <= a.u_limit <= 255:
        sys.exit("board 1..63, motor 1..14, u-limit 0..255")
    fw, slot, hw = a.motor, a.motor - 1, a.motor + 1
    cal_pwm, cal = calibration_for(a.board, hw)
    cal = cal or {}
    min_pwm = a.min_pwm if a.min_pwm is not None else (cal_pwm or 50)
    targets = {"step": [("to", a.to)], "stroke": [("low", a.low), ("high", a.high)],
               "sine": [("low", a.low), ("high", a.high)]}[a.mode]
    for name, val in targets:
        if val is None:
            sys.exit(f"{a.mode} needs --{name}")
        check_target(name, val, cal, a.ignore_safe_range)
    if a.mode != "step" and a.high <= a.low:
        sys.exit("--high must be above --low")
    mus = [float(x) for x in a.mu.split(",")] if a.mode == "sine" else []
    no_motor = {int(x.strip().lstrip("m")) for x in a.no_motor.split(",") if x.strip()}
    if a.motor in no_motor:
        sys.exit("--no-motor can't include the motor under test")

    bus = can.interface.Bus(channel=a.channel, interface="socketcan")
    board = Board(bus, a.board)
    mover = None
    try:
        # Is something else (the GUI) sending positions?
        end = time.perf_counter() + 0.3
        while time.perf_counter() < end:
            m = bus.recv(timeout=0.05)
            if m and m.arbitration_id == board.id and len(m.data) and m.data[0] in (0x01, 0x02, 0x07):
                sys.exit("Another program is sending positions to this board — close the GUI first.")

        print(f"Reading positions of board {a.board}'s 14 motors over CAN...")
        pos = {i: read_position(board, i) for i in range(1, 15)}
        if pos[fw] is None:
            sys.exit("No telemetry from the board — is it running and on the bus?")
        if not FW_LIMITS[0] <= pos[fw] <= FW_LIMITS[1]:
            sys.exit(f"m{a.motor} reads {pos[fw]}: outside {FW_LIMITS} — pot not connected?")
        park = [to_byte(pos[i]) if pos[i] is not None else 0 for i in range(1, 15)]
        half = range(0, 7) if slot < 7 else range(7, 14)
        silent = [f"m{i + 1}" for i in half if pos[i + 1] is None]
        if silent:
            sys.exit(f"No telemetry from {', '.join(silent)} — can't know where to hold them.")
        bad = [f"m{i + 1}={pos[i + 1]}" for i in half if i != slot and (i + 1) not in no_motor
               and FW_LIMITS[0] <= pos[i + 1] <= FW_LIMITS[1]
               and abs(POT_ZERO + STEP * park[i] - pos[i + 1]) > GUI_CONFIG["deadband"]]
        if bad:
            sys.exit(f"Can't hold these motors still: {', '.join(bad)} — outside the range a CAN frame can "
                     f"command [{REACHABLE[0]}, {REACHABLE[1]}], so sending would move them.\n"
                     "If those channels have no motor attached, add e.g. --no-motor 13,14")

        print(f"\n  Board {a.board}, motor m{a.motor} (firmware index {fw}, hardware channel {hw})")
        print(f"  Current position: {pos[fw]} ADC")
        if cal.get("safe_min") is not None:
            print(f"  Calibrated safe range: [{cal['safe_min']}, {cal['safe_max']}]")
        q = {n: POT_ZERO + STEP * to_byte(v) for n, v in targets}
        print(f"  Mode: {a.mode}  targets (quantised): {q}")
        if mus:
            print(f"  μ: {mus}, {a.cycles} cycles + 1 warm-up each "
                  f"(~{sum((a.cycles + 1) / mu for mu in mus):.0f} s total)")
        print(f"  Controller: u_limit {a.u_limit}, min_pwm {min_pwm}, Kp/Ki/Kd/alpha/deadband = GUI defaults")
        print("  Other motors in this frame hold their current positions"
              + (f" (no motor on: {', '.join(f'm{i}' for i in sorted(no_motor))})." if no_motor else "."))
        if input("\n  Move this motor? [y/N] ").strip().lower() != "y":
            sys.exit("Aborted.")

        cfg = dict(GUI_CONFIG, u_limit=a.u_limit)
        board.config(**cfg, min_pwm=min_pwm)
        mover = Mover(board, slot, park)
        board.stream(fw)
        mm = a.mm_per_count
        results = []
        if a.mode == "step":
            plan = [("move", to_byte(a.to))]
        elif a.mode == "stroke":
            plan = [("to low (setup)", to_byte(a.low)), ("low->high", to_byte(a.high)),
                    ("high->low", to_byte(a.low))]
        else:
            plan = [("to centre (setup)", round((to_byte(a.low) + to_byte(a.high)) / 2))]
        for name, b in plan:
            print(f"\n{name}: -> {POT_ZERO + STEP * b} ADC")
            samples, t_cmd, target = record_move(board, mover, fw, b, cfg["deadband"], a.timeout)
            sat_err = cfg["u_limit"] / (cfg["kp"] / 255)     # error above which PID output = u_limit
            res, trace = analyse_move(samples, t_cmd, target, cfg["deadband"], sat_err, mm)
            res["name"] = name
            for k, v in res.items():
                if k != "name":
                    print(f"  {k:28s} {v}")
            results.append(dict(res, trace=trace))
        for mu in mus:
            print(f"\nsine μ={mu} cycles/s ...")
            res = run_sine(board, mover, fw, to_byte(a.low), to_byte(a.high), mu, a.cycles)
            for k, v in res.items():
                print(f"  {k:28s} {v}")
            results.append(res)

        os.makedirs(OUT_DIR, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(OUT_DIR, f"motion_{a.mode}_b{a.board}_m{a.motor}_{stamp}.json")
        with open(path, "w") as f:
            json.dump({"timestamp": stamp, "board": a.board, "motor": a.motor, "hw_channel": hw,
                       "mode": a.mode, "u_limit": a.u_limit, "min_pwm": min_pwm,
                       "notes": "positions = pot_filtered ADC counts; times from the board clock; "
                                "times from the command include its CAN+USB delay (~1-2 ms); speed windows are 25 ms",
                       "results": results}, f, indent=1)
        print(f"\nSaved {path}")
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        try:
            if mover is not None:                          # hold wherever it is now
                now = read_position(board, fw, n=10)
                if now is not None:
                    mover.go(to_byte(now))
                board.config(**GUI_CONFIG, min_pwm=min_pwm)
                print("Motor holding; board config set to GUI defaults (u_limit 65).")
            board.stop_stream()
        finally:
            bus.shutdown()


if __name__ == "__main__":
    main()
