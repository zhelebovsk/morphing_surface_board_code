# Open Issues & Backlog

Ordered roughly by how soon each item will bite. Background is in the dated `CHANGES_*.md`
files.

## What has and hasn't been verified

**Every run to date has used exactly one board.** Verified on hardware with one board:
flashing, CAN commands and pong, telemetry streaming, PID with calibrated `min_pwm`,
the calibration app, presence scanning, PC-side bus-off recovery (`restart-ms 100`), and the
"nothing is answering" early stop.

**Never observed** — designed and reasoned about only: anything with two or more boards on
the bus, bus load at 30 boards, termination with many boards, presence tracking at scale,
the full mechanical surface moving together.

The bench board has motors only on hardware channels 12 and 13; calibration results for
other channels are meaningless.

Scale up incrementally (2 boards, then 4, 8, …) and check `ip -details -statistics link
show can0` error counters and the send-time warning after each step, rather than wiring all
30 at once.

## Before connecting more boards

### 1. Config re-send after a board reset — needs flashing + bench test

The pong reports whether the board has received config since boot; the host re-sends it to
any board that hasn't. Detection takes up to ~6 s with 30 boards. Nothing is re-sent until
**Send to all boards** has been clicked once per session. Bench steps: end of
`CHANGES_2026-10-19.md`.

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
- **CAN FD (planned, ready to test):** one 16-byte frame per board (`0x07`) with a 2 Mbit/s
  data phase, ~35% load. Implemented but off by default — test steps below. The slcan
  adapter can't do FD.
- Sending only changed values is another option.

**Testing CAN FD** (after the classic setup is verified on the bench):

1. **FD-safe check** — classic firmware (`CAN_FD_ENABLED 0`): run `./can_start_kvaser.sh fd`,
   set `CAN_FD = True` in `cantest/config.py`, start the GUI and **Start dynamic**. The board
   should answer pings but not move, and `bus-errors` in `ip -details -statistics link show
   can0` should stay at 0. This confirms a board that isn't flashed yet can't disturb an FD
   bus.
2. Set `#define CAN_FD_ENABLED 1` in `App/Inc/can_helper.h`, `make`, flash.
3. Back to the classic script and `CAN_FD = False`: the board should work exactly as before
   (FD firmware still accepts classic frames).
4. `./can_start_kvaser.sh fd` and `CAN_FD = True` again: the board answers pings, motors
   follow **Start dynamic**, and `bus-errors` stays at 0.
5. Run `cantest/test_comms.py` and compare the send time with classic.

To go back: `CAN_FD_ENABLED 0`, `CAN_FD = False`, plain `./can_start_kvaser.sh`.

**Note:** a board flashed before `ProtocolException = ENABLE` (in `STM32_code.ioc` /
`fdcan.c`) answers every FD frame with an error frame, freezing the whole surface. Reflash
every board before switching the host to FD.

### 3. CAN termination — confirm with the board designer

`memos/scheme-parts.md` says the board has a 120 Ω CAN terminator. A CAN bus needs exactly
two — one at each physical end. If every board has one fitted, they add up in parallel
(30 boards ≈ 4 Ω) and the bus stops working somewhere around 4–8 boards. **Ask the
designer whether the terminator can be disabled per board** before building the full bus.

Quick check: with the board unpowered and the adapter cable on but the Kvaser unplugged,
measure resistance between pins 2 and 7 of the 9-pin connector. ~120 Ω means fitted.

### 4. Board bus-off recovery — needs flashing + bench test

Without it, a board that goes bus-off ignores all commands until power-cycled.
`CAN_Check_Bus_Off()` restarts the controller; recoveries are counted in
`can_bus_off_recoveries`. Test: halt in gdb, `set *(uint32_t*)0x40006418 |= 1`, continue —
the board should keep answering pings and the counter should read 1.

### 5. Bit-timing sample point differs (low priority)

The boards sample at 87.5% of the bit (`STM32_code.ioc`: prescaler 10, seg1 13, seg2 2 at
160 MHz); the Kvaser is at 75%. Harmless on a short bench cable. On a long 30-board bus,
consider matching them (both ~80–87.5%) — e.g. `ip link set can0 type can bitrate 1000000
sample-point 0.875` in `can_start_kvaser.sh`.

## Firmware performance

### 6. Control loop runs at ~2 kHz, not the 10 kHz target

`fetch_potentiometer_values()` starts the ADC DMA and busy-waits for it every iteration.
The real fix is timer-triggered, circular, non-blocking DMA, so the loop always uses the
latest samples without waiting. Today the wait is only bounded by a 2 ms timeout.
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

## Controller config

### 10. Put the tuned config into the firmware defaults

The board keeps its controller config in RAM only; the PC re-sends it after a reset
(item 1). Until that re-send arrives, the board runs on the firmware defaults. Once tuning
settles, make the tuned values the firmware defaults so a reset board is correct
immediately. Keep the PC re-send for live tuning.

## Unresolved from bring-up

Motor driver for channels 13–14 didn't run although the FPGA output looked correct; 6 V motor
rail measured ~4.5 V. Re-check the rail under load.

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
