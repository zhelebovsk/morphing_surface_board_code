REFACTORING = True

MOTOR_SPACING_MM = 10.0   # mm per motor index (Y axis)
BOARD_SPACING_MM = 10.0   # mm per board index (X axis)

BOARD_COUNT = 30

# Board n takes commands on 0x100+n and replies on 0x100+n+REPLY_ID_OFFSET. Firmware from
# before 2026-11-18 replied on 0x100+n; the host accepts both. Must match can_helper.h.
REPLY_ID_OFFSET = 0x80
MOTORS_PER_BOARD = 14

from pathlib import Path
MIN_LIMITS_FILE = str(Path(__file__).parent / "motor_min.csv")
CALIBRATION_FILE = str(Path(__file__).parent / "HW_tests" / "calibrations" / "latest.json")

DEFAULT_MIN_LIMIT = 100
MOTOR_RANGE = 150
DEFAULT_MIN_PWM = 20   # used for any board missing from CALIBRATION_FILE

FUNCTION_DESCRIPTION = "u(x, y, t)"

DYNAMIC_CYCLE_HZ = 0.1   # default μ: wave cycles per second (one cycle = 10 s)
DYNAMIC_MAX_HZ = 0.5     # μ cap; at 0.5 a full stroke takes 1 s
BLINK_DURATION_SEC = 0.10

UPDATE_HZ = 100.0