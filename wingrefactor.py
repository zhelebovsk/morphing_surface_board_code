import can
import os
import queue
import threading
import time
from tkinter import (
    Tk, Toplevel, Frame, Canvas, Button, LEFT, RIGHT, BOTTOM, X, LabelFrame,
    DoubleVar, BooleanVar, StringVar, IntVar, Label,
    Spinbox, OptionMenu, Scale, Checkbutton
)
from math import sin, cos, tan, pi, exp, sqrt, ceil

SCALING_FACTOR = 2.5

MOTOR_SPACING_MM = 10.0   # mm per motor index (Y axis)
BOARD_SPACING_MM = 10.0   # mm per board index (X axis)

def motor_function(x_mm, y_mm, t):
    return sin(t*2*pi + x_mm/100) * cos(t*2*pi + y_mm/100)

FUNCTION_DESCRIPTION = "u(x, y, t)"


def clamp8(x):
    return max(0, min(255, int(x)))


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
        self.locations = new_locations  # single atomic assignment


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
        try:
            self.bus.send(msg, timeout=0.1)
        except can.CanError as e:
            print(f"CAN send failed: {e}")

    def send_positions(self, locations):
        board_count = len(locations)
        motors_per_board = len(locations[0])

        for board_index in range(board_count):
            board_id = board_index + 1

            data_low = bytes(
                [1] +
                [clamp8(locations[board_index][m]) for m in range(7)]
            )
            data_high = bytes(
                [2] +
                [clamp8(locations[board_index][m]) for m in range(7, 14)]
            )

            self.send_frame(data_high, board_id)
            self.send_frame(data_low, board_id)

    def send_board_config(self, board_id, kp, ki, kd, alpha, limit_signal, deadband):
        data = bytes([
            3,
            clamp8(kp),
            clamp8(ki),
            clamp8(kd),
            clamp8(alpha),
            clamp8(limit_signal),
            clamp8(deadband),
            0
        ])
        self.send_frame(data, board_id)


