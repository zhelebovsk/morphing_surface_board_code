from config import BOARD_COUNT, MOTORS_PER_BOARD
from limits import load_all_limits
from engine import ControlMotor

from gui.setup_window import SetupWindow
from gui.main_window import MainWindow


if __name__ == "__main__":
    setup = SetupWindow()

    if setup.started:
        channel = setup.get_channel()
        min_limits, _ = load_all_limits()

        motor = ControlMotor(
            channel=channel,
            min_limits=min_limits,
            range_of_motion=255,
            board_count=BOARD_COUNT,
            motors_per_board=MOTORS_PER_BOARD,
        )

        app = MainWindow(motor)
        app.start()
