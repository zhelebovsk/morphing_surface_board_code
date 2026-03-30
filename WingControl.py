import can
import os
from tkinter import (
    Tk, Toplevel, Frame, Canvas, Button, LEFT, RIGHT, BOTTOM, X, LabelFrame,
    Radiobutton, IntVar, DoubleVar, BooleanVar, StringVar, Label,
    Spinbox, OptionMenu, Scale, Checkbutton
)
from math import sin, pi, ceil

SCALING_FACTOR = 2.5

# calculates the locations of each motor in each wing
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

    def fill_from_function(self, func, t):
        for board in range(self.board_count):
            for motor in range(self.motors_per_board):
                raw = func(board, motor, t)
                scaled = raw * self.zero + self.zero + self.offset
                self.locations[board][motor] = scaled


class MotorCommunication:
    def __init__(self, channel):
        self.bus = None
        self.demo = (channel == "DEMO-MODE")

        if not self.demo:
            try:
                self.bus = can.interface.Bus(channel=channel, interface="socketcan")
            except OSError:
                print("CAN open failed, switching to demo mode")
                self.demo = True

    def send_frame(self, data, board_id):
        if self.demo:
            print(f"DEMO -> board {board_id}: {list(data)}")
            return

        msg = can.Message(
            arbitration_id=board_id + 0x100,
            data=data,
            is_extended_id=False
        )
        self.bus.send(msg, timeout=0.1)

    def send_positions(self, locations):
        board_count = len(locations)
        motors_per_board = len(locations[0])

        if motors_per_board != 14:
            print(f"ERROR: expected 14 motors per board, got {motors_per_board}")
            return

        for board_index in range(board_count):
            board_id = board_index + 1

            data_low = bytes(
                [1] +
                [max(0, min(255, int(locations[board_index][m]))) for m in range(7)]
            )
            data_high = bytes(
                [2] +
                [max(0, min(255, int(locations[board_index][m]))) for m in range(7, 14)]
            )

            self.send_frame(data_high, board_id)
            self.send_frame(data_low, board_id)

    def send_board_config(self, board_id, kp, ki, kd, alpha, limit_signal, deadband):
        data = bytes([
            3,
            max(0, min(255, int(kp))),
            max(0, min(255, int(ki))),
            max(0, min(255, int(kd))),
            max(0, min(255, int(alpha))),
            max(0, min(255, int(limit_signal))),
            max(0, min(255, int(deadband))),
            0
        ])
        self.send_frame(data, board_id)


