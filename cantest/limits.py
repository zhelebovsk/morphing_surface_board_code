import os
import csv
from config import BOARD_COUNT, MOTORS_PER_BOARD, MIN_LIMITS_FILE, MAX_LIMITS_FILE, DEFAULT_MIN_LIMIT, DEFAULT_MAX_LIMIT
from utils import clamp8    

def create_default_limit_file(path, default_value):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["board"] + [f"m{i}" for i in range(1, MOTORS_PER_BOARD + 1)])
        for board in range(1, BOARD_COUNT + 1):
            writer.writerow([board] + [default_value] * MOTORS_PER_BOARD)


def load_limit_file(path, default_value):
    if not os.path.exists(path):
        create_default_limit_file(path, default_value)

    limits = [[default_value for _ in range(MOTORS_PER_BOARD)] for _ in range(BOARD_COUNT)]

    try:
        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        for board_index in range(min(BOARD_COUNT, len(rows) - 1)):
            row = rows[board_index + 1]

            for motor_index in range(MOTORS_PER_BOARD):
                cell_index = motor_index + 1  # col 0 is board number
                if cell_index < len(row):
                    try:
                        limits[board_index][motor_index] = clamp8(float(row[cell_index]))
                    except ValueError:
                        limits[board_index][motor_index] = default_value
    except OSError:
        pass

    return limits


def save_limit_file(path, limits):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["board"] + [f"m{i}" for i in range(1, MOTORS_PER_BOARD + 1)])
        for board_index, row in enumerate(limits):
            writer.writerow([board_index + 1] + [clamp8(v) for v in row])


def load_all_limits():
    min_limits = load_limit_file(MIN_LIMITS_FILE, DEFAULT_MIN_LIMIT)
    max_limits = load_limit_file(MAX_LIMITS_FILE, DEFAULT_MAX_LIMIT)

    for board in range(BOARD_COUNT):
        for motor in range(MOTORS_PER_BOARD):
            if min_limits[board][motor] > max_limits[board][motor]:
                min_limits[board][motor], max_limits[board][motor] = (
                    max_limits[board][motor],
                    min_limits[board][motor],
                )

    return min_limits, max_limits