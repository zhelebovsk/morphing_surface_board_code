import can
import os
from tkinter import (
    Tk, Toplevel, Frame, Canvas, Button, LEFT, RIGHT, BOTTOM, X, LabelFrame,
    Radiobutton, IntVar, Entry, messagebox, Label,
    Spinbox, BooleanVar, StringVar, OptionMenu, Scale, Checkbutton
)
from math import sin, pi, ceil


class WingControl:
    def __init__(self, range_of_motion, x_size, y_size, offset=0):
        self.zero = range_of_motion / 2
        self.locations = []
        self.x_size = x_size   # board index
        self.y_size = y_size   # motor index inside board
        self.offset = offset

        for x in range(x_size):
            self.locations.append([self.zero + offset] * y_size)

    def selfZero(self):
        for x in range(self.x_size):
            for y in range(self.y_size):
                self.locations[x][y] = self.zero + self.offset

    def assembleFunction(self, xy_func, x_increment, y_increment, x_start=0, y_start=0):
        for x in range(self.x_size):
            for y in range(self.y_size):
                raw_func_value = xy_func(
                    x_start + (x * x_increment),
                    y_start + (y * y_increment)
                )
                scaled_value = raw_func_value * self.zero + self.zero + self.offset
                self.locations[x][y] = scaled_value


