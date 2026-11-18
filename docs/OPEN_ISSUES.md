# Open Issues & Backlog

Ordered roughly by how soon each item will bite. Background is in the dated logs in `docs/changes/`.

## What has and hasn't been verified

**Fleet run (June 2026, `main` as of ~`3fc2979`):** an older version ran the full surface
with ~26–30 boards — classic CAN at 1 Mbit/s through the slcan adapter, 100 Hz back-to-back
sending, `MOTOR_RANGE = 40`, `min_pwm` and telemetry streaming already in the firmware. This
proves the wiring, termination as fitted, board IDs, classic-CAN bus load and basic position
control at fleet scale.

**Verified with one board only** (current code): flashing, CAN commands and pong, telemetry
streaming, PID with calibrated `min_pwm`, the calibration app, presence scanning, PC-side
bus-off recovery (`restart-ms 100`), the "nothing is answering" early stop, CAN FD (#2),
config re-send after a reset (#1), board bus-off recovery (#4), and the full 30-slot send
load (`test_comms.py`).

**Not yet run with more than one board:** everything added since June — CAN FD, bus-off
recovery, presence tracking and config re-send, per-board calibrated `min_pwm`, the Kvaser
adapter, and `MOTOR_RANGE = 150` on the full mechanical surface.

**Note:** `MOTOR_RANGE = 150` is ~4× the travel used in June; start the first full run with
a low μ or **Run statically** and watch for motors reaching their mechanical ends.

The bench board has motors only on hardware channels 12 and 13; calibration results for
other channels are meaningless.

Scale up incrementally (2 boards, then 4, 8, …) and check `ip -details -statistics link
show can0` error counters and the send-time warning after each step, rather than wiring all
30 at once.

## Before connecting more boards

### 1. Config re-send after a board reset — done

The pong reports whether the board has received config since boot; the host re-sends it to
any board that hasn't. Nothing is re-sent until **Send to all boards** has been clicked once
per session. Bench-tested: after a reset the config was back within ~1 s (up to ~6 s expected
with 30 boards); until then the board runs on the firmware defaults (#10).

### 2. Bus load at 30 boards — CAN FD halves it

Measured with `hostCan/test_comms.py` (one real board ACKs the frames for the 29 absent ones),
time per 30-board cycle at `UPDATE_HZ = 100`:

| Mode | Frames per cycle | Time per 10 ms cycle | Bus load |
|---|---|---|---|
| Classic (`0x01` + `0x02`) | 60 × 8 bytes | 6.7 ms | ~67% |
| CAN FD (`0x07`) | 30 × 16 bytes, 2 Mbit/s data | 3.2 ms | ~32% |

CAN is normally kept under 30–40%, so classic leaves too little room for presence pings and
telemetry. FD is the planned fix; the steps below were run on one board.

- **If FD causes trouble:** `UPDATE_HZ = 50` in `hostCan/config.py` halves either figure. Motor
  mechanical bandwidth is under 20 Hz (`hostCan/HW_tests/NOTES_2026-06-15.md`).
- The slcan adapter can't do FD.
- Sending only changed values is another option.

**Switching to CAN FD:**

1. Flash every board with `CAN_FD_ENABLED 1` (the default in `firmware/App/Inc/can_helper.h`). FD
   firmware works unchanged on a classic bus.
2. `./can_start_kvaser.sh fd`, then restart the GUI (the host follows `can0`'s mode and prints
   a line when it is in FD mode).
3. Run `hostCan/test_comms.py`: *frames on the bus* must match the expected count and
   `bus-errors` in `ip -details -statistics link show can0` must stay at 0.

Bench-tested on one board, including motors following **Start dynamic**. Still unchecked:
more than one board.
Boards still on firmware older than November 2026 must be reflashed first (last note below).

To go back: plain `./can_start_kvaser.sh` and restart the GUI.

**Note:** FD only works with the Kvaser's sample points matching the boards (87.5% / 80%); at
the Kvaser default of 75% the board rejects most FD frames. `can_start_kvaser.sh` sets this.

**Note:** `test_comms.py`'s send time only shows frames were queued; *frames on the bus* is
the real check.

**Note:** a board on classic firmware ignores FD frames without disturbing the bus but doesn't
move. With no FD board on the bus, the Kvaser retries the first FD frame forever.

**Note:** a board flashed before `ProtocolException = ENABLE` (in `firmware/STM32_code.ioc` /
`fdcan.c`) answers every FD frame with an error frame, freezing the whole surface. Reflash
every board before switching the host to FD.

### 3. CAN termination — worked in June; measure once

`docs/hardware/scheme-parts.md` says the board has a 120 Ω CAN terminator. A CAN bus needs exactly
two — one at each physical end; 30 fitted in parallel (≈ 4 Ω) would break the bus. The June
fleet run worked with ~26–30 boards, so the bus as wired is fine; it's still worth knowing
which boards have one fitted, and whether it can be disabled, before rewiring.

Quick check: with the board unpowered and the adapter cable on but the Kvaser unplugged,
measure resistance between pins 2 and 7 of the 9-pin connector. ~120 Ω means fitted.

### 4. Board bus-off recovery — done

`CAN_Check_Bus_Off()` restarts the controller after a bus-off; recoveries are counted in
`can_bus_off_recoveries`. Bench-tested without halting the CPU: `openocd -f interface/stlink.cfg
-f target/stm32g4x.cfg -c init -c "mww 0x40006418 0x301"` (sets CCCR.INIT; read CCCR first and
OR in 1). The counter went to 1 and the board kept answering pings.

**Note:** don't halt the CPU in gdb with motors powered: PWM keeps running at the last duty
while the PID loop is stopped.

### 5. Bit-timing sample point — done

`can_start_kvaser.sh` sets the Kvaser to the boards' 87.5% in both modes (required for FD, #2).

### 12. Unexplained CAN receive errors on the bench

On 2026-11-18 the Kvaser counted 252 receive errors (0 transmit errors) at some point during an
afternoon of testing. They did not recur idle, under 1000 pings, under a 1 kHz telemetry stream,
or during a full-speed stroke; likely an event such as a board reset or plug-in mid-traffic.
To catch the cause next time, watch `ip -details -statistics link show can0` before and after
each step of a session.

## Firmware performance

### 6. Control loop runs at ~7.5 kHz, not the 10 kHz target

Measured 7.45 kHz (one pass ≈ 134 µs) with `hostCan/HW_tests/adc_rate_test.py`. The ADC
conversion itself is only ~12 µs of that; where the rest goes hasn't been profiled. Low
priority: motor mechanical bandwidth is under 20 Hz.

- `fetch_potentiometer_values()` still starts the ADC DMA and busy-waits for it every pass
  (bounded by a 2 ms timeout). Timer-triggered, circular, non-blocking DMA would remove that
  wait and give a steady sample rate.

### 7. Re-tune alpha if the loop rate changes

Cut-off `fc = −fs·ln(1−alpha)/(2π)`. At the measured ~7.5 kHz, the default alpha 0.2 gives
~265 Hz (alpha 0.1: ~125 Hz), still far above the motors' < 20 Hz. A ~70 Hz cut-off would need
alpha ≈ 0.06, but firmware clamps alpha to ≥ 0.1, so that clamp would need changing too.

## Calibration & limits

### 8. Per-motor safe range from calibration isn't used

`calibration_app.py`'s range sweep records `safe_min`/`safe_max` per motor, but nothing reads
them. Every motor's range is `motor_min.csv` + a uniform `MOTOR_RANGE = 150`, and the shape
function can push a motor to the top of that range whether or not its mechanism allows it.
Next step: clamp (not rescale) each motor to its calibrated safe range in `limits.py`.

### 9. `motor_max.csv` — removed

It was never read. Each motor's top is `motor_min` + `MOTOR_RANGE`, capped at 255
(`communication.scale_value`).

## Controller config

### 10. Put the tuned config into the firmware defaults

The board keeps its controller config in RAM only; the PC re-sends it after a reset
(item 1). Until that re-send arrives, the board runs on the firmware defaults. Once tuning
settles, make the tuned values the firmware defaults so a reset board is correct
immediately. Keep the PC re-send for live tuning.

## FPGA

### 11. Which FPGA design is on the boards isn't recorded

`fpga/` holds four variants of the PWM/DIR design, and the programmed file (`.jed`) isn't in
the repo or on the bench PC. `fpga/blink_test.ldf` builds `scaled_digital_on.v` with
`array_port_settings_tim.lpf`, but that's what *would* be built, not necessarily what's on
the boards. The motor logic is identical in all variants; they differ in the pot combiner
and whether they need the external 40 MHz clock. It matters before programming any new board.

- **Cheapest:** ask whoever programmed the boards which file they used, then keep the `.jed`
  and delete the unused variants.
- **Definitive:** build the candidate in Lattice Diamond and run **Verify** in Diamond
  Programmer over the board's JTAG header (needs a Lattice cable, e.g. HW-USBN-2B).

**Note:** the pot combiner in `scaled_digital_on.v` uses AND (`&`) while its comments and
`scaled_digital_tim.v` say OR (`|`). Only matters if the STM32 uses `POT_OUT`.

## Unresolved from bring-up

Motor driver for channels 13–14 didn't run although the FPGA output looked correct; 6 V motor
rail measured ~4.5 V. Re-check the rail under load.

## Housekeeping

- BENCH_GUIDE "Hardware hookup" (12 V input, SWD header X4, D-sub → RJ45 adapter) hasn't
  been confirmed against the actual hardware.
- `firmware/App/Src/usb_debug.c` and the old opcode handlers in `can_helper.c` are fully commented
  out. Delete or revive them; dead code misleads.
- Position commands received in the first ~1 s after boot (`position_init`) are overwritten
  — harmless at 100 Hz, but a one-off command sent right at power-up is lost.
- `scan_boards()` takes ~1.8 s with 29 absent boards (each batch waits out its timeout).
  Harmless at startup; drops to almost nothing once boards answer.