class ControlGUI:
    MIN = 0
    ZERO = 1
    MAX = 2
    WAVE_X = 3
    WAVE_Y = 4
    WAVE_XY = 5
    HOUSE_SPECIAL = 6

    UPDATE_HZ = 100
    UPDATE_DT = 1.0 / UPDATE_HZ
    UPDATE_MS = int(1000 / UPDATE_HZ)

    MOTOR_SPACING_MM = 10.0

    def __init__(self, channel, range_of_motion, width=14, length=30, offset=0):
        self.board_count = length
        self.motors_per_board = width

        self.wing_control = WingControl(range_of_motion, length, width, offset)
        self.communication = MotorCommunication(channel)

        self.window = Tk()
        self.window.tk.call('tk', 'scaling', SCALING_FACTOR)  # try 1.5–2.5
        self.window.title("Motor Control")
        self.window.geometry("1650x900")
        self.window.resizable(True, True)

        self.main_area = Frame(self.window)
        self.main_area.pack(side="top", fill="both", expand=True)

        self.bottom_area = Frame(self.window)
        self.bottom_area.pack(side=BOTTOM, fill=X)

        self.choice = IntVar(value=self.ZERO)
        self.running = BooleanVar(value=False)
        self.step_index = 0

        self.fx = DoubleVar(value=0.5)
        self.fy = DoubleVar(value=0.5)

        default_lambda_x_mm = max(self.MOTOR_SPACING_MM, self.board_count * self.MOTOR_SPACING_MM)
        default_lambda_y_mm = max(self.MOTOR_SPACING_MM, self.motors_per_board * self.MOTOR_SPACING_MM)

        self.lambda_x = DoubleVar(value=default_lambda_x_mm)
        self.lambda_y = DoubleVar(value=default_lambda_y_mm)

        self.function_label_var = StringVar()
        self.speed_label_var = StringVar()
        self.update_info_label_var = StringVar(
            value=f"Update rate: {self.UPDATE_HZ} Hz   |   Delay: {self.UPDATE_MS} ms"
        )

        # default values to insert
        self.kp_value = IntVar(value=0)
        self.ki_value = IntVar(value=0)
        self.kd_value = IntVar(value=0)
        self.alpha_value = IntVar(value=0)
        self.limit_signal_value = IntVar(value=0)
        self.deadband_value = IntVar(value=0)

        self.motor_canvases = []

        self.build_left_panel()
        self.build_board_view()
        self.build_bottom_bar()
        self.refresh_motion_labels()
        self.recolor()

        self.window.update_idletasks()
        self.window.minsize(self.window.winfo_reqwidth(), self.window.winfo_reqheight())

    def board_to_mm(self, board_index):
        return board_index * self.MOTOR_SPACING_MM

    def motor_to_mm(self, motor_index):
        return motor_index * self.MOTOR_SPACING_MM

    # The left panel is controlling the function relevant data
    def build_left_panel(self):
        panel = Frame(self.main_area)
        panel.pack(side=LEFT, anchor="n", padx=10, pady=10)

        func_box = LabelFrame(panel, text="Function")
        func_box.pack(fill="x")

        options = [
            ("Min", self.MIN),
            ("Zero", self.ZERO),
            ("Max", self.MAX),
            ("Wave in X", self.WAVE_X),
            ("Wave in Y", self.WAVE_Y),
            ("Wave X * Wave Y", self.WAVE_XY),
            ("House special", self.HOUSE_SPECIAL),
        ]

        for text, value in options:
            Radiobutton(
                func_box,
                text=text,
                variable=self.choice,
                value=value,
                command=self.refresh_motion_labels
            ).pack(anchor="w")

        motion_box = LabelFrame(panel, text="Motion parameters")
        motion_box.pack(fill="x", pady=8)

        Label(motion_box, textvariable=self.update_info_label_var).pack(anchor="w", padx=6, pady=(4, 8))

        Label(motion_box, text="fx (Hz)").pack(anchor="w", padx=6)
        Scale(
            motion_box,
            from_=0.0,
            to=5.0,
            resolution=0.05,
            orient="horizontal",
            variable=self.fx,
            length=240,
            command=lambda _=None: self.refresh_motion_labels()
        ).pack()

        Label(motion_box, text="fy (Hz)").pack(anchor="w", padx=6)
        Scale(
            motion_box,
            from_=0.0,
            to=5.0,
            resolution=0.05,
            orient="horizontal",
            variable=self.fy,
            length=240,
            command=lambda _=None: self.refresh_motion_labels()
        ).pack()

        max_lambda_x_mm = max(self.MOTOR_SPACING_MM, self.board_count * self.MOTOR_SPACING_MM)
        max_lambda_y_mm = max(self.MOTOR_SPACING_MM, self.motors_per_board * self.MOTOR_SPACING_MM)

        Label(motion_box, text="λx (mm)").pack(anchor="w", padx=6)
        Spinbox(
            motion_box,
            from_=self.MOTOR_SPACING_MM,
            to=max_lambda_x_mm,
            increment=5.0,
            textvariable=self.lambda_x,
            width=10,
            command=self.refresh_motion_labels
        ).pack(anchor="w", padx=6, pady=(0, 6))

        Label(motion_box, text="λy (mm)").pack(anchor="w", padx=6)
        Spinbox(
            motion_box,
            from_=self.MOTOR_SPACING_MM,
            to=max_lambda_y_mm,
            increment=5.0,
            textvariable=self.lambda_y,
            width=10,
            command=self.refresh_motion_labels
        ).pack(anchor="w", padx=6, pady=(0, 6))

        info_box = LabelFrame(panel, text="Physics view")
        info_box.pack(fill="x", pady=8)

        Label(
            info_box,
            textvariable=self.function_label_var,
            justify="left",
            wraplength=260
        ).pack(anchor="w", padx=6, pady=(4, 6))

        Label(
            info_box,
            textvariable=self.speed_label_var,
            justify="left",
            wraplength=260
        ).pack(anchor="w", padx=6, pady=(0, 6))

        run_box = LabelFrame(panel, text="Run")
        run_box.pack(fill="x", pady=8)

        Button(run_box, text="Run statically", command=self.run_static).pack(fill="x", padx=4, pady=2)
        Button(run_box, text="Start dynamic", command=self.start_dynamic).pack(fill="x", padx=4, pady=2)
        Button(run_box, text="Stop dynamic", command=self.stop_dynamic).pack(fill="x", padx=4, pady=2)

    def build_board_view(self):
        board_frame = Frame(self.main_area)
        board_frame.pack(side=RIGHT, padx=10, pady=10, expand=True)

        canvas_size = max(16, ceil(min(620 / self.motors_per_board, 1200 / self.board_count)))

        # top-left empty corner
        Label(board_frame, text="", width=4).grid(row=0, column=0, padx=1, pady=1)

        # column numbers
        for board in range(self.board_count):
            Label(board_frame, text=str(board + 1), width=4).grid(
                row=0, column=board + 1, padx=1, pady=1
            )

        # row numbers + motor cells
        for motor in range(self.motors_per_board):
            Label(board_frame, text=str(motor + 1), width=4).grid(
                row=motor + 1, column=0, padx=1, pady=1
            )

            for board in range(self.board_count):
                c = Canvas(
                    board_frame,
                    width=canvas_size,
                    height=canvas_size,
                    bg="green",
                    highlightthickness=1,
                    highlightbackground="white"
                )
                c.grid(row=motor + 1, column=board + 1, padx=0, pady=0)
                self.motor_canvases.append(c)

    def build_bottom_bar(self):
        bottom_bar = LabelFrame(self.bottom_area, text="Board config packet")
        bottom_bar.pack(fill=X, padx=10, pady=10)

        sliders_frame = Frame(bottom_bar)
        sliders_frame.pack(side=LEFT, padx=8, pady=8)

        self.add_slider(sliders_frame, "Kp", self.kp_value)
        self.add_slider(sliders_frame, "Ki", self.ki_value)
        self.add_slider(sliders_frame, "Kd", self.kd_value)
        self.add_slider(sliders_frame, "Alpha", self.alpha_value)
        self.add_slider(sliders_frame, "Limit signal", self.limit_signal_value)
        self.add_slider(sliders_frame, "Deadband", self.deadband_value)

        buttons_frame = Frame(bottom_bar)
        buttons_frame.pack(side=LEFT, padx=16, pady=8)

        Button(buttons_frame, text="Send to all boards", command=self.send_config_to_all_boards).pack(fill=X, pady=2)
        Button(buttons_frame, text="Pick boards", command=self.open_pick_boards_window).pack(fill=X, pady=2)

    def add_slider(self, parent, title, variable):
        block = Frame(parent)
        block.pack(side=LEFT, padx=8)

        Label(block, text=title).pack()
        Scale(block, from_=0, to=255, orient="horizontal", variable=variable, length=170).pack()

    def get_wave_function(self):
        fx = max(0.0, self.fx.get())
        fy = max(0.0, self.fy.get())
        lambda_x_mm = max(0.001, self.lambda_x.get())
        lambda_y_mm = max(0.001, self.lambda_y.get())
        mode = self.choice.get()

        if mode == self.MIN:
            return lambda board, motor, t: -1.0
        if mode == self.ZERO:
            return lambda board, motor, t: 0.0
        if mode == self.MAX:
            return lambda board, motor, t: 1.0
        if mode == self.WAVE_X:
            return lambda board, motor, t: sin(
                2 * pi * ((self.board_to_mm(board) / lambda_x_mm) - fx * t)
            )
        if mode == self.WAVE_Y:
            return lambda board, motor, t: sin(
                2 * pi * ((self.motor_to_mm(motor) / lambda_y_mm) - fy * t)
            )
        if mode == self.WAVE_XY:
            return lambda board, motor, t: (
                sin(2 * pi * ((self.board_to_mm(board) / lambda_x_mm) - fx * t)) *
                sin(2 * pi * ((self.motor_to_mm(motor) / lambda_y_mm) - fy * t))
            )

        #CUSTOM - here you make your custom function, as board is 'the x axis' and motor is 'the y axis'
        if mode == self.HOUSE_SPECIAL:
            return lambda board, motor, t: sin(board*motor*t)

        return lambda board, motor, t: 0.0

    def refresh_motion_labels(self):
        fx = max(0.0, self.fx.get())
        fy = max(0.0, self.fy.get())
        lambda_x_mm = max(0.001, self.lambda_x.get())
        lambda_y_mm = max(0.001, self.lambda_y.get())
        mode = self.choice.get()

        if mode == self.MIN:
            self.function_label_var.set("Function:\nu(x,y,t) = -1")
            self.speed_label_var.set("Speed:\nStatic field")
        elif mode == self.ZERO:
            self.function_label_var.set("Function:\nu(x,y,t) = 0")
            self.speed_label_var.set("Speed:\nStatic field")
        elif mode == self.MAX:
            self.function_label_var.set("Function:\nu(x,y,t) = 1")
            self.speed_label_var.set("Speed:\nStatic field")
        elif mode == self.WAVE_X:
            self.function_label_var.set(
                f"Function:\nu(x,t) = sin(2π(x/λx - fx·t))\n"
                f"λx = {lambda_x_mm:.2f} mm,   fx = {fx:.2f} Hz"
            )
            self.speed_label_var.set(
                f"Derived speed:\nvx = fx·λx = {fx:.2f} · {lambda_x_mm:.2f} = {fx * lambda_x_mm:.2f} mm/s"
            )
        elif mode == self.WAVE_Y:
            self.function_label_var.set(
                f"Function:\nu(y,t) = sin(2π(y/λy - fy·t))\n"
                f"λy = {lambda_y_mm:.2f} mm,   fy = {fy:.2f} Hz"
            )
            self.speed_label_var.set(
                f"Derived speed:\nvy = fy·λy = {fy:.2f} · {lambda_y_mm:.2f} = {fy * lambda_y_mm:.2f} mm/s"
            )
        elif mode == self.WAVE_XY:
            self.function_label_var.set(
                "Function:\n"
                "u(x,y,t) = sin(2π(x/λx - fx·t)) · sin(2π(y/λy - fy·t))\n"
                f"λx = {lambda_x_mm:.2f} mm, fx = {fx:.2f} Hz, "
                f"λy = {lambda_y_mm:.2f} mm, fy = {fy:.2f} Hz"
            )
            self.speed_label_var.set(
                f"Derived speeds:\n"
                f"vx = {fx * lambda_x_mm:.2f} mm/s\n"
                f"vy = {fy * lambda_y_mm:.2f} mm/s"
            )
        elif mode == self.HOUSE_SPECIAL:
            self.function_label_var.set("Function:\nHouse special = 0\n(edit in code)")
            self.speed_label_var.set("Speed:\nDefined by programmer")
        else:
            self.function_label_var.set("Function:\nu(x,y,t) = 0")
            self.speed_label_var.set("Speed:\nStatic field")

    def recolor(self):
        counter = 0
        for motor in range(self.wing_control.motors_per_board):
            for board in range(self.wing_control.board_count):
                grayscale = round(
                    255 *
                    (self.wing_control.locations[board][motor] - self.wing_control.offset)
                    / (self.wing_control.zero * 2)
                )
                grayscale = max(0, min(255, grayscale))
                hex_value = f"{grayscale:02x}"
                self.motor_canvases[counter]["bg"] = "#" + hex_value * 3
                counter += 1

    def push_positions(self):
        self.communication.send_positions(self.wing_control.locations)
        self.recolor()

    def run_static(self):
        func = self.get_wave_function()
        self.wing_control.fill_from_function(func, t=0.0)
        self.push_positions()

    def start_dynamic(self):
        if self.running.get():
            return
        self.running.set(True)
        self.step_index = 0
        self.run_dynamic_step()

    def run_dynamic_step(self):
        if not self.running.get():
            return

        t = self.step_index * self.UPDATE_DT
        func = self.get_wave_function()
        self.wing_control.fill_from_function(func, t)
        self.push_positions()

        self.step_index += 1
        self.window.after(self.UPDATE_MS, self.run_dynamic_step)

    def stop_dynamic(self):
        self.running.set(False)

    def build_config_values(self):
        return (
            self.kp_value.get(),
            self.ki_value.get(),
            self.kd_value.get(),
            self.alpha_value.get(),
            self.limit_signal_value.get(),
            self.deadband_value.get()
        )

    def send_config_to_all_boards(self):
        kp, ki, kd, alpha, limit_signal, deadband = self.build_config_values()
        for board_id in range(1, self.board_count + 1):
            self.communication.send_board_config(
                board_id, kp, ki, kd, alpha, limit_signal, deadband
            )

    def open_pick_boards_window(self):
        pick_window = Toplevel(self.window)
        pick_window.title("Pick boards")
        pick_window.resizable(False, False)

        checks_frame = Frame(pick_window)
        checks_frame.pack(padx=10, pady=10)

        board_vars = []
        for board_index in range(self.board_count):
            var = BooleanVar(value=False)
            board_vars.append(var)

            Checkbutton(
                checks_frame,
                text=f"Board {board_index + 1}",
                variable=var
            ).grid(row=board_index // 4, column=board_index % 4, sticky="w", padx=8, pady=3)

        def send_selected():
            kp, ki, kd, alpha, limit_signal, deadband = self.build_config_values()
            for board_index, var in enumerate(board_vars):
                if var.get():
                    self.communication.send_board_config(
                        board_index + 1, kp, ki, kd, alpha, limit_signal, deadband
                    )
            pick_window.destroy()

        buttons = Frame(pick_window)
        buttons.pack(pady=(0, 10))

        Button(buttons, text="Send", command=send_selected).pack(side=LEFT, padx=5)
        Button(buttons, text="Cancel", command=pick_window.destroy).pack(side=LEFT, padx=5)

    def start(self):
        self.window.mainloop()


class SetupGUI:
    def __init__(self):
        channels = ["DEMO-MODE"]

        try:
            for name in os.listdir("/sys/class/net"):
                if name.startswith(("can", "vcan", "slcan")):
                    channels.append(name)
        except OSError:
            pass

        self.window = Tk()
        self.window.tk.call('tk', 'scaling', SCALING_FACTOR)  # try 1.5–2.5
        self.window.title("GUI setup")
        self.window.geometry("960x120")
        self.window.resizable(False, False)

        self.channel_choice = StringVar(value=channels[0])
        self.width_choice = IntVar(value=14)
        self.length_choice = IntVar(value=30)
        self.started = False

        Label(self.window, text="CAN channel:").pack(side=LEFT, padx=4, pady=8)
        OptionMenu(self.window, self.channel_choice, *channels).pack(side=LEFT, padx=4, pady=8)

        Label(self.window, text="Width:").pack(side=LEFT, padx=4, pady=8)
        Spinbox(
            self.window,
            from_=1,
            to=50,
            increment=1,
            textvariable=self.width_choice,
            width=4
        ).pack(side=LEFT, padx=4, pady=8)

        Label(self.window, text="Length:").pack(side=LEFT, padx=4, pady=8)
        Spinbox(
            self.window,
            from_=1,
            to=82,
            increment=1,
            textvariable=self.length_choice,
            width=4
        ).pack(side=LEFT, padx=4, pady=8)

        Button(self.window, text="Start", command=self.on_start).pack(side=LEFT, padx=8, pady=8)
        self.window.mainloop()

    def on_start(self):
        self.started = True
        self.window.destroy()

    def get(self):
        return self.channel_choice.get(), self.width_choice.get(), self.length_choice.get()


if __name__ == "__main__":
    setup = SetupGUI()

    if setup.started:
        channel, width, length = setup.get()

        app = ControlGUI(
            channel=channel,
            range_of_motion=255,
            width=int(width),
            length=int(length)
        )
        app.start()
