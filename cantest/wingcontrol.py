from config import BOARD_SPACING_MM, MOTOR_SPACING_MM

class WingControl:
    def __init__(self, range_of_motion, board_count, motors_per_board, offset=0):
        self.zero = range_of_motion / 2
        self.board_count = board_count
        self.motors_per_board = motors_per_board
        self.offset = offset
        self.locations = [
            [self.zero + offset for _ in range(motors_per_board)]
            for _ in range(board_count)
        ]
        self.x_center = (board_count - 1) / 2
        self.y_center = (motors_per_board - 1) / 2

    def fill_from_function(self, func, t):
        new_locations = []
        for board in range(self.board_count):
            x_mm = (board - self.x_center) * BOARD_SPACING_MM
            row = []
            for motor in range(self.motors_per_board):
                y_mm = (self.y_center - motor) * MOTOR_SPACING_MM
                raw = func(x_mm, y_mm, t)
                row.append(raw * self.zero + self.zero + self.offset)
            new_locations.append(row)
        self.locations = new_locations