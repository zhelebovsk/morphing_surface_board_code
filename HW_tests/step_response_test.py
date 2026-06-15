"""
step_response_test.py — Closed-loop step response characterisation.

Purpose:
  Commands one motor to jump from its current position to a new target.
  The board streams pot_raw + pot_filtered back over CAN at 100 Hz so the
  control loop runs uninterrupted (no OpenOCD halts during recording).

  !! SAFETY !!
  MAX_STEP_COUNTS = 100 ADC counts hard cap.
  You must confirm before anything moves.

Setup:
  1. Flash and run firmware (must include CAN streaming — command 0x04/0x05).
  2. Start the CAN interface:  ./can_start.sh
  3. Make sure the Python GUI is NOT running.
  4. Connect ST-LINK (only needed to read initial position).
  5. Run:
       python3 step_response_test.py [board_id] [active_motor_idx] [step_delta]

     board_id          : 1-30
     active_motor_idx  : 0-13  (maps to firmware active_motors[i] = i+1)
     step_delta        : ADC counts to step (default 70, max 100)
                         Positive = up, negative = down.

Output:
  results/step_board{B}_motor{M}_deltaD.json
"""

import json
import math
import os
import sys
import time
from datetime import datetime

import can

from common import ELF_PATH, OpenOCDProcess, OpenOCDTelnet, get_symbol_address

# ── Config ────────────────────────────────────────────────────────────────────

BOARD_ID         = int(sys.argv[1]) if len(sys.argv) > 1 else 1
ACTIVE_MOTOR_IDX = int(sys.argv[2]) if len(sys.argv) > 2 else 0
STEP_DELTA_ADC   = int(sys.argv[3]) if len(sys.argv) > 3 else 70

MAX_STEP_COUNTS  = 100
STREAM_INTERVAL_MS = 10   # 100 Hz streaming from board
POLL_DURATION_S  = 5.0
CAN_CHANNEL      = "can0"
OUTPUT_DIR       = "results"

LOCATION_MULTIPLIER = 7
POT_ZERO            = 1048
LO_LIMIT            = 680
HI_LIMIT            = 3415
MOTOR_AMOUNT        = 16
ACTIVE_MOTORS       = list(range(1, 15))

# ── Helpers ───────────────────────────────────────────────────────────────────

def active_motor_id(idx):
    return ACTIVE_MOTORS[idx]

def desired_to_can_value(desired_pos):
    return max(0, min(255, int(round((desired_pos - POT_ZERO) / LOCATION_MULTIPLIER))))

def pot_to_can(pot):
    return max(0, min(255, round((pot - POT_ZERO) / LOCATION_MULTIPLIER)))

def build_can_frames(all_can_values, test_active_idx, test_value):
    vals = list(all_can_values)
    vals[test_active_idx] = test_value
    return bytes([0x01] + vals[0:7]), bytes([0x02] + vals[7:14])

def parse_stream_frame(msg):
    """Parse a 0xA0 streaming frame. Returns (motor_id, raw, filtered, ts_us) or None."""
    if len(msg.data) < 8 or msg.data[0] != 0xA0:
        return None
    motor_id = msg.data[1]
    raw      = msg.data[2] | (msg.data[3] << 8)
    filt_raw = msg.data[4] | (msg.data[5] << 8)
    filt     = filt_raw if filt_raw < 32768 else filt_raw - 65536
    ts       = msg.data[6] | (msg.data[7] << 8)
    return motor_id, raw, filt, ts

