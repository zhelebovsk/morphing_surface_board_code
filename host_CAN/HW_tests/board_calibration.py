"""
board_calibration.py — Full-board motor calibration.

For each connected motor on a board:
  1. Detects if motor is physically connected (pot in safe ADC range).
  2. Binary-searches for the minimum min_pwm that overcomes stiction.
  3. Runs a clean step response at that min_pwm.
  4. Alternates step direction (+/-) so the motor stays near its start position.

At the end prints a per-motor summary and recommends a global min_pwm for the board.

Usage:
  python3 board_calibration.py [board_id]   (default board_id=1)

Requirements:
  - Firmware with CAN streaming (0x04/0x05) and min_pwm config (0x03 byte 7).
  - CAN interface up  (./can_start.sh).
  - ST-LINK connected.
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
CAN_CHANNEL      = "can0"
OUTPUT_DIR       = "results"

STEP_SIZE_ADC    = 60       # ADC counts per step (small but detectable)
STEP_TIMEOUT_S   = 4.0      # how long to record each step response
SETTLE_S         = 1.5      # wait after each step before next test
STREAM_MS        = 10       # 100 Hz streaming

# min_pwm search range
MIN_PWM_LOW      = 20
MIN_PWM_HIGH     = 90
MIN_PWM_STEP     = 10       # coarse first pass

MOVEMENT_THRESH  = 10       # ADC counts — motor must move at least this much
LO_LIMIT         = 680
HI_LIMIT         = 3415

LOCATION_MUL     = 7
POT_ZERO         = 1048
MOTOR_AMOUNT     = 16
ACTIVE_MOTORS    = list(range(1, 15))   # motor_ids 1-14

# Kp=0.2→51, Ki=0.1→26, Kd=0, alpha=0.2→51, u_limit=100, deadband=10
BASE_CONFIG      = [51, 26, 0, 51, 100, 10]

# ── Helpers ───────────────────────────────────────────────────────────────────

def pot_to_can(pot):
    return max(0, min(255, round((pot - POT_ZERO) / LOCATION_MUL)))

def build_frames(park_vals, active_idx, target_can):
    vals = list(park_vals)
    vals[active_idx] = target_can
    return bytes([0x01] + vals[0:7]), bytes([0x02] + vals[7:14])

def send_config(bus, can_id, min_pwm):
    data = bytes([0x03] + BASE_CONFIG + [min_pwm])
    bus.send(can.Message(arbitration_id=can_id, data=data, is_extended_id=False))

def send_step(bus, can_id, park_vals, active_idx, target_can):
    d1, d2 = build_frames(park_vals, active_idx, target_can)
    bus.send(can.Message(arbitration_id=can_id, data=d1, is_extended_id=False))
    bus.send(can.Message(arbitration_id=can_id, data=d2, is_extended_id=False))

def parse_stream(msg, motor_id):
    if len(msg.data) < 8 or msg.data[0] != 0xA0 or msg.data[1] != motor_id:
        return None
    raw  = msg.data[2] | (msg.data[3] << 8)
    filt_u = msg.data[4] | (msg.data[5] << 8)
    filt = filt_u if filt_u < 32768 else filt_u - 65536
    return raw, filt

def record_step(bus, can_id, motor_id, duration_s):
    """Collect CAN stream frames for duration_s. Returns (raw_list, time_list)."""
    bus.set_filters([{"can_id": can_id, "can_mask": 0x7FF, "extended": False}])
    raws, times = [], []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < duration_s:
        msg = bus.recv(timeout=0.05)
        if msg is None:
            continue
        parsed = parse_stream(msg, motor_id)
        if parsed:
            raws.append(parsed[0])
            times.append(round(time.perf_counter() - t0, 4))
    return raws, times

def movement(raws, initial):
    if not raws:
        return 0
    tail = raws[int(len(raws) * 0.7):]
    return abs(sum(tail) / len(tail) - initial)

def fit_tau(times, raws, initial, final):
    span = initial - final
    if abs(span) < 1:
        return None
    noise, t0 = 5, 0.0
    for t, v in zip(times, raws):
        if abs(v - initial) > noise:
            t0 = t
            break
    pts = [(t - t0, math.log((v - final) / span))
           for t, v in zip(times, raws)
           if t >= t0 and (v - final) / span > 0.01]
    if len(pts) < 3:
        return None
    n   = len(pts)
    sx  = sum(p[0] for p in pts)
    sy  = sum(p[1] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts)
    d   = n * sxx - sx * sx
    return -1.0 / ((n * sxy - sx * sy) / d) if abs(d) > 1e-12 else None

# ── Per-motor test ─────────────────────────────────────────────────────────────

def test_motor(bus, can_id, active_idx, initial_pot, park_vals, direction):
    """
    Try increasing min_pwm values until the motor moves.
    Returns dict with results, or None if motor never moved.
    direction: +1 or -1
    """
    motor_id   = ACTIVE_MOTORS[active_idx]
    step_delta = direction * STEP_SIZE_ADC
    target_adc = initial_pot + step_delta
    target_can = pot_to_can(target_adc)

    if not (LO_LIMIT <= target_adc <= HI_LIMIT):
        # Flip direction if out of range
        step_delta  = -step_delta
        target_adc  = initial_pot + step_delta
        target_can  = pot_to_can(target_adc)

    # Start streaming
    bus.send(can.Message(arbitration_id=can_id,
             data=bytes([0x04, motor_id, STREAM_MS, 0, 0, 0, 0, 0]),
             is_extended_id=False))
    time.sleep(0.05)

    best = None
    for min_pwm in range(MIN_PWM_LOW, MIN_PWM_HIGH + 1, MIN_PWM_STEP):
        send_config(bus, can_id, min_pwm)
        time.sleep(0.02)

        send_step(bus, can_id, park_vals, active_idx, target_can)
        raws, times = record_step(bus, can_id, motor_id, STEP_TIMEOUT_S)

        moved = movement(raws, initial_pot)
        print(f"    min_pwm={min_pwm:3d}  moved={moved:.0f} ADC counts", end="")

        if moved >= MOVEMENT_THRESH:
            tail     = raws[int(len(raws) * 0.7):]
            final    = sum(tail) / len(tail)
            overshoot = final - (initial_pot + step_delta)
            tau      = fit_tau(times, raws, initial_pot, final)
            print(f"  τ={tau*1000:.0f}ms  overshoot={overshoot:+.0f}" if tau else "  ✓")
            best = {
                "min_pwm":     min_pwm,
                "tau_ms":      round(tau * 1000, 1) if tau else None,
                "step_delta":  step_delta,
                "actual_step": round(final - initial_pot, 1),
                "overshoot":   round(overshoot, 1),
            }
            break
        else:
            print("  — no movement")

        # Return motor to initial position before next attempt
        return_can = pot_to_can(initial_pot)
        send_step(bus, can_id, park_vals, active_idx, return_can)
        time.sleep(SETTLE_S)

    # Stop streaming
    bus.send(can.Message(arbitration_id=can_id,
             data=bytes([0x05, 0, 0, 0, 0, 0, 0, 0]),
             is_extended_id=False))

    # Return to initial after successful step
    if best:
        return_can = pot_to_can(initial_pot)
        send_config(bus, can_id, 50)   # restore default min_pwm
        send_step(bus, can_id, park_vals, active_idx, return_can)
        time.sleep(SETTLE_S)

    return best

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    can_id = 0x100 + BOARD_ID
    print(f"Board calibration — board {BOARD_ID}")
    print(f"CAN: {CAN_CHANNEL}  |  step size: {STEP_SIZE_ADC} ADC counts\n")

    try:
        bus = can.interface.Bus(channel=CAN_CHANNEL, interface="socketcan")
    except OSError as e:
        print(f"ERROR opening CAN: {e}\nRun ./can_start.sh first.")
        sys.exit(1)

    # ── Read all pot values + desired positions via OpenOCD ───────────────────
    pot_addr     = get_symbol_address(ELF_PATH, "pot_raw")
    desired_addr = get_symbol_address(ELF_PATH, "desired_position")

    print("Reading pot values via OpenOCD...")
    with OpenOCDProcess():
        ocd = OpenOCDTelnet()
        ocd.halt()
        pots    = ocd.read_uint16_array(pot_addr, MOTOR_AMOUNT)
        desired = ocd.read_uint16_array(desired_addr, MOTOR_AMOUNT)
        ocd.resume()
        ocd.close()

    # Park all motors at current pot position
    park_vals = [pot_to_can(pots[mid]) for mid in ACTIVE_MOTORS]
    d1 = bytes([0x01] + park_vals[0:7])
    d2 = bytes([0x02] + park_vals[7:14])
    bus.send(can.Message(arbitration_id=can_id, data=d1, is_extended_id=False))
    bus.send(can.Message(arbitration_id=can_id, data=d2, is_extended_id=False))
    time.sleep(0.2)

    # ── Find connected motors ─────────────────────────────────────────────────
    connected = []
    print(f"{'Motor':>6}  {'hw ch':>5}  {'pot':>6}  {'status'}")
    print("-" * 40)
    for active_idx, motor_id in enumerate(ACTIVE_MOTORS):
        pot = pots[motor_id]
        if LO_LIMIT <= pot <= HI_LIMIT:
            status = "CONNECTED"
            connected.append(active_idx)
        else:
            status = "not connected"
        print(f"  [{active_idx:2d}]  ch {motor_id+1:2d}   {pot:5d}  {status}")

    if not connected:
        print("\nNo connected motors found. Check wiring.")
        bus.shutdown()
        sys.exit(1)

    print(f"\nFound {len(connected)} connected motor(s): "
          f"{[ACTIVE_MOTORS[i]+1 for i in connected]} (hw channels)\n")

    answer = input("Start calibration? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        bus.shutdown()
        sys.exit(0)

    # ── Test each connected motor ─────────────────────────────────────────────
    results = {}
    direction = 1   # alternate +/- to keep motors in range

    for active_idx in connected:
        motor_id = ACTIVE_MOTORS[active_idx]
        pot      = pots[motor_id]
        print(f"\n── Motor {motor_id+1} (hw ch {motor_id+1}, active_idx={active_idx}) "
              f"── pot={pot} ──")

        result = test_motor(bus, can_id, active_idx, pot, park_vals, direction)
        direction *= -1   # flip for next motor

        if result:
            results[motor_id] = result
            print(f"  → min_pwm={result['min_pwm']}  "
                  f"τ={result['tau_ms']}ms  "
                  f"overshoot={result['overshoot']:+.0f}")
        else:
            results[motor_id] = None
            print(f"  → Motor did not respond up to min_pwm={MIN_PWM_HIGH}")

    bus.shutdown()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("CALIBRATION SUMMARY")
    print("=" * 50)
    print(f"{'hw ch':>6}  {'min_pwm':>8}  {'τ (ms)':>8}  {'overshoot':>10}")
    print("-" * 40)

    working = {mid: r for mid, r in results.items() if r}
    for motor_id, r in results.items():
        if r:
            print(f"  ch {motor_id+1:2d}   {r['min_pwm']:8d}  "
                  f"{str(r['tau_ms']):>8}  {r['overshoot']:>+10.0f}")
        else:
            print(f"  ch {motor_id+1:2d}   {'—':>8}  {'—':>8}  {'no response':>10}")

    if working:
        recommended = max(r["min_pwm"] for r in working.values())
        taus = [r["tau_ms"] for r in working.values() if r["tau_ms"]]
        print(f"\nRecommended global min_pwm : {recommended}")
        if taus:
            print(f"Average τ                  : {sum(taus)/len(taus):.0f} ms")
        print(f"\nTo set on all boards:")
        print(f"  data = bytes([0x03, 51, 26, 0, 51, 100, 10, {recommended}])")
        print(f"  for board_id in range(1, 31):")
        print(f"      bus.send(can.Message(arbitration_id=0x100+board_id, "
              f"data=data, is_extended_id=False))")

    # Save
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out = {
        "timestamp":    datetime.now().isoformat(),
        "board_id":     BOARD_ID,
        "step_size_adc": STEP_SIZE_ADC,
        "motors":       {str(k+1): v for k, v in results.items()},
        "recommended_min_pwm": recommended if working else None,
    }
    out_path = os.path.join(OUTPUT_DIR, f"calibration_board{BOARD_ID}.json")
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
