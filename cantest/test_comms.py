"""
Single-board communication test.
Runs the full 30-board send loop with 1 real board connected.
The 29 frames for non-existent boards are ACKed by the real board in hardware.
Reports: which board responded, cycle timing, and any send errors.

Usage:
    python test_comms.py [can_channel]   e.g.  python test_comms.py can0
"""

import sys
import time
from communication import MotorCommunication, can_search
from config import BOARD_COUNT, MOTORS_PER_BOARD, DEFAULT_MIN_LIMIT, MOTOR_RANGE

CYCLES      = 200          # how many send cycles to run
MID_VALUE   = 127          # neutral motor position (0–255)

def main():
    channels = can_search()
    real_channels = [c for c in channels if c != "DEMO-MODE"]

    if len(sys.argv) > 1:
        channel = sys.argv[1]
    elif real_channels:
        channel = real_channels[0]
        print(f"Using channel: {channel}")
    else:
        print("No CAN interface found, running in DEMO-MODE")
        channel = "DEMO-MODE"

    min_limits = [[DEFAULT_MIN_LIMIT] * MOTORS_PER_BOARD for _ in range(BOARD_COUNT)]
    comm = MotorCommunication(channel, min_limits)

    # --- scan ---
    print(f"\nScanning for boards (expecting 1 of {BOARD_COUNT})...")
    found = comm.scan_boards(BOARD_COUNT, timeout=0.5)
    missing = [i for i in range(1, BOARD_COUNT + 1) if i not in found]
    print(f"  Responding: {found}")
    print(f"  Missing:    {missing}\n")

    # This test intentionally hammers all 30 board slots regardless of who
    # actually answered, to measure real full-fleet bus timing — override
    # communication.py's normal "skip boards we know are absent" behavior.
    comm.active_boards = set(range(1, BOARD_COUNT + 1))

    # --- build neutral locations ---
    locations = [[MID_VALUE] * MOTORS_PER_BOARD for _ in range(BOARD_COUNT)]

    # --- send loop ---
    print(f"Running {CYCLES} send cycles at full 30-board rate...")
    errors      = 0
    times_ms    = []

    for i in range(CYCLES):
        t0 = time.perf_counter()
        try:
            comm.send_positions(locations)
        except Exception as e:
            errors += 1
            print(f"  cycle {i}: error — {e}")
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        times_ms.append(elapsed_ms)

    # --- report ---
    avg  = sum(times_ms) / len(times_ms)
    peak = max(times_ms)
    budget_ms = 10.0   # 100 Hz cycle budget

    print(f"\nResults over {CYCLES} cycles:")
    print(f"  avg  send_positions: {avg:.2f} ms  (budget {budget_ms:.1f} ms)")
    print(f"  peak send_positions: {peak:.2f} ms")
    print(f"  over-budget cycles:  {sum(1 for t in times_ms if t > budget_ms)}")
    print(f"  send errors:         {errors}")

    if peak > budget_ms:
        print("\nWARNING: peak exceeded cycle budget — bus may be saturated.")
    else:
        print("\nOK: all cycles within budget.")

if __name__ == "__main__":
    main()