class MotorCommunication:
    def __init__(self, port):
        self.bus = None
        self.demo = (port == "DEMO-MODE")

        if not self.demo:
            try:
                self.bus = can.interface.Bus(channel=port, interface="socketcan")
            except OSError:
                print("Your CAN sucks")
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

    def send(self, locations):
        board_count = len(locations)
        motors_per_board = len(locations[0])

        if motors_per_board != 14:
            print(f"ERROR: expected 14 motors per board, got {motors_per_board}")
            return

        for board_index in range(board_count):
            board_id = board_index + 1

            data1 = bytes(
                [1] +
                [max(0, min(255, int(locations[board_index][motor]))) for motor in range(7)]
            )

            data2 = bytes(
                [2] +
                [max(0, min(255, int(locations[board_index][motor]))) for motor in range(7, 14)]
            )

            self.send_frame(data2, board_id)
            self.send_frame(data1, board_id)

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
    SIN_X = 3
    SIN_Y = 4
    SIN_X_SIN_Y = 5
    CUSTOM = 6

    def __init__(self, port, range_of_motion, width=14, length=30, offset=0):
        self.wing_control = WingControl(range_of_motion, length, width, offset)
        self.communication = MotorCommunication(port)
        self.board_count = length

        self.window = Tk()
        self.window.title("Motor Control")
        self.window.geometry("1600x850")
        self.window.resizable(True, True)

        self.main_area = Frame(self.window)
        self.main_area.pack(side="top", fill="both", expand=True)

        self.bottom_area = Frame(self.window)
        self.bottom_area.pack(side="bottom", fill="x")

        self.motor_representation = []
        self.dynamic_on = []
        self.dynamic_off = []
        self.choice = IntVar(value=self.ZERO)
        self.dynamically_running = BooleanVar(value=False)

        self.kp_value = IntVar(value=0)
        self.ki_value = IntVar(value=0)
        self.kd_value = IntVar(value=0)
        self.alpha_value = IntVar(value=0)
        self.limit_signal_value = IntVar(value=0)
        self.deadband_value = IntVar(value=0)

        self.control_panel_setup()
        self.visual_motor_setup(width, length)
        self.bottom_bar_setup()

        self.window.update_idletasks()
        self.window.minsize(
            self.window.winfo_reqwidth(),
            self.window.winfo_reqheight()
        )

    def control_panel_setup(self):
        control_panel = Frame(self.main_area)
        control_panel.pack(side=LEFT, anchor="n", padx=8, pady=8)

        func_options = LabelFrame(control_panel, text="function options")
        func_options.pack(fill="x")

        function_options = [
            ("min", self.MIN),
            ("zero", self.ZERO),
            ("max", self.MAX),
            ("sin x", self.SIN_X),
            ("sin y", self.SIN_Y),
            ("sin x * sin y", self.SIN_X_SIN_Y),
            ("custom", self.CUSTOM),
        ]

        for text, value in function_options:
            Radiobutton(func_options, text=text, variable=self.choice, value=value).pack(anchor="w")

        self.custom_entry = Entry(func_options)
        self.custom_entry.pack(fill="x")
        self.dynamic_off.append(self.custom_entry)

        run_options = LabelFrame(control_panel, text="run options")
        run_options.pack(fill="x", pady=6)

        static_btn = Button(run_options, text="run statically", command=self.runStatic)
        static_btn.pack(fill="x")
        self.dynamic_off.append(static_btn)

        Label(run_options, text="delay(ms):").pack()

        self.delay_val = Spinbox(run_options, from_=5, to=20000, increment=5)
        self.delay_val.pack(fill="x")

        dynamic_start_btn = Button(
            run_options,
            text="start running dynamically",
            command=lambda: self.startDynamic(int(self.delay_val.get()))
        )
        dynamic_start_btn.pack(fill="x")
        self.dynamic_off.append(dynamic_start_btn)

        dynamic_stop_btn = Button(
            run_options,
            text="stop running dynamically",
            state="disabled",
            command=self.stopDynamic
        )
        dynamic_stop_btn.pack(fill="x")
        self.dynamic_on.append(dynamic_stop_btn)

        advanced_options = LabelFrame(control_panel, text="advanced options")
        advanced_options.pack(fill="x", pady=6)

        motor_increment_options = LabelFrame(advanced_options, text="motor increments")
        motor_increment_options.pack(fill="x")

        Label(motor_increment_options, text="x axis:").pack()
        self.x_motor_increment = Entry(motor_increment_options)
        self.x_motor_increment.insert(0, "pi/12")
        self.x_motor_increment.pack(fill="x")

        Label(motor_increment_options, text="y axis:").pack()
        self.y_motor_increment = Entry(motor_increment_options)
        self.y_motor_increment.insert(0, "pi/12")
        self.y_motor_increment.pack(fill="x")

        time_increment_options = LabelFrame(advanced_options, text="time increments")
        time_increment_options.pack(fill="x", pady=6)

        Label(time_increment_options, text="x axis:").pack()
        self.x_time_increment = Entry(time_increment_options)
        self.x_time_increment.insert(0, "pi/12")
        self.x_time_increment.pack(fill="x")

        Label(time_increment_options, text="y axis:").pack()
        self.y_time_increment = Entry(time_increment_options)
        self.y_time_increment.insert(0, "pi/12")
        self.y_time_increment.pack(fill="x")

    def visual_motor_setup(self, width, length):
        visual_motors = Frame(self.main_area)
        visual_motors.pack(side=RIGHT, padx=8, pady=8, expand=True)

        canvas_size = max(14, ceil(min(560 / width, 1120 / length)))

        for y_count in range(width):
            for x_count in range(length):
                canvas = Canvas(
                    visual_motors,
                    height=canvas_size,
                    width=canvas_size,
                    bg="green",
                    highlightthickness=1,
                    highlightbackground="white"
                )
                canvas.grid(row=y_count, column=x_count, padx=0, pady=0, ipadx=0, ipady=0)
                self.motor_representation.append(canvas)

    def add_slider(self, parent, title, variable):
        slider_frame = Frame(parent)
        slider_frame.pack(side=LEFT, padx=10, pady=5)

        Label(slider_frame, text=title).pack()
        Scale(
            slider_frame,
            from_=0,
            to=255,
            orient="horizontal",
            variable=variable,
            length=180
        ).pack()

    def bottom_bar_setup(self):
        bottom_bar = LabelFrame(self.bottom_area, text="Board config")
        bottom_bar.pack(fill=X, padx=8, pady=8)

        sliders_frame = Frame(bottom_bar)
        sliders_frame.pack(side=LEFT, padx=10, pady=5)

        self.add_slider(sliders_frame, "Kp", self.kp_value)
        self.add_slider(sliders_frame, "Ki", self.ki_value)
        self.add_slider(sliders_frame, "Kd", self.kd_value)
        self.add_slider(sliders_frame, "Alpha", self.alpha_value)
        self.add_slider(sliders_frame, "Limit signal", self.limit_signal_value)
        self.add_slider(sliders_frame, "Deadband", self.deadband_value)

        buttons_frame = Frame(bottom_bar)
        buttons_frame.pack(side=LEFT, padx=15, pady=5)

        Button(
            buttons_frame,
            text="Send to all boards",
            command=self.send_config_to_all_boards
        ).pack(fill=X, pady=2)

        Button(
            buttons_frame,
            text="Pick boards",
            command=self.open_pick_boards_window
        ).pack(fill=X, pady=2)

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
                        board_index + 1,
                        kp, ki, kd, alpha, limit_signal, deadband
                    )

            pick_window.destroy()

        buttons_frame = Frame(pick_window)
        buttons_frame.pack(pady=(0, 10))

        Button(buttons_frame, text="Send", command=send_selected).pack(side=LEFT, padx=5)
        Button(buttons_frame, text="Cancel", command=pick_window.destroy).pack(side=LEFT, padx=5)

    def functionParser(self):
        if self.choice.get() == self.MIN:
            return lambda x, y: -1
        elif self.choice.get() == self.ZERO:
            return lambda x, y: 0
        elif self.choice.get() == self.MAX:
            return lambda x, y: 1
        elif self.choice.get() == self.SIN_X:
            return lambda x, y: sin(x)
        elif self.choice.get() == self.SIN_Y:
            return lambda x, y: sin(y)
        elif self.choice.get() == self.SIN_X_SIN_Y:
            return lambda x, y: sin(x) * sin(y)
        elif self.choice.get() == self.CUSTOM:
            return lambda x, y: eval(self.custom_entry.get())
        else:
            messagebox.showwarning(
                "Function Choice Error",
                "An error has occurred while trying to parse the radio box data.\n"
                "Falling back to zero."
            )
            return lambda x, y: 0

    def recolor(self):
        counter = 0
        for y in range(self.wing_control.y_size):
            for x in range(self.wing_control.x_size):
                grayscale = round(
                    255 *
                    (self.wing_control.locations[x][y] - self.wing_control.offset)
                    / (self.wing_control.zero * 2)
                )
                grayscale = max(0, min(255, grayscale))
                value_hex = f"{grayscale:02x}"
                self.motor_representation[counter]["bg"] = "#" + value_hex * 3
                counter += 1

    def update(self):
        self.communication.send(self.wing_control.locations)
        self.recolor()

    def runStatic(self):
        func = self.functionParser()

        try:
            x_inc = eval(self.x_motor_increment.get())
        except Exception as exception:
            messagebox.showwarning(
                "x Motor Increment Error",
                "An error has occurred while trying to calculate the x motor increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            x_inc = pi / 12

        try:
            y_inc = eval(self.y_motor_increment.get())
        except Exception as exception:
            messagebox.showwarning(
                "y Motor Increment Error",
                "An error has occurred while trying to calculate the y motor increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            y_inc = pi / 12

        try:
            self.wing_control.assembleFunction(func, x_inc, y_inc)
        except Exception as exception:
            messagebox.showwarning(
                "Custom Function Error",
                "An error has occurred while trying to calculate the motor values.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            self.wing_control.selfZero()

        self.update()

    def startDynamic(self, delay):
        for widget in self.dynamic_on:
            widget["state"] = "normal"
        for widget in self.dynamic_off:
            widget["state"] = "disabled"

        self.dynamically_running.set(True)
        func = self.functionParser()

        try:
            x_motor_inc = eval(self.x_motor_increment.get())
        except Exception as exception:
            messagebox.showwarning(
                "x Motor Increment Error",
                "An error has occurred while trying to calculate the x motor increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            x_motor_inc = pi / 12

        try:
            y_motor_inc = eval(self.y_motor_increment.get())
        except Exception as exception:
            messagebox.showwarning(
                "y Motor Increment Error",
                "An error has occurred while trying to calculate the y motor increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            y_motor_inc = pi / 12

        try:
            x_time_inc = eval(self.x_time_increment.get())
        except Exception as exception:
            messagebox.showwarning(
                "x Time Increment Error",
                "An error has occurred while trying to calculate the x time increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            x_time_inc = pi / 12

        try:
            y_time_inc = eval(self.y_time_increment.get())
        except Exception as exception:
            messagebox.showwarning(
                "y Time Increment Error",
                "An error has occurred while trying to calculate the y time increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            y_time_inc = pi / 12

        self.runDynamic(func, delay, x_motor_inc, y_motor_inc, x_time_inc, y_time_inc)

    def runDynamic(self, func, delay, x_motor_inc, y_motor_inc, x_time_inc, y_time_inc, shift=0):
        try:
            self.wing_control.assembleFunction(
                func,
                x_motor_inc,
                y_motor_inc,
                shift * x_time_inc,
                shift * y_time_inc
            )
        except Exception as exception:
            messagebox.showwarning(
                "Custom Function Error",
                "An error has occurred while trying to calculate the motor values.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            self.wing_control.selfZero()
            self.choice.set(self.ZERO)
            self.stopDynamic()

        self.update()

        if self.dynamically_running.get():
            self.window.after(
                delay,
                lambda: self.runDynamic(
                    func, delay,
                    x_motor_inc, y_motor_inc,
                    x_time_inc, y_time_inc,
                    shift + 1
                )
            )

    def stopDynamic(self):
        for widget in self.dynamic_on:
            widget["state"] = "disabled"
        for widget in self.dynamic_off:
            widget["state"] = "normal"
        self.dynamically_running.set(False)

    def start(self):
        self.window.mainloop()


class SetupGUI:
    def __init__(self):
        ports_list = ["DEMO-MODE"]

        try:
            for name in os.listdir("/sys/class/net"):
                if name.startswith(("can", "vcan", "slcan")):
                    ports_list.append(name)
        except OSError:
            pass

        self.setting_popup = Tk()
        self.setting_popup.title("gui setup")
        self.setting_popup.geometry("500x70")
        self.setting_popup.resizable(False, False)

        self.com_choice = StringVar()
        self.width_choice = IntVar()
        self.length_choice = IntVar()
        self.start_flag = False

        self.visuals(ports_list)
        self.setting_popup.mainloop()

    def visuals(self, port_list):
        Label(self.setting_popup, text="CAN channel: ").pack(side=LEFT)

        self.com_choice.set(port_list[0])
        OptionMenu(self.setting_popup, self.com_choice, *port_list).pack(side=LEFT)

        Label(self.setting_popup, text="Width: ").pack(side=LEFT)
        self.width_choice.set(14)
        Spinbox(
            self.setting_popup,
            from_=1, to=50, increment=1,
            textvariable=self.width_choice,
            width=3
        ).pack(side=LEFT)

        Label(self.setting_popup, text="Length: ").pack(side=LEFT)
        self.length_choice.set(30)
        Spinbox(
            self.setting_popup,
            from_=1, to=82, increment=1,
            textvariable=self.length_choice,
            width=3
        ).pack(side=LEFT)

        Button(self.setting_popup, text="Start", command=self.start_btn_cmd).pack(side=LEFT)

    def start_btn_cmd(self):
        self.start_flag = True
        self.setting_popup.destroy()

    def get(self):
        return self.com_choice.get(), self.width_choice.get(), self.length_choice.get()


if __name__ == "__main__":
    setup = SetupGUI()

    if setup.start_flag:
        port, width, length = setup.get()

        app = ControlGUI(
            port=port,
            range_of_motion=255,
            width=int(width),
            length=int(length)
        )
        app.start()
