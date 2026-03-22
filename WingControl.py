import can
import os
from tkinter import (
    Tk, Frame, Canvas, Button, LEFT, RIGHT, LabelFrame,
    Radiobutton, IntVar, Entry, messagebox, Label,
    Spinbox, BooleanVar, StringVar, OptionMenu, Toplevel, Scale, HORIZONTAL
)
from math import sin, pi, ceil

#This class calculated the changes in the (simulation) board
class WingControl:

    def __init__(self, range_of_motion, x_size, y_size, offset=0):
        self.zero = range_of_motion / 2
        self.locations = []
        self.x_size = x_size   # x = board index
        self.y_size = y_size   # y = motor index inside board
        self.offset = offset

        for x in range(x_size):
            self.locations.append([self.zero + offset] * y_size)

    def selfZero(self):
        for x in range(self.x_size):
            for y in range(self.y_size):
                self.locations[x][y] = self.zero + self.offset

    def assembleFunction(self, xy_func, x_increment, y_increment, x_start=0, y_start=0):
        # locations[x][y] : x = board , y = motor inboard
        for x in range(self.x_size):
            for y in range(self.y_size):
                raw_func_value = xy_func(x_start + (x * x_increment),y_start + (y * y_increment))
                scaled_value = raw_func_value * self.zero + self.zero + self.offset
                self.locations[x][y] = scaled_value


#
class MotorCommunication:
    def __init__(self, chan):
        self.bus = None
        self.demo = (chan == "DEMO-MODE")

        if not self.demo:
            try:
                self.bus = can.interface.Bus(channel=chan, interface="socketcan")
            except OSError:
                print("Your CAN sucks")
                self.demo = True

    def send_frame(self, data, board_id):

        if not self.demo:
            msg = can.Message(arbitration_id=board_id + 0x100,data=data,is_extended_id=False)
            self.bus.send(msg, timeout=0.1)
        else:
            print(can.Message(arbitration_id=board_id + 0x100,data=data,is_extended_id=False))

    def send_motor_speed_packet(self, board_id, motor_speeds, motor_index, is_up):
        if motor_index < 7: #
            motor_range = range(7)
            command = 5 if is_up else 7
        else:
            motor_range = range(7, 14)
            command = 6 if is_up else 8

        if is_up:
            values = [max(0, min(255, int(motor_speeds[board_id - 1][m]["up"])))
                for m in motor_range
            ]
        else:
            values = [max(0, min(255, int(motor_speeds[board_id - 1][m]["down"])))
                          for m in motor_range
            ]

        self.send_frame(bytes([command] + values), board_id)



    def send(self, locations):
        #one board = one column of 14 motors, locations represented as [board][motor]
        board_count = len(locations)
        motors_per_board = len(locations[0])

        if motors_per_board != 14:
            print(f"ERROR: expected 14 motors per board, got {motors_per_board}")
            return

        for board_index in range(board_count):
            board_id = board_index + 1

            #first packet: first byte is 14 + motors 0..6
            data1 = bytes([14] +
                [max(0, min(255, int(locations[board_index][motor]))) for motor in range(7)])

            #second packet: first byte is 15 + motors 7...13
            data2 = bytes([15] +
                [max(0, min(255, int(locations[board_index][motor]))) for motor in range(7, 14)])

            if self.bus != "DEMO":
                # send data2 first, then data1
                self.send_frame(data2, board_id)
                self.send_frame(data1, board_id)




