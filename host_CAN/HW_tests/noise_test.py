"""
noise_test.py — Stationary pot noise characterisation.

Purpose:
  Records pot_raw and pot_filtered for one motor while it is HELD STILL
  (no CAN commands should be arriving during this test).
  The variance of pot_raw gives the measurement noise R for the Kalman filter.

Setup:
  1. Flash and run firmware on the board.
  2. Do NOT run the Python GUI or any CAN sender — motor must be stationary.
  3. Connect ST-LINK.
  4. Run:  python noise_test.py [motor_id]

Output:
  results/noise_motorX.json   — raw samples + statistics

motor_id: physical motor index 0-15 (active motors are 1-14).
"""

import json
import os
import sys
import time
from datetime import datetime

from common import ELF_PATH, OpenOCDProcess, OpenOCDTelnet, get_symbol_address

# ── Config ────────────────────────────────────────────────────────────────────

MOTOR_ID    = int(sys.argv[1]) if len(sys.argv) > 1 else 1   # default motor 1
N_SAMPLES   = 500        # number of halt-read-resume cycles
OUTPUT_DIR  = "results"

# ── Stats helpers ─────────────────────────────────────────────────────────────

def mean(xs):
    return sum(xs) / len(xs)

def variance(xs):
    m = mean(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)

def lag1_autocorr(xs):
    m = mean(xs)
    denom = sum((x - m) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    numer = sum((xs[i] - m) * (xs[i - 1] - m) for i in range(1, len(xs)))
    return numer / denom

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not os.path.exists(ELF_PATH):
        print(f"ERROR: ELF not found at {ELF_PATH}. Build firmware first.")
        sys.exit(1)

    if not (0 <= MOTOR_ID <= 15):
        print("ERROR: motor_id must be 0-15.")
        sys.exit(1)

    print(f"Noise test — motor {MOTOR_ID}, {N_SAMPLES} samples")
    print("Make sure NO CAN commands are running. Motor must be stationary.\n")

    raw_addr  = get_symbol_address(ELF_PATH, "pot_raw")
    filt_addr = get_symbol_address(ELF_PATH, "pot_filtered")
    if raw_addr is None or filt_addr is None:
        print("ERROR: could not find pot_raw or pot_filtered in ELF.")
        sys.exit(1)

    # Each element: uint16 = 2 bytes, float = 4 bytes
    motor_raw_addr  = raw_addr  + MOTOR_ID * 2
    motor_filt_addr = filt_addr + MOTOR_ID * 4

    raw_samples      = []
    filtered_samples = []
    timestamps       = []

    with OpenOCDProcess():
        ocd = OpenOCDTelnet()
        t_start = time.perf_counter()

        for i in range(N_SAMPLES):
            ocd.halt()
            raw  = ocd.read_uint16(motor_raw_addr)
            filt = ocd.read_float(motor_filt_addr)
            ocd.resume()

            t = time.perf_counter() - t_start
            if raw is not None:
                raw_samples.append(raw)
                filtered_samples.append(filt)
                timestamps.append(round(t, 6))

            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{N_SAMPLES}  raw={raw}  filt={filt:.1f}")

        ocd.close()

    elapsed = timestamps[-1] if timestamps else 0
    actual_hz = len(raw_samples) / elapsed if elapsed > 0 else 0

    R   = variance(raw_samples)
    std = R ** 0.5

    results = {
        "timestamp":   datetime.now().isoformat(),
        "motor_id":    MOTOR_ID,
        "n_samples":   len(raw_samples),
        "duration_s":  round(elapsed, 3),
        "sample_hz":   round(actual_hz, 1),
        "statistics": {
            "mean_raw":        round(mean(raw_samples), 2),
            "variance_R":      round(R, 4),
            "std_dev":         round(std, 4),
            "lag1_autocorr":   round(lag1_autocorr(raw_samples), 4),
            "mean_filtered":   round(mean(filtered_samples), 2),
        },
        "raw_samples":      raw_samples,
        "filtered_samples": [round(f, 2) for f in filtered_samples],
        "timestamps_s":     timestamps,
    }

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"noise_motor{MOTOR_ID}.json")
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\n── Results ──────────────────────────────")
    print(f"  Samples:        {len(raw_samples)} @ {actual_hz:.1f} Hz")
    print(f"  Mean (raw):     {results['statistics']['mean_raw']:.1f} ADC counts")
    print(f"  Std dev:        {std:.2f} ADC counts")
    print(f"  Variance R:     {R:.2f}  ← use this in kalman_params.py")
    print(f"  Lag-1 autocorr: {results['statistics']['lag1_autocorr']:.3f}")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
