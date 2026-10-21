# Open Issues & Backlog

As of 2026-10-19. Ordered roughly by how soon it will bite. Dated `CHANGES_*.md` files have
the full background for each item.

## What has and hasn't been verified

**Every run to date has used exactly one board.** Verified on hardware with one board:
flashing, CAN commands and pong, telemetry streaming, PID with calibrated `min_pwm` (on the
two motors that are attached — see "From early hardware bring-up" below),
the calibration app, presence scanning, PC-side bus-off recovery (`restart-ms 100`), and the
"nothing is answering" early stop.

**Never observed** — designed and reasoned about only: anything with two or more boards on
the bus, bus load at 30 boards, termination with many boards, presence tracking at scale,
the full mechanical surface moving together.

Scale up incrementally (2 boards, then 4, 8, …) and check `ip -details -statistics link
show can0` error counters and the send-time warning after each step, rather than wiring all
30 at once.

## Before connecting more boards

### 1. Controller config is lost when a board resets — FIXED in code, not yet on hardware

The `0x03` config (Kp/Ki/Kd, alpha, `u_limit`, deadband, `min_pwm`) lives in RAM only. A
board that resets — power cycle, brown-out, or simply being plugged in — returns to the
built-in defaults (`App/Src/motor_helper.c`: Kp 0.2, Ki 0.1, alpha 0.2, `u_limit` 100,
deadband 10, `min_pwm` 50). Note the GUI's default `Limit signal` is 65, not 100.

The host only sends config when someone clicks **Send to all boards** (or when the
calibration app finishes). The background presence monitor notices a board coming back
but doesn't re-send its config, so after a reset the board quietly runs on defaults with the
wrong `min_pwm`.

**Fixed 2026-10-19 (needs flashing + a bench test):** the pong now carries a
"config received since boot" byte, and the host's background monitor re-sends each board
the config it last sent it (or the most recent config, for a board never configured)
whenever a board reports `0`. Detection latency is one presence check of that board — up to
~6 s with 30 boards present, since each check pings 5 present boards. With old firmware,
only a board that drops out for 3+ checks and returns gets its config re-sent; a quick
reset goes unnoticed. Storing config in the on-board EEPROM would remove the need
entirely, but isn't done.

Still true: nothing is re-sent until someone has clicked **Send to all boards** at least
once per session.

### 2. Bus load at 30 boards is predicted at ~70%

Two 8-byte frames per board per cycle: 60 frames × ~118 µs ≈ 7.1 ms of every 10 ms cycle at
`UPDATE_HZ = 100`. CAN is normally kept under 30–40%. Expect the red *send_positions took
… ms* warning once many boards are connected, plus less room for presence pings and
telemetry.

- **Cheapest fix:** `UPDATE_HZ = 50` in `cantest/config.py` (~36%). Motor mechanical
  bandwidth is under 20 Hz (`HW_tests/NOTES_2026-06-15.md`), so 100 Hz is already ~5×
  oversampled.
- Measure first: `cantest/test_comms.py` runs the full 60-frame cycle against however
  many boards are present (the real boards ACK the frames for the absent ones).
- **CAN FD:** one frame per board at a faster data rate, roughly 20–30% load. Tried
  2026-06-22 and reverted, possibly only because of the boot-order bug (fixed 2026-08-11) —
  worth a retry. Needs `fd on dbitrate …` in `can_start_kvaser.sh` as well as the firmware
  change; the slcan adapter route would stop working.
- Sending only changed values is another option.

### 3. CAN termination — confirm with the board designer

`memos/scheme-parts.md` says the board has a 120 Ω CAN terminator. A CAN bus needs exactly
two — one at each physical end. If every board has one fitted, they add up in parallel
(30 boards ≈ 4 Ω) and the bus stops working somewhere around 4–8 boards. This is very likely
handled by the design (jumper or not fitted on most boards) but isn't documented. **Ask the
designer whether the terminator can be disabled per board** before building the full bus.

Quick check: with the board unpowered and the adapter cable on but the Kvaser unplugged,
measure resistance between pins 2 and 7 of the 9-pin connector. ~120 Ω means fitted.

### 4. A board whose CAN controller goes bus-off stays off the bus — FIXED in code, not yet on hardware

The PC side recovers from bus-off automatically (`restart-ms 100`), but the boards don't.
On the STM32G4's FDCAN, bus-off leaves the controller stopped (`CCCR.INIT` set) until
software clears it, and the firmware has no bus-off handling — no
`HAL_FDCAN_ErrorStatusCallback`, no `FDCAN_IT_BUS_OFF`. A board that transmits (pong,
telemetry) while the bus is being disturbed — e.g. another board powering up on a live bus —
could go bus-off and then silently ignore all commands, holding its last position, until
someone power-cycles it. Not yet observed (only one board has ever run).

