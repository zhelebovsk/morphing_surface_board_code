from config import BOARD_COUNT, MOTORS_PER_BOARD
from limits import load_all_limits
from engine import ControlMotor

from gui.setup_window import SetupWindow
from gui.main_window import MainWindow


if __name__ == "__main__":
    setup = SetupWindow()

    if setup.started:
        channel = setup.get_channel()
        min_limits, _, _ = load_all_limits()

        motor = ControlMotor(
            channel=channel,
            min_limits=min_limits,
            range_of_motion=255,
            board_count=BOARD_COUNT,
            motors_per_board=MOTORS_PER_BOARD,
        )

        # ControlMotor already scanned during construction (and keeps
        # rescanning in the background) — no need to scan again here.
        found = sorted(motor.communication.active_boards)
        missing = [i for i in range(1, BOARD_COUNT + 1) if i not in found]
        if missing:
            print(f"WARNING: {len(missing)} board(s) not responding: {missing}")
        else:
            print(f"All {BOARD_COUNT} boards responding.")

        app = MainWindow(motor)
        app.start()