class ControlGUI:
    #Constants for function choice
    MIN = 0
    ZERO = 1
    MAX = 2
    SIN_X = 3
    SIN_Y = 4
    SIN_X_SIN_Y = 5
    CUSTOM = 6

    def __init__(self, chan, range_of_motion, width=14, length=30, offset=0):

        #locations represented as [board][motor]
        self.wing_control = WingControl(range_of_motion, length, width, offset)
        self.communication = MotorCommunication(chan)

        self.window = Tk()
        self.window.title("Motor Control")
        #self.window.geometry("1136x612")
        self.window.resizable(False, False)

        self.motor_representation = []
        self.dynamic_on = []
        self.dynamic_off = []
        self.choice = IntVar(value=self.ZERO)
        self.dynamically_running = BooleanVar()

        self.control_panel_setup()
        self.visual_motor_setup(width, length)

        self.motor_speeds = [[{"up": 50, "down": 50} for _ in range(width)]for _ in range(length)]

    def control_panel_setup(self):
        control_panel = Frame(self.window, name="control_panel")
        control_panel.pack(side=LEFT)

        func_options = LabelFrame(control_panel, text="function options", name="func_options")
        func_options.pack()

        function_options = []

        function_options.append(Radiobutton(func_options, text="min", variable=self.choice, value=self.MIN))
        function_options.append(Radiobutton(func_options, text="zero", variable=self.choice, value=self.ZERO))
        function_options.append(Radiobutton(func_options, text="max", variable=self.choice, value=self.MAX))
        function_options.append(Radiobutton(func_options, text="sin x", variable=self.choice, value=self.SIN_X))
        function_options.append(Radiobutton(func_options, text="sin y", variable=self.choice, value=self.SIN_Y))
        function_options.append(Radiobutton(func_options, text="sin x * sin y", variable=self.choice, value=self.SIN_X_SIN_Y))
        function_options.append(Radiobutton(func_options, text="custom", variable=self.choice, value=self.CUSTOM))

        for radio_button in function_options:
            radio_button.pack()

        custom = Entry(func_options, name="custom")
        custom.pack()
        self.dynamic_off.append(custom)

        run_options = LabelFrame(control_panel, text="run options", name="run_options")
        run_options.pack()

        static_btn = Button(run_options, text="run statically", command=lambda: self.runStatic())
        static_btn.pack()
        self.dynamic_off.append(static_btn)

        self.dynamically_running = BooleanVar()

        dynamic_start_btn = Button(
            run_options,
            text="start running dynamically",
            command=lambda: self.startDynamic(int(delay_val.get()))
        )
        dynamic_start_btn.pack()
        self.dynamic_off.append(dynamic_start_btn)

        dynamic_stop_btn = Button(
            run_options,
            text="stop running dynamically",
            state="disabled",
            command=lambda: self.stopDynamic()
        )
        dynamic_stop_btn.pack()
        self.dynamic_on.append(dynamic_stop_btn)

        delay_lbl = Label(run_options, text="delay(ms):")
        delay_lbl.pack()

        delay_val = Spinbox(run_options, from_=5, to=20000, increment=5, name="delay_val")
        delay_val.pack()

        advanced_options = LabelFrame(control_panel, text="advanced options", name="advanced_options")
        advanced_options.pack()

        motor_increment_options = LabelFrame(
            advanced_options,
            text="motor increments",
            name="motor_increment_options"
        )
        motor_increment_options.pack()

        x_motor_lbl = Label(motor_increment_options, text="x axis:")
        x_motor_lbl.pack()
        x_motor_increment = Entry(motor_increment_options, name="x_motor_increment")
        x_motor_increment.insert(0, "pi/12")
        x_motor_increment.pack()

        y_motor_lbl = Label(motor_increment_options, text="y axis:")
        y_motor_lbl.pack()
        y_motor_increment = Entry(motor_increment_options, name="y_motor_increment")
        y_motor_increment.insert(0, "pi/12")
        y_motor_increment.pack()

        time_increment_options = LabelFrame(
            advanced_options,
            text="time increments",
            name="time_increment_options"
        )
        time_increment_options.pack()

        x_time_lbl = Label(time_increment_options, text="x axis:")
        x_time_lbl.pack()
        x_time_increment = Entry(time_increment_options, name="x_time_increment")
        x_time_increment.insert(0, "pi/12")
        x_time_increment.pack()

        y_time_lbl = Label(time_increment_options, text="y axis:")
        y_time_lbl.pack()
        y_time_increment = Entry(time_increment_options, name="y_time_increment")
        y_time_increment.insert(0, "pi/12")
        y_time_increment.pack()

    def visual_motor_setup(self, width, length):
        visual_motors = Frame(self.window)
        visual_motors.pack(side=RIGHT)

        self.motor_representation = []
        canvas_size = ceil(min((375 / width), (750 / length)))

        for motor_index in range(width):
            row_list = []
            for board_index in range(length):
                canvas = Canvas(
                    visual_motors,
                    height=canvas_size,
                    width=canvas_size,
                    bg="green"
                )
                canvas.grid(row=motor_index, column=board_index, padx=0, pady=0, ipadx=0, ipady=0)
                canvas.bind(
                    "<Button>",
                    lambda event, b=board_index, m=motor_index: self.open_motor_speed_window(b, m)
                )
                row_list.append(canvas)
            self.motor_representation.append(row_list)

    def functionParser(self):
        if self.choice.get() == self.MIN:
            func = lambda x, y: -1
        elif self.choice.get() == self.ZERO:
            func = lambda x, y: 0
        elif self.choice.get() == self.MAX:
            func = lambda x, y: 1
        elif self.choice.get() == self.SIN_X:
            func = lambda x, y: sin(x)
        elif self.choice.get() == self.SIN_Y:
            func = lambda x, y: sin(y)
        elif self.choice.get() == self.SIN_X_SIN_Y:
            func = lambda x, y: sin(x) * sin(y)
        elif self.choice.get() == self.CUSTOM:
            # still uses eval, this is not safe for untrusted input
            func = lambda x, y: eval(
                self.window.children.get("control_panel")
                .children.get("func_options")
                .children.get("custom").get()
            )
        else:
            messagebox.showwarning(
                "Function Choice Error",
                "An error has occurred while trying to parse the radio box data.\n"
                "Falling back to zero."
            )
            func = lambda x, y: 0
        return func

    def recolor(self):
        for motor_index in range(self.wing_control.y_size):
            for board_index in range(self.wing_control.x_size):
                grayscale = round(
                    255 *
                    (self.wing_control.locations[board_index][motor_index] - self.wing_control.offset)
                    / (self.wing_control.zero * 2)
                )
                grayscale = max(0, min(255, grayscale))
                hex_value = f"{grayscale:02x}"
                self.motor_representation[motor_index][board_index]["bg"] = "#" + hex_value * 3

    def update(self):
        self.communication.send(self.wing_control.locations)
        self.recolor()

    def open_motor_speed_window(self, board_index, motor_index):
        window = Toplevel(self.window)
        window.title(f"Board {board_index + 1}, Motor {motor_index + 1}")
        window.resizable(False, False)

        current = self.motor_speeds[board_index][motor_index]

        up_var = IntVar(value=current["up"])
        down_var = IntVar(value=current["down"])

        Label(window, text=f"Board {board_index + 1}  Motor {motor_index + 1}").pack(padx=10, pady=5)

        Label(window, text="Up speed").pack()
        Scale(
            window,
            from_=0,
            to=255,
            resolution=5,
            orient="horizontal",
            variable=up_var,
            length=250
        ).pack(padx=10)

        Label(window, text="Down speed").pack()
        Scale(
            window,
            from_=0,
            to=255,
            resolution=5,
            orient="horizontal",
            variable=down_var,
            length=250
        ).pack(padx=10)

        def save_and_close():
            old_up = self.motor_speeds[board_index][motor_index]["up"]
            old_down = self.motor_speeds[board_index][motor_index]["down"]

            new_up = max(0, min(255, 5 * round(up_var.get() / 5)))
            new_down = max(0, min(255, 5 * round(down_var.get() / 5)))

            self.motor_speeds[board_index][motor_index]["up"] = new_up
            self.motor_speeds[board_index][motor_index]["down"] = new_down

            if new_up != old_up:
                self.communication.send_motor_speed_packet(board_index + 1, self.motor_speeds, motor_index, is_up=True)

            if new_down != old_down:
                self.communication.send_motor_speed_packet(board_index + 1, self.motor_speeds, motor_index, is_up=False)

            window.destroy()

        Button(window, text="Save", command=save_and_close).pack(pady=10)

    def runStatic(self):
        func = self.functionParser()

        try:
            x_inc = eval(
                self.window.children.get("control_panel")
                .children.get("advanced_options")
                .children.get("motor_increment_options")
                .children.get("x_motor_increment").get()
            )
        except Exception as exception:
            messagebox.showwarning(
                "x Motor Increment Error",
                "An error has occurred while trying to calculate the x motor increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            x_inc = pi / 12

        try:
            y_inc = eval(
                self.window.children.get("control_panel")
                .children.get("advanced_options")
                .children.get("motor_increment_options")
                .children.get("y_motor_increment").get()
            )
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
            x_motor_inc = eval(
                self.window.children.get("control_panel")
                .children.get("advanced_options")
                .children.get("motor_increment_options")
                .children.get("x_motor_increment").get()
            )
        except Exception as exception:
            messagebox.showwarning(
                "x Motor Increment Error",
                "An error has occurred while trying to calculate the x motor increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            x_motor_inc = pi / 12

        try:
            y_motor_inc = eval(
                self.window.children.get("control_panel")
                .children.get("advanced_options")
                .children.get("motor_increment_options")
                .children.get("y_motor_increment").get()
            )
        except Exception as exception:
            messagebox.showwarning(
                "y Motor Increment Error",
                "An error has occurred while trying to calculate the y motor increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            y_motor_inc = pi / 12

        try:
            x_time_inc = eval(
                self.window.children.get("control_panel")
                .children.get("advanced_options")
                .children.get("time_increment_options")
                .children.get("x_time_increment").get()
            )
        except Exception as exception:
            messagebox.showwarning(
                "x Time Increment Error",
                "An error has occurred while trying to calculate the x time increment.\n"
                "ERROR TYPE: {0}\n"
                "ERROR: {1}".format(type(exception), exception)
            )
            x_time_inc = pi / 12

        try:
            y_time_inc = eval(
                self.window.children.get("control_panel")
                .children.get("advanced_options")
                .children.get("time_increment_options")
                .children.get("y_time_increment").get()
            )
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
        self.channels = self.find_channels()

        self.setting_popup = Tk()
        self.setting_popup.title("GUI setup")
        self.setting_popup.geometry("500x70")
        self.setting_popup.resizable(False, False)

        self.com_choice = StringVar(value=self.channels[0])
        self.width_choice = IntVar(value=14)
        self.length_choice = IntVar(value=30)
        self.start = False



        self.widgets()
        self.setting_popup.mainloop()

    def find_channels(self):
        channels = ["DEMO-MODE"]
        try:
            for name in os.listdir("/sys/class/net"):
                if name.startswith(("can", "vcan", "slcan")):
                    channels.append(name)
        except OSError:
            pass
        return channels

    def widgets(self):

        Label(self.setting_popup, text="CAN channel:").pack(side=LEFT)
        OptionMenu(self.setting_popup, self.com_choice, *self.channels).pack(side=LEFT)

        Label(self.setting_popup, text="Width:").pack(side=LEFT)
        Spinbox(self.setting_popup, from_=1, to=50, textvariable=self.width_choice, width=3).pack(side=LEFT)

        Label(self.setting_popup, text="Length:").pack(side=LEFT)
        Spinbox(self.setting_popup, from_=1, to=82, textvariable=self.length_choice, width=3).pack(side=LEFT)

        Button(self.setting_popup, text="Start", command=self.on_start).pack(side=LEFT)


    def on_start(self):
        self.start = True
        self.setting_popup.destroy()

    def get(self):
        return self.com_choice.get(), self.width_choice.get(), self.length_choice.get()


if __name__ == "__main__":
    setup = SetupGUI()

    if setup.start:
        chan, width, length = setup.get()

        # range_of_motion kept as example value.
        # we will need to change it to real hardware range if needed.
        app = ControlGUI(
            chan=chan,
            range_of_motion=255,
            width=int(width),   # should be 14 for the experiment
            length=int(length)  # should be 30 for the experiment?
        )
        app.start()
