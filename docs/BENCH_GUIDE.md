# Bench Guide

How to set up, run, calibrate and troubleshoot the system. Written for a single board on
the bench, which is the only configuration tested so far (and that board has only two
motors attached, on hardware channels 12 and 13).

## One-time setup (Ubuntu)

```bash
sudo apt install gcc-arm-none-eabi make openocd stlink-tools can-utils gdb-multiarch
pip install python-can PySide6 numpy
```

- Use `gdb-multiarch` for debugging (`arm-none-eabi-gdb` is not what this setup uses).
- STM32CubeMX is only needed to change peripheral configuration (`STM32_code.ioc`) — see
  [Editing the CubeMX project](#editing-the-cubemx-project) below.
- Lattice Diamond is only needed to reprogram the FPGA.

## Hardware hookup

- **Power:** 12 V into the board's main connector. Everything else is derived on board.
- **Programming:** ST-LINK on the SWD header (X4).
- **CAN:** Kvaser Leaf v3 (USB) → its 9-pin D-sub → adapter → the board's RJ45.
- **Board ID:** set the DIP switch to the board number (1..30) *before* power-up; it's
  read once at boot.

## Build and flash

```bash
make -j4                 # → build/STM32_code.elf / .bin
./run.sh                 # builds, then flashes over ST-LINK with openocd and resets
# alternative: st-flash write build/STM32_code.bin 0x08000000
```

After reset the board samples its pots for ~1 s and holds every motor where it is.

## Bring up the CAN interface

Once per Kvaser plug-in (needs sudo):

```bash
./can_start_kvaser.sh
ip -details link show can0      # expect: "can state ERROR-ACTIVE restart-ms 100"
```

`restart-ms 100` is essential: `can0` recovers by itself 100 ms after a bus-off.

> **Note:** Linux's default (`restart-ms 0`) is to never recover, so a single bus-off left
> `can0` dead until someone ran `ip link set can0 down/up` by hand.

If you keep a copy of the script elsewhere (e.g. a Desktop shortcut), make it a symlink to
the repo's script so it can't go stale.

Do **not** add `one-shot on`.

> **Note:** one-shot (send each frame once, no automatic retries) would prevent bus-off
> outright, but this Kvaser's firmware doesn't support it — tested: the whole `ip` command
> fails with `Operation not supported`, leaving `can0` down.

`can_start.sh` is the equivalent for a serial slcan adapter: `./can_start.sh 6` uses
`/dev/ttyACM6`.

Watching traffic:

```bash
candump can0                    # everything
candump can0,101:7FF            # only board 1
cansend can0 101#06             # ping board 1 by hand → candump shows a reply: 101 [3] A1 01 00
                                # (last byte: 00 = not configured yet, 01 = configured;
                                #  firmware before 2026-10-19 replies with 2 bytes: A1 01)
```

## Run the control GUI

```bash
cd cantest
python main.py
```

1. Choose `can0` (or `DEMO-MODE` to run without hardware) → **Start**.
2. The app scans for boards 1..`BOARD_COUNT`. With fewer boards connected than that, it
   lists the absent ones (`N board(s) not responding: [...]`) — **normal**, the rest still
   work.

   > **Note:** pinging absent boards is harmless. On CAN, any live node acknowledges every
   > frame, whoever it's addressed to, so no errors build up as long as one board is up.
3. **Send the controller config** — "Board config packet" bar → **Send to all boards**.
   Boards boot with built-in defaults, and each board's calibrated `min_pwm` is only applied
   when you send this. After that, the app re-sends it automatically to any board that
   resets (terminal: *"Re-sending controller config to board(s) …"*).
4. **Run statically** (one frame at time *t*) or **Start dynamic** (continuous at
   `UPDATE_HZ`, speed set by μ).
5. To change what the surface does, edit `motor_function()` in `cantest/function.py`.

Calibration controls in the main window:
- **Edit limits** — table editor for `cantest/motor_min.csv` (each motor's lowest allowed
  position byte; the usable range is `min .. min + MOTOR_RANGE`).
- **Reload limits** — re-read `motor_min.csv` and `HW_tests/calibrations/latest.json`.
  The GUI also auto-reloads when either file changes.

The first position command after startup moves every motor to the commanded shape at
once, from wherever it was holding; make sure nothing is near a mechanical stop.

## Settings

**Host — `cantest/config.py`** (restart the GUI after changing):

| Setting | Default | What it does |
|---|---|---|
| `BOARD_COUNT` | 30 | Boards scanned and driven (IDs 1..N) |
| `MOTORS_PER_BOARD` | 14 | Motors per board |
| `UPDATE_HZ` | 100 | Position updates per second; bus load scales with it |
| `MOTOR_RANGE` | 150 | Travel of each motor above its `motor_min.csv` value, in position bytes |
| `DEFAULT_MIN_PWM` | 20 | `min_pwm` for boards missing from the calibration file |
| `BOARD_SPACING_MM` / `MOTOR_SPACING_MM` | 10 | Grid spacing used for `x`, `y` in the shape function |

**Board controller — from the GUI**, "Board config packet" bar: Kp, Ki, Kd, filter alpha,
PWM limit, deadband, `min_pwm` (per board, from calibration). The firmware defaults in
`App/Src/motor_helper.c` apply only until a config is sent. Ranges and scaling:
[CAN_PROTOCOL.md](CAN_PROTOCOL.md#0x03--controller-config).

**Board ID** — the DIP switch, read once at power-up.

## Calibrate motors

See `HW_tests/CALIBRATION.md`. Short version: close the GUI, then

```bash
cd HW_tests && python calibration_app.py
```

It finds each motor's `min_pwm`, flags suspicious channels (wrong direction, not attached),
writes `HW_tests/calibrations/latest.json` and sends the result to the boards. Commit
`latest.json` when you're happy with a run (timestamped runs are git-ignored).

## Editing the CubeMX project

Only needed to change pins, peripherals or clocks — building, flashing and running never
touch CubeMX. Open `STM32_code.ioc` in STM32CubeMX and regenerate; Core/ is only safe to
edit inside `USER CODE` blocks, since regeneration overwrites everything else.

Try the plain way first:

```bash
cubemx            # or however STM32CubeMX is installed on your machine
```

If its window renders badly (blank or frozen panels, common under Wayland), use
`./cube.zsh` instead. It runs CubeMX inside a nested X window: Xephyr, with openbox as the
window manager. Needs `sudo apt install xserver-xephyr openbox`, assumes `cubemx` is on
the PATH and a 1920×1080 window; Xephyr and openbox keep running after you close CubeMX,
so close the Xephyr window too.

## Troubleshooting

### Read the bus state

```bash
ip -details -statistics link show can0
```

| State | Meaning |
|---|---|
| `ERROR-ACTIVE` | Healthy. |
| `ERROR-WARNING` | Errors accumulating — wiring or termination is marginal. |
| `ERROR-PASSIVE` | Typically **nothing on the bus is acknowledging frames**: no board powered, cable unplugged, or bitrate mismatch. The adapter keeps retrying the same frame. Not one missing board. |
| `BUS-OFF` | Real bit errors happened. Auto-recovers after 100 ms. **But see the quirk below.** |

**Kvaser quirk:** after an auto-recovery, `ip` can keep showing `BUS-OFF` indefinitely even
though traffic is flowing normally. Don't trust the state alone — check whether the `TX
packets` counter is still increasing (a frame only counts once a node acknowledged it), or
just ping a board.

> **Note:** this is why the code's own "nothing is answering" check watches the TX counter
> instead of the reported state.

The kernel log records real bus-off events with timestamps:

```bash
journalctl -k | grep can0
```

### Known causes and fixes

| Symptom | Likely cause |
|---|---|
| Board missing, bus `ERROR-ACTIVE`, other boards fine | That board: power, DIP setting, firmware, its cable. Pings to absent boards are harmless — any live board acknowledges them. |
| Startup prints *"Scan stopped: … none of the pings … were acknowledged"* | Nothing alive on the bus. Board powered? Cable in? Board finished booting? |
| `BUS-OFF` right after powering or plugging a board in | Expected when a board powers up while the adapter is mid-retry. Recovers by itself in 100 ms; the app then re-sends config to the new board. |
| One board stops responding to everything, others fine, bus `ERROR-ACTIVE` | Firmware since 2026-10-19 recovers from its own bus-off automatically (check `can_bus_off_recoveries` in gdb). On older firmware, power-cycle the board. |
| `can0` dead, state `BUS-OFF`, `restart-ms 0` | Interface was brought up without the script. Re-run `./can_start_kvaser.sh`. |
| `RTNETLINK answers: Operation not supported` | Someone added `one-shot on`. Remove it. |
| Red *"WARNING: send_positions took … ms"* | Send cycle exceeded `1/UPDATE_HZ`. Expected to get worse with many boards — see OPEN_ISSUES.md. |
| Motor doesn't move / creeps | `min_pwm` too low for that motor (stiction), or config never sent after a board reset. |
| Motor never moves, its pot reads ~4095 | Pot not connected; firmware hard stop keeps it off. |
| Motor runs away from its target | Pot/motor polarity reversed on that channel. Calibration app flags this as "suspicious". |
| Board hangs at boot | Historically the ADC DMA wait (fixed 2026-08-11, now bounded). Attach with OpenOCD + `gdb-multiarch` to see where it's stuck. |
| GUI won't start / import error | Check `git diff cantest/` for stray edits — this has happened. |

### Live debugging

```bash
openocd -f interface/stlink.cfg -f target/stm32g4x.cfg
gdb-multiarch build/STM32_code.elf -ex "target extended-remote :3333"
```

Useful variables: `pot_raw`, `pot_filtered`, `desired_position`, `motor_speeds`,
`adc_timeout_count`, `conv_counter`, `board_id`, `Kp`/`Ki`/`min_pwm`,
`can_bus_off_recoveries`.
