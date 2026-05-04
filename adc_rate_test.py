#!/usr/bin/env python3
"""
adc_rate_test.py — Measure actual vs theoretical ADC sampling rate on STM32G474.

Connects to the running firmware via OpenOCD + ST-LINK (no CAN required).
Reads conv_counter[0] from motor_helper.c twice, MEASURE_DURATION_SEC apart,
and computes the real achieved ADC update rate.

Requirements:
  - openocd installed and on PATH
  - arm-none-eabi-nm installed and on PATH
  - ST-LINK connected to the board
  - Firmware built (build/STM32_code.elf must exist)
  - Firmware running on the board

Usage:
  python3 adc_rate_test.py
"""

import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────

ELF_PATH = "build/STM32_code.elf"

OPENOCD_CFG_FILES = ["interface/stlink.cfg", "target/stm32g4x.cfg"]
OPENOCD_HOST = "localhost"
OPENOCD_TELNET_PORT = 4444

MEASURE_DURATION_SEC = 2.0
OUTPUT_FILE = "adc_rate_results.json"

# ── Theoretical calculation ───────────────────────────────────────────────────
# From adc.c and SystemClock_Config in main.c:
#   HSE /2 * 40 /2 = 170 MHz SYSCLK
#   ADC12 clock source = SYSCLK, prescaler = DIV4 → 42.5 MHz ADC clock
#   Sampling time = ADC_SAMPLETIME_24CYCLES_5 = 24.5 cycles
#   12-bit resolution → 12.5 conversion cycles
#   Total per channel = 37 cycles

SYSCLK_HZ         = 170_000_000
ADC_PRESCALER     = 4
ADC_CLOCK_HZ      = SYSCLK_HZ / ADC_PRESCALER   # 42.5 MHz
SAMPLING_CYCLES   = 24.5
CONVERSION_CYCLES = 12.5
CYCLES_PER_CH     = SAMPLING_CYCLES + CONVERSION_CYCLES  # 37

ADC1_CHANNELS     = 13   # from adc.c: NbrOfConversion = 13
ADC2_CHANNELS     = 3    # from adc.c: NbrOfConversion = 3

ADC1_CYCLES       = ADC1_CHANNELS * CYCLES_PER_CH
ADC2_CYCLES       = ADC2_CHANNELS * CYCLES_PER_CH

ADC1_TIME_US      = (ADC1_CYCLES / ADC_CLOCK_HZ) * 1e6
ADC2_TIME_US      = (ADC2_CYCLES / ADC_CLOCK_HZ) * 1e6

# ADC1 and ADC2 are started together (DMA) and run in parallel.
# The bottleneck is ADC1 (more channels).
BOTTLENECK_US     = max(ADC1_TIME_US, ADC2_TIME_US)
THEORETICAL_MAX_HZ = 1e6 / BOTTLENECK_US

# From main.c: fix_motor_speeds() called every 500 µs → 2000 Hz actual rate
CONTROL_LOOP_US   = 500
CONTROL_LOOP_HZ   = 1e6 / CONTROL_LOOP_US


def compute_theoretical():
    return {
        "sysclk_mhz":          SYSCLK_HZ / 1e6,
        "adc_clock_mhz":       ADC_CLOCK_HZ / 1e6,
        "sampling_cycles":     SAMPLING_CYCLES,
        "conversion_cycles":   CONVERSION_CYCLES,
        "cycles_per_channel":  CYCLES_PER_CH,
        "adc1_channels":       ADC1_CHANNELS,
        "adc2_channels":       ADC2_CHANNELS,
        "adc1_sequence_us":    round(ADC1_TIME_US, 3),
        "adc2_sequence_us":    round(ADC2_TIME_US, 3),
        "bottleneck_adc":      "ADC1",
        "bottleneck_us":       round(BOTTLENECK_US, 3),
        "theoretical_max_hz":  round(THEORETICAL_MAX_HZ, 1),
        "control_loop_hz":     CONTROL_LOOP_HZ,
        "note": (
            f"ADC1 is the bottleneck ({ADC1_CHANNELS} ch). "
            f"Hardware can do {THEORETICAL_MAX_HZ:.0f} Hz, but the control loop "
            f"in main.c only triggers every {CONTROL_LOOP_US} µs → "
            f"{CONTROL_LOOP_HZ:.0f} Hz actual rate."
        ),
    }


# ── Symbol lookup ─────────────────────────────────────────────────────────────