def fit_first_order(times, values, initial, final):
    span = initial - final
    if abs(span) < 1e-6:
        return None, None, None

    noise = 5
    t0 = times[-1]
    for t, v in zip(times, values):
        if abs(v - initial) > noise:
            t0 = t
            break

    valid_t, valid_ln = [], []
    for t, v in zip(times, values):
        if t < t0:
            continue
        ratio = (v - final) / span
        if ratio > 0.01:
            valid_t.append(t - t0)
            valid_ln.append(math.log(ratio))

    if len(valid_t) < 3:
        return None, None, None

    n     = len(valid_t)
    sx    = sum(valid_t)
    sy    = sum(valid_ln)
    sxy   = sum(valid_t[i] * valid_ln[i] for i in range(n))
    sxx   = sum(x ** 2 for x in valid_t)
    denom = n * sxx - sx * sx
    if abs(denom) < 1e-12:
        return None, None, None

    slope = (n * sxy - sx * sy) / denom
    tau   = -1.0 / slope if slope != 0 else None

    residuals = []
    for t, v in zip(times, values):
        t_rel = max(0.0, t - t0)
        predicted = final + span * math.exp(-t_rel / tau) if tau else final
        residuals.append(v - predicted)

    return tau, t0, residuals

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    step_delta = STEP_DELTA_ADC
    if abs(step_delta) > MAX_STEP_COUNTS:
        print(f"WARNING: clamping step from {step_delta} to ±{MAX_STEP_COUNTS}")
        step_delta = MAX_STEP_COUNTS if step_delta > 0 else -MAX_STEP_COUNTS

    motor_id = active_motor_id(ACTIVE_MOTOR_IDX)
    can_id   = 0x100 + BOARD_ID
    print(f"Step response — board {BOARD_ID}, active_motor[{ACTIVE_MOTOR_IDX}] "
          f"(motor_id={motor_id}), step = {step_delta:+d} ADC counts\n")

    # ── Open CAN ─────────────────────────────────────────────────────────────
    try:
        bus = can.interface.Bus(channel=CAN_CHANNEL, interface="socketcan")
    except OSError as e:
        print(f"ERROR opening CAN: {e}\nRun ./can_start.sh first.")
        sys.exit(1)

    # ── Read initial state via OpenOCD ────────────────────────────────────────
    pot_addr     = get_symbol_address(ELF_PATH, "pot_raw")
    desired_addr = get_symbol_address(ELF_PATH, "desired_position")

    with OpenOCDProcess():
        ocd = OpenOCDTelnet()
        ocd.halt()
        initial_pos   = ocd.read_uint16_array(pot_addr + motor_id * 2, 1)[0]
        desired_array = ocd.read_uint16_array(desired_addr, MOTOR_AMOUNT)
        pots_all      = ocd.read_uint16_array(pot_addr, MOTOR_AMOUNT)
        ocd.resume()
        ocd.close()

    target_adc = initial_pos + step_delta
    target_can = max(0, min(255, round((target_adc - POT_ZERO) / LOCATION_MULTIPLIER)))

    if not (LO_LIMIT <= target_adc <= HI_LIMIT):
        print(f"SAFETY ABORT: target {target_adc} outside [{LO_LIMIT}, {HI_LIMIT}].")
        bus.shutdown()
        sys.exit(1)

    print(f"  Current position : {initial_pos} ADC counts")
    print(f"  Target position  : {target_adc} ADC counts  ({step_delta:+d})")
    print(f"  Movement         : ~{abs(step_delta) * 3300 / 4096:.0f} mV on pot")
    print()
    answer = input("  Move this motor? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        bus.shutdown()
        sys.exit(0)

    # Park all other motors at their current pot position
    park_vals = [pot_to_can(pots_all[mid]) for mid in ACTIVE_MOTORS]
    data1, data2 = build_can_frames(park_vals, ACTIVE_MOTOR_IDX, target_can)

    # Start streaming BEFORE sending the step so we catch t=0
    stream_cmd = bytes([0x04, motor_id, STREAM_INTERVAL_MS, 0, 0, 0, 0, 0])
    bus.send(can.Message(arbitration_id=can_id, data=stream_cmd, is_extended_id=False))
    time.sleep(0.05)  # let first stream frames arrive

    # Send step command
    bus.send(can.Message(arbitration_id=can_id, data=data1, is_extended_id=False))
    bus.send(can.Message(arbitration_id=can_id, data=data2, is_extended_id=False))
    t_step = time.perf_counter()
    print("Step sent. Recording via CAN stream...\n")

    # ── Receive streaming frames ──────────────────────────────────────────────
    raw_samples  = []
    filt_samples = []
    timestamps   = []

    bus.set_filters([{"can_id": can_id, "can_mask": 0x7FF, "extended": False}])

    while time.perf_counter() - t_step < POLL_DURATION_S:
        msg = bus.recv(timeout=0.1)
        if msg is None:
            continue
        parsed = parse_stream_frame(msg)
        if parsed is None or parsed[0] != motor_id:
            continue
        _, raw, filt, _ = parsed
        t = time.perf_counter() - t_step
        raw_samples.append(raw)
        filt_samples.append(filt)
        timestamps.append(round(t, 4))

    # Stop streaming
    bus.send(can.Message(arbitration_id=can_id,
                         data=bytes([0x05, 0, 0, 0, 0, 0, 0, 0]),
                         is_extended_id=False))
    bus.shutdown()

    if len(timestamps) < 5:
        print("ERROR: no stream frames received. Check firmware version and CAN.")
        sys.exit(1)

    actual_hz = len(timestamps) / timestamps[-1]
    print(f"Received {len(timestamps)} samples @ {actual_hz:.1f} Hz")

    tail      = raw_samples[int(len(raw_samples) * 0.8):]
    final_pos = sum(tail) / len(tail)
    actual_step_adc = final_pos - initial_pos

    tau, dead_time, residuals = fit_first_order(timestamps, raw_samples, initial_pos, final_pos)
    if tau:
        Q_estimate = sum(r ** 2 for r in residuals) / len(residuals)
        print(f"Dead time (stiction): {dead_time * 1000:.0f} ms")
        print(f"Time constant τ:      {tau * 1000:.1f} ms")
        print(f"Step commanded:       {step_delta:+d} ADC counts")
        print(f"Step actual:          {actual_step_adc:+.1f} ADC counts")
        print(f"Residual variance Q:  {Q_estimate:.2f}")
    else:
        dead_time = Q_estimate = None
        print("Could not fit — motor may not have moved enough.")

    results = {
        "timestamp":        datetime.now().isoformat(),
        "board_id":         BOARD_ID,
        "active_motor_idx": ACTIVE_MOTOR_IDX,
        "motor_id":         motor_id,
        "step_delta_adc":   step_delta,
        "target_adc":       target_adc,
        "initial_adc":      int(initial_pos),
        "final_adc_mean":   round(final_pos, 1),
        "actual_step_adc":  round(actual_step_adc, 1),
        "sample_hz":        round(actual_hz, 1),
        "fit": {
            "dead_time_ms":        round(dead_time * 1000, 1) if dead_time else None,
            "tau_s":               round(tau, 4) if tau else None,
            "tau_ms":              round(tau * 1000, 2) if tau else None,
            "Q_residual_variance": round(Q_estimate, 4) if Q_estimate else None,
        },
        "raw_samples":  raw_samples,
        "filt_samples": filt_samples,
        "timestamps_s": timestamps,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR,
        f"step_board{BOARD_ID}_motor{ACTIVE_MOTOR_IDX}_delta{step_delta:+d}.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nSaved to {out_path}")
    print("Run  python3 kalman_params.py  to compute Kalman filter parameters.")


if __name__ == "__main__":
    main()
