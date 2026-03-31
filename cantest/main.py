from config import BOARD_COUNT, MOTORS_PER_BOARD
from limits import load_all_limits
from engine import ControlMotor
# currently (Tkinter):
from gui2.setup_window import SetupWindow
from gui2.main_window import MainWindow

# switch to PySide6:
# from gui2.setup_window import SetupWindow
# from gui2.main_window import MainWindow

if __name__ == "__main__":
    setup = SetupWindow()

    if setup.started:
        channel = setup.get_channel()
        min_limits, max_limits = load_all_limits()

        motor = ControlMotor(
            channel=channel,
            min_limits=min_limits,
            max_limits=max_limits,
            range_of_motion=255,
            board_count=BOARD_COUNT,
            motors_per_board=MOTORS_PER_BOARD,
        )

        app = MainWindow(motor)
        app.start()