**Fixed 2026-10-19 (needs flashing + a bench test):** `CAN_Check_Bus_Off()`
(`App/Src/can_helper.c`), called every main-loop iteration, clears `CCCR.INIT` if the
controller has stopped itself, which starts the standard recovery. Recoveries are counted
in `can_bus_off_recoveries` (readable with gdb). Config survives this — it's not a reset.

How to test without waiting for a real bus-off: with the board running, halt it in gdb,
`set *(uint32_t*)0x40006418 |= 1` (FDCAN1 `CCCR.INIT`), continue — the board should keep
answering pings and `can_bus_off_recoveries` should read 1.

### 5. Bit-timing sample point differs (low priority)

The boards sample at 87.5% of the bit (`STM32_code.ioc`: prescaler 10, seg1 13, seg2 2 at
160 MHz); the Kvaser is at 75%. Harmless on a short bench cable. On a long 30-board bus,
consider matching them (both ~80–87.5%) — e.g. `ip link set can0 type can bitrate 1000000
sample-point 0.875` in `can_start_kvaser.sh`.

## CAN behaviour to know about (settled, not bugs)

- **Absent boards are harmless.** CAN acknowledgement isn't addressed — any live board
  ACKs every frame. Bench-confirmed 2026-10-19.
- **Nothing alive on the bus → `ERROR-PASSIVE`, not bus-off.** The adapter retries forever
  and the scan's early stop reports it.
- **Bus-off happens when a board powers up while the adapter is retrying** — real bit
  errors. `restart-ms 100` recovers it in 100 ms. This was the cause of the August "board
  won't connect" problem.
- **The Kvaser driver can report `BUS-OFF` after recovering** even while traffic flows.
  Use the TX counter, not the state, as the source of truth.
- **One-shot mode isn't supported** by this adapter's firmware. Don't re-add it.

## Firmware performance

### 6. Control loop runs at ~2 kHz, not the 10 kHz target

`fetch_potentiometer_values()` starts the ADC DMA and busy-waits for it every iteration.
The real fix is timer-triggered, circular, non-blocking DMA, so the loop always uses the
latest samples without waiting. The 2026-08-11 change only bounded the wait (to stop hangs).
Measure with `HW_tests/adc_rate_test.py`.

### 7. Re-tune alpha if the loop rate changes

alpha 0.1–0.3 is right at 2 kHz (cut-off ~34–110 Hz). At 10 kHz the same alpha passes ~5×
higher frequencies; it would need ~0.04–0.06 — but firmware clamps alpha to ≥ 0.1, so that
clamp would need changing too.

## Calibration & limits

### 8. Per-motor safe range from calibration isn't used

`calibration_app.py`'s range sweep records `safe_min`/`safe_max` per motor, but nothing reads
them. Every motor's range is `motor_min.csv` + a uniform `MOTOR_RANGE = 150`, and the shape
function can push a motor to the top of that range whether or not its mechanism allows it.
Next step: clamp (not rescale) each motor to its calibrated safe range in `limits.py`.

### 9. `cantest/motor_max.csv` is unused

Kept in the repo but not read by any code. Either wire it in (could replace item 8) or
delete it so nobody edits it expecting an effect.

## From early hardware bring-up — status unknown

`PROBMELS.md` (December 2025) recorded: the motor driver for channels 13–14 not running even
though the FPGA output looked correct on a scope, and the 6 V motor rail measuring ~4.5 V.
Neither has a recorded resolution. Re-check the 6 V rail under load.

**The bench board has only two motors attached.** The June notes found valid pot readings
only on hardware channels 12 and 13, and the latest calibration
(`HW_tests/calibrations/latest.json`) is consistent: channels 12 and 13 calibrate cleanly;
every other channel is flagged suspicious or got no result. So "verified on hardware" in
this repo means *two motors on one board*. Treat calibration results for other channels as
meaningless until motors are attached to them.

## Housekeeping

- Which FPGA bitstream (`lattice_code/*.v` variant) is on the boards isn't recorded.
- BENCH_GUIDE "Hardware hookup" (12 V input, SWD header X4, D-sub → RJ45 adapter) hasn't
  been confirmed against the actual hardware.
- `App/Src/usb_debug.c` and the old opcode handlers in `can_helper.c` are fully commented
  out. Delete or revive them; dead code misleads.
- Position commands received in the first ~1 s after boot (`position_init`) are overwritten
  — harmless at 100 Hz, but a one-off command sent right at power-up is lost.
- `scan_boards()` takes ~1.8 s with 29 absent boards (each batch waits out its timeout).
  Harmless at startup; drops to almost nothing once boards answer.
