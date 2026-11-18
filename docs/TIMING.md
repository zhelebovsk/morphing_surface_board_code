# Timing

How long things take, from a CAN frame to a motor reaching its target. Each number is marked
**measured** (bench, 2026-11-18, board 1) or **calculated** (from frame sizes and config).
Motor numbers come from one motor only — host m12, hardware channel 13, on the bench — and are
in ADC counts (no mm conversion measured yet).

## Communication

| What | Value | Source |
|---|---|---|
| One frame on the wire | 111–135 µs classic, ~110–130 µs FD | calculated (range = bit stuffing) |
| Ping round trip, PC → board → PC (incl. USB, Kvaser) | median 0.34 ms, max 0.64 ms, 0 of 300 lost | measured |
| All 30 boards, one position cycle | 6.7 ms classic, 3.2 ms FD | measured (`test_comms.py`) |
| Bus load at 100 Hz | 67 % classic, 32 % FD | measured cycle × 100 Hz |
| Max send rate for 30 boards at ≤ 40 % load | ~60 Hz classic, ~125 Hz FD | calculated |
| Delay between board 1 and board 30 in one cycle | up to 6.7 ms classic, 3.2 ms FD | measured cycle (boards are sent in order) |

The smallest update is one board frame: 7 motors in classic CAN, all 14 in FD.

## Board

| What | Value | Source |
|---|---|---|
| Control loop (all 16 channels per pass) | 7.45 kHz, one pass ≈ 134 µs | measured (`adc_rate_test.py`) |
| New target picked up after the frame arrives | ≤ 134 µs (next pass) | from the loop period |
| ADC read of all pots | 12 µs | calculated |
| Motor PWM | 52.08 kHz | calculated |

## One motor moving (measured)

900-count edge-to-edge stroke (ADC 1097 ↔ 2000), GUI default PID, 1–3 runs per value.

| | u_limit 65 (GUI default) | u_limit 100 |
|---|---|---|
| First motion after the command | 12–20 ms | 13–15 ms |
| Reaches cruise speed | ~19–24 ms after the command | ~22–25 ms after the command |
| Cruise speed | ~2700–3200 counts/s | ~5100–5300 counts/s |
| **Edge to edge (first within ±10)** | **371 ms up, 374 ms down** | **267–270 ms up, 276–281 ms down** |
| Overshoot | 47 counts up, 0 down | 21–45 counts up, ≤ 1 down |
| Parked within ±15 | 394 ms up, 371 ms down | 294–314 ms up, 274–276 ms down |

- Spin-up is short (cruise within ~12 ms of first motion); the rotor's momentum shows mainly as
  overshoot when stopping, and only upward on this motor.
- The last ~200–450 counts are slower (~1500–2000 counts/s): there the PID output drops to the
  `min_pwm` floor. A higher Kp shortens this.
- Upward moves can hunt at the ±10 deadband edge for up to a few seconds while staying within ±15.

## Wave tracking (measured)

Sine, ±300 counts around 1601, u_limit 65, 100 Hz setpoints, two runs.

| μ (cycles/s) | Amplitude reached | Lag | Max error |
|---|---|---|---|
| 0.1 | 99.5–99.6 % | 54 ms | 25–29 counts |
| 0.2 | 99.5 % | 35 ms | 26–31 counts |
| 0.3 | 99.5 % | 27 ms | 26–33 counts |
| 0.5 (GUI max) | 99.4–99.5 % | 22 ms | 32 counts |

The lag comes mostly from the deadband: the motor reacts once it is 10 counts behind, which takes
longer on a slow wave. The motor needs at most ~940 counts/s here, well under its cruise speed, so the
real limit lies above μ = 0.5 (not measured).

## Measuring it again

```bash
cd hostCan/HW_tests        # CAN up, GUI closed; on the bench add --no-motor 13,14
python3 motion_timing_test.py 1 12 stroke --low 1100 --high 2000 --u-limit 100
python3 motion_timing_test.py 1 12 sine --low 1300 --high 1900 --mu 0.1,0.2,0.3,0.5
cd .. && python3 test_comms.py         # full 30-slot bus cycle
```

**Not measured yet:** mm per ADC count, other motors, motors under the real surface load, wave
speeds above μ = 0.5, the host's send-loop jitter, and anything with more than one board.
