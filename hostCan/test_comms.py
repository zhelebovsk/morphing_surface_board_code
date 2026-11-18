"""
CAN communication bench test, for any number of connected boards (1..BOARD_COUNT).

1. Scans for boards and lists which answer.
2. Runs CYCLES back-to-back position send cycles and times them.
   - Default (full-fleet load): sends to every board slot 1..BOARD_COUNT, connected or not,
     to measure bus timing as if the whole fleet were present. Frames for absent boards are
     still ACKed by any connected board, so this works with as few as one board.
   - --present-only: sends only to the boards that answered, like the GUI does.
3. Checks that every frame reached the bus, that no bus errors occurred, and that every
   board that answered before the run still answers after it.

Connected boards' motors move to mid-range (position byte 127, scaled by the default
min limit) during the run.

Usage:
    python3 test_comms.py [can_channel] [--cycles N] [--present-only]
Exit code 0 = pass, 1 = fail.
"""

import argparse
import json
import subprocess
import sys
import time

from communication import MotorCommunication, can_search, read_tx_packets
from config import BOARD_COUNT, MOTORS_PER_BOARD, DEFAULT_MIN_LIMIT, UPDATE_HZ

MID_VALUE = 127   # neutral motor position (0–255)


def read_bus_stats(channel):
    """(state, bus_error count) from `ip`, or (None, None) if unavailable."""
    try:
        out = subprocess.run(["ip", "-j", "-d", "-s", "link", "show", channel],
                             capture_output=True, text=True, timeout=1.0).stdout
        linkinfo = json.loads(out)[0]["linkinfo"]
        return linkinfo["info_data"].get("state"), linkinfo["info_xstats"].get("bus_error")
    except (OSError, subprocess.SubprocessError, ValueError, LookupError, TypeError):
        return None, None


def pick_channel(requested):
    if requested:
        return requested
    real = [c for c in can_search() if c != "DEMO-MODE"]
    if real:
        print(f"Using channel: {real[0]}")
        return real[0]
    print("No CAN interface found, running in DEMO-MODE")
    return "DEMO-MODE"


def main():
    parser = argparse.ArgumentParser(description="CAN communication bench test")
    parser.add_argument("channel", nargs="?", help="CAN interface, e.g. can0")
    parser.add_argument("--cycles", type=int, default=200, help="send cycles (default 200)")
    parser.add_argument("--present-only", action="store_true",
                        help="send only to boards that answered (default: all slots)")
    args = parser.parse_args()

    channel = pick_channel(args.channel)
    min_limits = [[DEFAULT_MIN_LIMIT] * MOTORS_PER_BOARD for _ in range(BOARD_COUNT)]
    comm = MotorCommunication(channel, min_limits)
    try:
        return run(comm, channel, args)
    finally:
        if comm.bus is not None:
            comm.bus.shutdown()


def run(comm, channel, args):
    # --- scan ---
    print(f"\nScanning boards 1..{BOARD_COUNT}...")
    found = comm.scan_boards(BOARD_COUNT, timeout=0.5)
    missing = [b for b in range(1, BOARD_COUNT + 1) if b not in found]
    print(f"  Responding ({len(found)}): {found}")
    print(f"  Missing    ({len(missing)}): {missing}")
    if not found:
        print("\nFAIL: no board answered — nothing to test. Check power, cable, and that no"
              " debugger is holding a board halted.")
        return 1

    targets = sorted(found) if args.present_only else list(range(1, BOARD_COUNT + 1))
    mode = "present boards only" if args.present_only else f"all {BOARD_COUNT} slots (full-fleet load)"
    frames_per_board = 1 if comm.fd else 2
    print(f"\nMode: {mode}, {'CAN FD' if comm.fd else 'classic CAN'}, "
          f"{frames_per_board} frame(s) per board per cycle")

    # send_positions skips boards not in active_boards; set it to the slots under test.
    comm.active_boards = set(targets)
    locations = [[MID_VALUE] * MOTORS_PER_BOARD for _ in range(BOARD_COUNT)]

    # --- send loop ---
    print(f"Running {args.cycles} send cycles...")
    tx_before = read_tx_packets(channel)
    _, bus_err_before = read_bus_stats(channel)
    errors = 0
    times_ms = []
    for i in range(args.cycles):
        t0 = time.perf_counter()
        try:
            comm.send_positions(locations)
        except Exception as e:
            errors += 1
            print(f"  cycle {i}: error — {e}")
        times_ms.append((time.perf_counter() - t0) * 1000.0)

    # send_positions returns once frames are queued; let the queue drain before counting.
    time.sleep(1.0)
    tx_after = read_tx_packets(channel)
    state, bus_err_after = read_bus_stats(channel)

    # --- did every board survive the run? ---
    still_there = comm.scan_boards(BOARD_COUNT, timeout=0.5)
    lost = [b for b in found if b not in still_there]
    appeared = [b for b in still_there if b not in found]

    # --- report ---
    budget_ms = 1000.0 / UPDATE_HZ
    avg, peak = sum(times_ms) / len(times_ms), max(times_ms)
    print(f"\nResults over {args.cycles} cycles ({len(targets)} board slots):")
    print(f"  avg  send time:      {avg:.2f} ms  (cycle budget {budget_ms:.1f} ms at {UPDATE_HZ:.0f} Hz)")
    print(f"  peak send time:      {peak:.2f} ms")
    print(f"  over-budget cycles:  {sum(1 for t in times_ms if t > budget_ms)}")
    print(f"  send errors:         {errors}")

    problems = []
    if tx_before is not None and tx_after is not None:
        expected = args.cycles * len(targets) * frames_per_board
        sent = tx_after - tx_before
        print(f"  frames on the bus:   {sent} of {expected}")
        if sent < expected:
            problems.append("frames were queued but not all reached the bus")
    if bus_err_before is not None and bus_err_after is not None:
        print(f"  new bus errors:      {bus_err_after - bus_err_before}   (state {state})")
        if bus_err_after > bus_err_before:
            problems.append("bus errors during the run")
    print(f"  boards after run:    {len(still_there)} answering"
          + (f", lost {lost}" if lost else "")
          + (f", newly appeared {appeared}" if appeared else ""))
    if lost:
        problems.append(f"board(s) {lost} stopped answering")
    if errors:
        problems.append("send errors")

    if problems:
        print("\nFAIL: " + "; ".join(problems) + ".")
        print("  Details: ip -details -statistics link show " + channel)
        return 1
    if peak > budget_ms:
        print("\nWARNING: peak send time exceeded the cycle budget — bus may be saturated.")
    else:
        print("\nOK: all frames sent, no bus errors, all boards still answering.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