def get_symbol_address(elf_path, symbol_name):
    """Return the address of a global symbol from the ELF, or None."""
    result = subprocess.run(
        ["arm-none-eabi-nm", elf_path],
        capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[2] == symbol_name:
            return int(parts[0], 16)
    return None


# ── OpenOCD telnet client ─────────────────────────────────────────────────────

class OpenOCDTelnet:
    PROMPT = b"> "

    def __init__(self, host, port, timeout=10):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect((host, port))
        self._read_until_prompt()  # consume the initial banner

    def _read_until_prompt(self):
        """Read bytes until the OpenOCD '> ' prompt appears."""
        buf = b""
        while not buf.endswith(self.PROMPT):
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        return buf.decode(errors="replace")

    def cmd(self, command):
        self.sock.sendall((command + "\n").encode())
        return self._read_until_prompt()

    def read_u32(self, address):
        """Read a 32-bit word at address. Target must be halted."""
        resp = self.cmd(f"mdw 0x{address:08X}")
        # Response: "0x20001234: deadbeef \n> "
        for line in resp.splitlines():
            if ":" in line and "0x" in line:
                try:
                    hex_val = line.split(":")[1].strip().split()[0]
                    return int(hex_val, 16)
                except (IndexError, ValueError):
                    pass
        return None

    def close(self):
        try:
            self.sock.sendall(b"exit\n")
        except Exception:
            pass
        self.sock.close()


# ── Hardware measurement ──────────────────────────────────────────────────────

def measure_actual_rate(elf_path, duration_sec):
    """
    Start OpenOCD, connect, and measure the rate of conv_counter[0].

    Returns (result_dict, error_string). One of them will be None.
    """
    # Find symbol
    addr = get_symbol_address(elf_path, "conv_counter")
    if addr is None:
        return None, "Symbol 'conv_counter' not found in ELF (was the firmware built?)"
    print(f"  conv_counter[0] address: 0x{addr:08X}")

    # Build OpenOCD command
    # "init; halt" connects without resetting the target so conv_counter keeps running.
    ocd_args = ["openocd"]
    for cfg in OPENOCD_CFG_FILES:
        ocd_args += ["-f", cfg]
    ocd_args += ["-c", "tcl_port disabled", "-c", "init", "-c", "halt"]

    ocd_proc = subprocess.Popen(
        ocd_args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1.5)   # wait for OpenOCD to enumerate the target

    try:
        ocd = OpenOCDTelnet(OPENOCD_HOST, OPENOCD_TELNET_PORT, timeout=15)
    except Exception as e:
        ocd_proc.terminate()
        ocd_proc.wait()
        return None, f"Could not connect to OpenOCD telnet: {e}"

    try:
        # --- First read ---
        ocd.cmd("halt")
        count1 = ocd.read_u32(addr)
        ocd.cmd("resume")

        if count1 is None:
            return None, "Failed to read conv_counter[0] (first read)"
        print(f"  conv_counter[0] at t=0 s:  {count1}")

        # Only time the sleep — firmware runs freely here, halt/resume overhead excluded
        t1 = time.perf_counter()
        time.sleep(duration_sec)
        t2 = time.perf_counter()

        # --- Second read ---
        ocd.cmd("halt")
        count2 = ocd.read_u32(addr)
        ocd.cmd("resume")
        ocd.close()

        if count2 is None:
            return None, "Failed to read conv_counter[0] (second read)"
        print(f"  conv_counter[0] at t={duration_sec} s: {count2}")

        elapsed = t2 - t1   # ≈ duration_sec, unaffected by OpenOCD command latency
        delta   = count2 - count1
        actual_hz = delta / elapsed

        return {
            "conv_counter_start":  count1,
            "conv_counter_end":    count2,
            "delta_conversions":   delta,
            "elapsed_sec":         round(elapsed, 4),
            "actual_hz":           round(actual_hz, 2),
        }, None

    except Exception as e:
        return None, str(e)
    finally:
        ocd_proc.terminate()
        ocd_proc.wait()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("ADC Sample Rate Test — STM32G474")
    print("=" * 60)

    results = {
        "timestamp":   datetime.now().isoformat(),
        "theoretical": None,
        "measured":    None,
        "error":       None,
    }

    # 1. Theoretical
    print("\n[1/2] Theoretical ADC rate (from adc.c + main.c config):")
    th = compute_theoretical()
    results["theoretical"] = th

    print(f"  ADC clock:          {th['adc_clock_mhz']} MHz")
    print(f"  Cycles/channel:     {th['cycles_per_channel']}  "
          f"({th['sampling_cycles']} sampling + {th['conversion_cycles']} conversion)")
    print(f"  ADC1 sequence:      {th['adc1_sequence_us']} µs  ({th['adc1_channels']} channels)")
    print(f"  ADC2 sequence:      {th['adc2_sequence_us']} µs  ({th['adc2_channels']} channels)")
    print(f"  Theoretical max:    {th['theoretical_max_hz']} Hz  (complete 16-motor read)")
    print(f"  Control loop limit: {th['control_loop_hz']:.0f} Hz  (every {CONTROL_LOOP_US} µs in main.c)")

    # 2. Hardware measurement
    if not os.path.exists(ELF_PATH):
        msg = f"ELF not found at '{ELF_PATH}'. Build the firmware first ('make')."
        print(f"\n[2/2] Hardware measurement skipped: {msg}")
        results["error"] = msg
    else:
        print(f"\n[2/2] Measuring actual ADC rate over {MEASURE_DURATION_SEC:.1f}s via ST-LINK...")
        measured, err = measure_actual_rate(ELF_PATH, MEASURE_DURATION_SEC)
        if err:
            print(f"  ERROR: {err}")
            results["error"] = err
        else:
            results["measured"] = measured
            ratio = (measured["actual_hz"] / th["theoretical_max_hz"]) * 100
            print(f"  Actual rate:        {measured['actual_hz']} Hz")
            print(f"  Hardware utilised:  {ratio:.1f}% of theoretical max")
            if measured["actual_hz"] > 0:
                actual_us = 1e6 / measured["actual_hz"]
                print(f"  Period:             {actual_us:.1f} µs")

    # 3. Save
    with open(OUTPUT_FILE, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {OUTPUT_FILE}")

    if results.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    main()
