# Morphing Surface — Board Firmware & Host Control

Firmware and PC software for a morphing-surface system in a water tunnel: a grid of DC
motors deforms a flexible wall so it follows a shape function `u(x, y, t)` (for example a
travelling wave).

- **30 boards** (planned), each an STM32G474 driving **14 DC motors** with potentiometer
  position feedback and a PID loop per motor.
- A **Linux PC** runs a Python/Qt app that computes the target shape and streams position
  setpoints to every board over **CAN at 1 Mbit/s**, through a Kvaser Leaf v3 USB adapter.

**Status:** tested with one board only (2 motors). Fleet-scale behaviour is untested; see
[OPEN_ISSUES](docs/OPEN_ISSUES.md).

## Documentation

| Read this | For |
|---|---|
| [docs/BENCH_GUIDE.md](docs/BENCH_GUIDE.md) | **Start here.** Setup, build/flash, bring up CAN, run the GUI, calibrate, troubleshoot |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How the firmware and host software work, units, motor numbering |
| [docs/CAN_PROTOCOL.md](docs/CAN_PROTOCOL.md) | Every CAN frame the system uses, byte by byte |
| [docs/OPEN_ISSUES.md](docs/OPEN_ISSUES.md) | Known problems, untested assumptions, backlog |
| [HW_tests/CALIBRATION.md](HW_tests/CALIBRATION.md) | The per-motor calibration app |
| `CHANGES_<date>.md` | Dated session logs: what changed and *why*. Detailed history; the docs above are the summary |
| `memos/` | Original hardware notes (board schematic parts, pinouts, solved problems) |

## Repository map

```
Core/, Drivers/, Middlewares/,   STM32CubeMX-generated firmware skeleton (HAL, startup, USB).
USB_Device/, STM32_code.ioc      Edit Core/ only inside USER CODE blocks; .ioc is the CubeMX project.
App/                             Hand-written firmware: motor control, CAN handler, board config.
Makefile, run.sh                 Build (arm-none-eabi-gcc) and build+flash (openocd).
cantest/                         Host control app (Python, PySide6, python-can). Entry: main.py
HW_tests/                        Hardware test & calibration tools (calibration_app.py etc.)
lattice_code/                    Verilog for the on-board Lattice FPGA (PWM/DIR forwarding)
can_start_kvaser.sh              Bring up can0 on the Kvaser adapter  ← the one in daily use
can_start.sh                     Bring up can0 via an slcan (serial) adapter instead
memos/                           Hardware notes from board bring-up
cube.zsh                         Optional CubeMX launcher (see BENCH_GUIDE)
```