class ControlGUI:
    UPDATE_HZ = 100.0
    UPDATE_DT = 1.0 / UPDATE_HZ

    def __init__(self, channel, range_of_motion, width=14, length=30, offset=0):

        self.board_count = length
        self.motors_per_board = width

        self.wing_control = WingControl(range_of_motion, length, width, offset)
        self.communication = MotorCommunication(channel)

        self.window = Tk()
        self.window.tk.call('tk', 'scaling', SCALING_FACTOR)
        self.window.title("Motor Control")
        self.window.geometry("1650x900")
        self.window.resizable(True, True)

        self.main_area = Frame(self.window)
        self.main_area.pack(side="top", fill="both", expand=True)

        self.bottom_area = Frame(self.window)
        self.bottom_area.pack(side=BOTTOM, fill=X)

        self.running = False
        self.step_index = 0
        self._hovered = None
        self._frame_queue = queue.Queue()

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
        self.recolor()

        self.window.update_idletasks()
        self.window.minsize(self.window.winfo_reqwidth(), self.window.winfo_reqheight())

    def build_left_panel(self):
        panel = Frame(self.main_area)
        panel.pack(side=LEFT, anchor="n", padx=10, pady=10)

        info_box = LabelFrame(panel, text="Active function")
        info_box.pack(fill="x", pady=8)

        Label(
            info_box,
            text=FUNCTION_DESCRIPTION,
            justify="left",
            wraplength=260,
            font=("Courier", 10)
        ).pack(anchor="w", padx=6, pady=6)

        Label(
            info_box,
            text="Edit motor_function() in the source\nto change the behaviour.",
            justify="left",
            wraplength=260,
            fg="gray"
        ).pack(anchor="w", padx=6, pady=(0, 6))

        timing_box = LabelFrame(panel, text="Timing")
        timing_box.pack(fill="x", pady=8)

        Label(
            timing_box,
            text=f"Update rate: {self.UPDATE_HZ} Hz",
            justify="left"
        ).pack(anchor="w", padx=6, pady=6)

        run_box = LabelFrame(panel, text="Run")
        run_box.pack(fill="x", pady=8)

        t_row = Frame(run_box)
        t_row.pack(fill="x", padx=4, pady=2)
        Label(t_row, text="t =").pack(side=LEFT)
        self.static_t = DoubleVar(value=0.0)
        Spinbox(t_row, from_=-1e9, to=1e9, increment=0.1, textvariable=self.static_t,
                width=8, format="%.2f").pack(side=LEFT, padx=4)

        Button(run_box, text="Run statically", command=self.run_static).pack(fill="x", padx=4, pady=2)
        Button(run_box, text="Start dynamic", command=self.start_dynamic).pack(fill="x", padx=4, pady=2)
        Button(run_box, text="Stop dynamic", command=self.stop_dynamic).pack(fill="x", padx=4, pady=2)

    def build_board_view(self):
        board_frame = Frame(self.main_area)
        board_frame.pack(side=RIGHT, padx=10, pady=10, expand=True)

        canvas_size = max(16, ceil(min(620 / self.motors_per_board, 1200 / self.board_count)))

        Label(board_frame, text="", width=4).grid(row=0, column=0, padx=1, pady=1)

        for board in range(self.board_count):
            padx = (10, 1) if board == 15 else 1
            Label(board_frame, text=str(board + 1), width=4).grid(
                row=0, column=board + 1, padx=padx, pady=1
            )

        hover_frame = Frame(board_frame)
        hover_frame.grid(
            row=self.motors_per_board + 3, column=0,
            columnspan=self.board_count + 1, pady=(8, 0)
        )

        headers = ["board", "motor", "x", "y", "z"]
        self._hover_vars = {h: StringVar(value="--") for h in headers}
        units = {"x": " mm", "y": " mm"}

        for col, h in enumerate(headers):
            Label(hover_frame, text=h, font=("Courier", 10, "bold"),
                  width=12, relief="groove", anchor="center").grid(row=0, column=col, padx=1)
            Label(hover_frame, textvariable=self._hover_vars[h],
                  font=("Courier", 10), width=12, relief="sunken", anchor="center").grid(row=1, column=col, padx=1)

        for motor in range(self.motors_per_board):
            pady = (10, 1) if motor == 7 else 1
            Label(board_frame, text=str(motor + 1), width=4).grid(
                row=motor + 1, column=0, padx=1, pady=pady
            )

            for board in range(self.board_count):
                padx = (10, 0) if board == 15 else 0
                pady = (10, 0) if motor == 7 else 0
                c = Canvas(
                    board_frame,
                    width=canvas_size,
                    height=canvas_size,
                    bg="green",
                    highlightthickness=1,
                    highlightbackground="black"
                )
                c.grid(row=motor + 1, column=board + 1, padx=padx, pady=pady)
                self.motor_canvases.append(c)

                x_mm = (board - self.wing_control.x_center) * BOARD_SPACING_MM
                y_mm = (self.wing_control.y_center - motor) * MOTOR_SPACING_MM

                def on_enter(e, b=board, m=motor, x=x_mm, y=y_mm):
                    self._hovered = (b, m, x, y)
                    self._refresh_hover_label()

                c.bind("<Enter>", on_enter)
                c.bind("<Leave>", lambda e: self._clear_hover_label())

        x_min = int(-self.wing_control.x_center * BOARD_SPACING_MM)
        x_max = int( self.wing_control.x_center * BOARD_SPACING_MM)
        y_min = int(-self.wing_control.y_center * MOTOR_SPACING_MM)
        y_max = int( self.wing_control.y_center * MOTOR_SPACING_MM)

        # bottom ruler
        Frame(board_frame, bg="black", height=2).grid(
            row=self.motors_per_board + 1, column=1,
            columnspan=self.board_count, sticky="ew", pady=(6, 0)
        )
        Label(board_frame, text=f"x:  {x_min} … {x_max} mm").grid(
            row=self.motors_per_board + 2, column=1,
            columnspan=self.board_count
        )

        # right ruler
        Frame(board_frame, bg="black", width=2).grid(
            row=1, column=self.board_count + 1,
            rowspan=self.motors_per_board, sticky="ns", padx=(6, 0)
        )
        Label(board_frame, text=f"y: +{y_max}\n…\n{y_min} mm", justify="center").grid(
            row=1, column=self.board_count + 2,
            rowspan=self.motors_per_board
        )

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

    def recolor(self):
        counter = 0
        for motor in range(self.wing_control.motors_per_board):
            for board in range(self.wing_control.board_count):
                # normalise to -1 … +1
                t = (
                    (self.wing_control.locations[board][motor] - self.wing_control.offset)
                    / self.wing_control.zero
                ) - 1.0
                t = max(-1.0, min(1.0, t))
                if t >= 0:                      # 0 … +1  →  white … red
                    r, g, b = 255, round(255 * (1 - t)), round(255 * (1 - t))
                else:                           # -1 … 0  →  blue … white
                    r, g, b = round(255 * (1 + t)), round(255 * (1 + t)), 255
                self.motor_canvases[counter]["bg"] = f"#{r:02x}{g:02x}{b:02x}"
                counter += 1
        self._refresh_hover_label()

    def _refresh_hover_label(self):
        if self._hovered is None:
            return
        b, m, x, y = self._hovered
        wc = self.wing_control
        z = (wc.locations[b][m] - wc.offset) / wc.zero - 1.0
        self._hover_vars["board"].set(str(b + 1))
        self._hover_vars["motor"].set(str(m + 1))
        self._hover_vars["x"].set(f"{x:+.1f} mm")
        self._hover_vars["y"].set(f"{y:+.1f} mm")
        self._hover_vars["z"].set(f"{z:+.3f}")

    def _clear_hover_label(self):
        self._hovered = None
        for v in self._hover_vars.values():
            v.set("--")

    def run_static(self):
        self.wing_control.fill_from_function(motor_function, t=self.static_t.get())
        self.communication.send_positions(self.wing_control.locations)
        self.recolor()

    def start_dynamic(self):
        if self.running:
            return
        self.running = True
        self.step_index = 0
        self._frame_queue = queue.Queue()
        threading.Thread(target=self._send_loop, daemon=True).start()
        self._schedule_recolor()

    def _send_loop(self):
        next_time = time.perf_counter()
        while self.running:
            t = self.step_index * self.UPDATE_DT
            self.wing_control.fill_from_function(motor_function, t)
            locations = self.wing_control.locations
            self.communication.send_positions(locations)
            self._frame_queue.put([row[:] for row in locations])
            self.step_index += 1

            next_time = max(next_time + self.UPDATE_DT, time.perf_counter())
            sleep_for = next_time - time.perf_counter()
            if sleep_for > 0:
                time.sleep(sleep_for)

    def _schedule_recolor(self):
        if not self.running:
            return
        locations = None
        try:
            while True:
                locations = self._frame_queue.get_nowait()
        except queue.Empty:
            pass
        if locations is not None:
            self.wing_control.locations = locations
            self.recolor()
        self.window.after(20, self._schedule_recolor)

    def stop_dynamic(self):
        self.running = False

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
        self.window.tk.call('tk', 'scaling', SCALING_FACTOR)
        self.window.title("GUI setup")
        self.window.geometry("960x120")
        self.window.resizable(False, False)

        self.channel_choice = StringVar(value=channels[0])
        self.started = False

        Label(self.window, text="CAN channel:").pack(side=LEFT, padx=4, pady=8)
        OptionMenu(self.window, self.channel_choice, *channels).pack(side=LEFT, padx=4, pady=8)

        Button(self.window, text="Start", command=self.on_start).pack(side=LEFT, padx=8, pady=8)
        self.window.mainloop()

    def on_start(self):
        self.started = True
        self.window.destroy()

    def get(self):
        return self.channel_choice.get()


if __name__ == "__main__":
    setup = SetupGUI()

    if setup.started:
        channel = setup.get()

        app = ControlGUI(channel=channel, range_of_motion=255)
        app.start()