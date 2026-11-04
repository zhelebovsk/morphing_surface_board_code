REFACTORING = True

MOTOR_SPACING_MM = 10.0   # mm per motor index (Y axis)
BOARD_SPACING_MM = 10.0   # mm per board index (X axis)

BOARD_COUNT = 30
MOTORS_PER_BOARD = 14

from pathlib import Path
MIN_LIMITS_FILE = str(Path(__file__).parent / "motor_min.csv")
CALIBRATION_FILE = str(Path(__file__).parent.parent / "HW_tests" / "calibrations" / "latest.json")

DEFAULT_MIN_LIMIT = 100
MOTOR_RANGE = 150
DEFAULT_MIN_PWM = 20   # used for any board missing from CALIBRATION_FILE

FUNCTION_DESCRIPTION = "u(x, y, t)"

DYNAMIC_CYCLE_HZ = 1.0
BLINK_DURATION_SEC = 0.10

UPDATE_HZ = 100.0

# CAN FD: one 16-byte frame per board per cycle (opcode 0x07) instead of two
# classic frames. Must match CAN_FD_ENABLED in App/Inc/can_helper.h and
# `./can_start_kvaser.sh fd` (docs/OPEN_ISSUES.md #2).
CAN_FD = False