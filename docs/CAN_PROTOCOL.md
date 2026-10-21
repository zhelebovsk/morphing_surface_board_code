# CAN Protocol

Classic CAN (not FD), **1 Mbit/s**, standard 11-bit IDs, 8-byte max payload.
Source of truth: `App/Src/can_helper.c` (board side), `cantest/communication.py` (host side).

## Addressing

Each board's ID comes from its 6-position DIP switch, read once at boot
(`App/Src/dip.c`):

```
CAN ID = 0x100 + DIP value        board 1 → 0x101, board 30 → 0x11E
```

- The host numbers boards **1..30** (`BOARD_COUNT` in `cantest/config.py`), so set DIPs to
  1..30. DIP 0 (ID `0x100`) is never addressed by the host. 6 bits allow up to 63.
- **The same ID is used in both directions.** The host sends commands to `0x100+n`; board
  *n* replies on `0x100+n` too. Replies are told apart from commands by their first byte
  (`0xA0`/`0xA1`), never by ID.
- There is **no hardware acceptance filter** (one was tried and crashed release builds — see
  `CHANGES_2026-08-11.md`). Every board receives every frame and discards the ones whose ID
  isn't its own in the RX interrupt.

Byte 0 of every frame is the opcode.

## Host → board

### `0x01` / `0x02` — set positions (sent every cycle, 100 Hz)

```
0x01: [0x01, p0, p1, p2, p3, p4, p5, p6]        motors in slots 0..6
0x02: [0x02, p7, p8, p9, p10, p11, p12, p13]    motors in slots 7..13
```

Each `p` is a 0..255 position byte. The board converts it to an ADC setpoint:

```
desired_position = pot_zero + p * 7        (pot_zero = 1048, LOCATION_MULTIPLIER = 7)
                   clamped to [680, 3415]  (LO_LIMIT / HI_LIMIT)
```

so `p` = 0..255 maps to ADC 1048..2833. Slot *k* drives firmware motor
`active_motors[k]` = *k*+1 — see the numbering table in [ARCHITECTURE.md](ARCHITECTURE.md).

The host sends `0x02` then `0x01` for each board, and skips boards it currently believes are
absent.

### `0x03` — controller config

```
[0x03, kp, ki, kd, alpha, u_limit, deadband, min_pwm]
```

| Byte | Firmware value | Default at boot | GUI slider default |
|---|---|---|---|
| kp | `Kp = kp/255` | 0.2 | 51 (= 0.2) |
| ki | `Ki = ki/255` | 0.1 | 26 (≈ 0.1) |
| kd | `Kd = kd/255` | 0.0 | 0 |
| alpha | IIR filter `alpha = a/255`, **clamped to [0.1, 0.8]** | 0.2 | 51 (= 0.2) |
| u_limit | max PWM magnitude, 0..255 (255 = 100% duty) | 100 | 65 ("Limit signal") |
| deadband | error (ADC counts) below which the motor is switched off | 10 | 10 |
| min_pwm | minimum PWM whenever outside deadband (overcomes stiction) | 50 | per-board calibrated value |

Applies to **all motors on the board**. Not stored in flash: **a board that resets comes back
with the boot defaults** until the host sends `0x03` again. Once a config has been sent from
the GUI, the host re-sends it automatically to any board that reports (in its pong) that it
hasn't received one.

### `0x04` / `0x05` — telemetry stream on / off

```
0x04: [0x04, motor_index, interval_ms]   start streaming one motor (firmware index 0..15)
0x05: [0x05]                             stop
```

This is a measurement feature: it makes the *board* report one motor's actual position back
to the PC (as `0xA0` frames, below) until told to stop. Normally traffic only flows PC →
board, and boards never report positions. The motor keeps being controlled normally while
streaming.

Used by `HW_tests/calibration_app.py` and `step_response_test.py` to watch how a motor
responds to a small step (did it move, which way, how fast). The main GUI never uses it.
It replaced reading positions over ST-LINK/OpenOCD, which halts the CPU on every read and
corrupted the measurements.

`interval_ms = 0` streams on every control-loop iteration. Only one motor per board can
stream at a time.

### `0x06` — ping

```
[0x06]
```

Board replies with a pong (below). Used by `scan_boards()` at startup and by the background
`poll_presence()` to track which boards are present.

## Board → host

### `0xA0` — telemetry sample (while streaming)

```
[0xA0, motor_index, raw_lo, raw_hi, filt_lo, filt_hi, ts_lo, ts_hi]
```

- `raw`: `uint16` `pot_raw[motor]` (unfiltered ADC, 0..4095)
- `filt`: `int16` `pot_filtered[motor]` (IIR output, truncated)
- `ts`: low 16 bits of the board's microsecond timer (wraps every ~65 ms — use for
  intervals between consecutive samples, not absolute time)

All little-endian.

### `0xA1` — pong

```
[0xA1, board_id & 0xFF, config_received]
```

- Byte 1 is the low byte of the CAN ID (e.g. `0x01` for board 1); the host identifies the
  responder from the arbitration ID (`id - 0x100`).
- Byte 2 is `1` once the board has received a `0x03` config since it booted, `0` before. The
  host re-sends config to any board reporting `0` (see `ControlMotor._resend_config_where_needed`).
  Firmware before 2026-10-19 sends a 2-byte pong without it; the host still accepts that and
  falls back to re-sending config when a board reappears after being marked missing.

## Retired opcodes

`can_helper.c` still contains commented-out handlers for older opcodes (speed up/down, reset
`0x0D`, raw PWM `0x0E`/`0x0F`, motor supply voltage). They are not compiled in. If you
revive one, note that `0x04`–`0x06` have since been reused.

## Bus budget (predicted, not measured)

A full position cycle is 2 frames × 30 boards = 60 frames of ~118 bits ≈ **7.1 ms per cycle**,
i.e. **~70% bus load at 100 Hz**. That's high for CAN (30–40% is the usual comfort zone).
See OPEN_ISSUES.md.
