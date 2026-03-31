from math import ceil
from tkinter import (
    Tk, Toplevel, Frame, Canvas, Button, LEFT, RIGHT, BOTTOM, X, LabelFrame,
    DoubleVar, BooleanVar, StringVar, IntVar, Label,
    Spinbox, Scale, Checkbutton,
)

from config import SCALING_FACTOR, BOARD_SPACING_MM, MOTOR_SPACING_MM
from function import FUNCTION_DESCRIPTION


class MainWindow:
    def __init__(self, engine):
        self.engine = engine
        self.board_count = engine.board_count
        self.motors_per_board = engine.motors_per_board

        self.window = Tk()
        self.window.tk.call('tk', 'scaling', SCALING_FACTOR)
        self.window.title("Motor Control")
        self.window.geometry("1650x900")
        self.window.resizable(True, True)

        self.main_area = Frame(self.window)
        self.main_area.pack(side="top", fill="both", expand=True)

        self.bottom_area = Frame(self.window)
        self.bottom_area.pack(side=BOTTOM, fill=X)

        self._hovered = None

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
            text=f"Update rate: {self.engine.UPDATE_HZ} Hz",
            justify="left"
        ).pack(anchor="w", padx=6, pady=6)

        run_box = LabelFrame(panel, text="Run")
        run_box.pack(fill="x", pady=8)

        t_row = Frame(run_box)
        t_row.pack(fill="x", padx=4, pady=2)
        Label(t_row, text="t =").pack(side=LEFT)
        self.static_t = DoubleVar(value=0.0)
        Spinbox(
            t_row,
            from_=-1e9,
            to=1e9,
            increment=0.1,
            textvariable=self.static_t,
            width=8,
            format="%.2f"
        ).pack(side=LEFT, padx=4)

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

        for col, h in enumerate(headers):
            Label(
                hover_frame,
                text=h,
                font=("Courier", 10, "bold"),
                width=12,
                relief="groove",
                anchor="center"
            ).grid(row=0, column=col, padx=1)
            Label(
                hover_frame,
                textvariable=self._hover_vars[h],
                font=("Courier", 10),
                width=12,
                relief="sunken",
                anchor="center"
            ).grid(row=1, column=col, padx=1)

        wc = self.engine.wing_control
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

                x_mm = (board - wc.x_center) * BOARD_SPACING_MM
                y_mm = (wc.y_center - motor) * MOTOR_SPACING_MM

                def on_enter(e, b=board, m=motor, x=x_mm, y=y_mm):
                    self._hovered = (b, m, x, y)
                    self._refresh_hover_label()

                c.bind("<Enter>", on_enter)
                c.bind("<Leave>", lambda e: self._clear_hover_label())

        x_min = int(-wc.x_center * BOARD_SPACING_MM)
        x_max = int(wc.x_center * BOARD_SPACING_MM)
        y_min = int(-wc.y_center * MOTOR_SPACING_MM)
        y_max = int(wc.y_center * MOTOR_SPACING_MM)

        Frame(board_frame, bg="black", height=2).grid(
            row=self.motors_per_board + 1, column=1,
            columnspan=self.board_count, sticky="ew", pady=(6, 0)
        )
        Label(board_frame, text=f"x:  {x_min} … {x_max} mm").grid(
            row=self.motors_per_board + 2, column=1,
            columnspan=self.board_count
        )

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
        for motor in range(self.motors_per_board):
            for board in range(self.board_count):
                shown_value = self.engine.displayed_value(board, motor)
                t = max(-1.0, min(1.0, (shown_value / 255.0) * 2.0 - 1.0))
                if t >= 0:
                    r, g, b = 255, round(255 * (1 - t)), round(255 * (1 - t))
                else:
                    r, g, b = round(255 * (1 + t)), round(255 * (1 + t)), 255
                self.motor_canvases[counter]["bg"] = f"#{r:02x}{g:02x}{b:02x}"
                counter += 1
        self._refresh_hover_label()

    def _refresh_hover_label(self):
        if self._hovered is None:
            return
        b, m, x, y = self._hovered
        shown_value = self.engine.displayed_value(b, m)
        z = (shown_value / 255.0) * 2.0 - 1.0
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
        self.engine.run_static(self.static_t.get())
        self.recolor()

    def start_dynamic(self):
        self.engine.start_dynamic()
        self._schedule_recolor()

    def _schedule_recolor(self):
        if not self.engine.running:
            return
        locations = self.engine.drain_frame_queue()
        if locations is not None:
            self.engine.wing_control.locations = locations
            self.recolor()
        self.window.after(20, self._schedule_recolor)

    def stop_dynamic(self):
        self.engine.stop_dynamic()

    def _build_config_values(self):
        return (
            self.kp_value.get(),
            self.ki_value.get(),
            self.kd_value.get(),
            self.alpha_value.get(),
            self.limit_signal_value.get(),
            self.deadband_value.get(),
        )

    def send_config_to_all_boards(self):
        kp, ki, kd, alpha, limit_signal, deadband = self._build_config_values()
        self.engine.send_config(range(1, self.board_count + 1), kp, ki, kd, alpha, limit_signal, deadband)

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
            kp, ki, kd, alpha, limit_signal, deadband = self._build_config_values()
            board_ids = [i + 1 for i, var in enumerate(board_vars) if var.get()]
            self.engine.send_config(board_ids, kp, ki, kd, alpha, limit_signal, deadband)
            pick_window.destroy()

        buttons = Frame(pick_window)
        buttons.pack(pady=(0, 10))
        Button(buttons, text="Send", command=send_selected).pack(side=LEFT, padx=5)
        Button(buttons, text="Cancel", command=pick_window.destroy).pack(side=LEFT, padx=5)

    def start(self):
        self.window.mainloop()
