import sys
from math import ceil

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QGroupBox, QLabel, QPushButton, QDoubleSpinBox,
    QSlider, QSpinBox, QFrame, QDialog, QCheckBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPalette

from config import BOARD_SPACING_MM, MOTOR_SPACING_MM
from config import FUNCTION_DESCRIPTION, UPDATE_HZ


class _MotorCell(QFrame):
    def __init__(self, on_enter, on_leave, parent=None):
        super().__init__(parent)
        self._on_enter = on_enter
        self._on_leave = on_leave
        self.setFrameShape(QFrame.Box)
        self.setLineWidth(1)
        self.setAutoFillBackground(True)
        self.set_color(0, 200, 0)

    def enterEvent(self, event):
        self._on_enter()

    def leaveEvent(self, event):
        self._on_leave()

    def set_color(self, r, g, b):
        palette = self.palette()
        palette.setColor(QPalette.Window, QColor(r, g, b))
        self.setPalette(palette)


class MainWindow:
    def __init__(self, engine):
        self.engine = engine
        self.board_count = engine.board_count
        self.motors_per_board = engine.motors_per_board

        self._app = QApplication.instance() or QApplication(sys.argv)

        self._window = QMainWindow()
        self._window.setWindowTitle("Motor Control")
        self._window.resize(1650, 900)

        central = QWidget()
        self._window.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QWidget()
        top_layout = QHBoxLayout(top)
        root.addWidget(top, stretch=1)

        top_layout.addWidget(self._build_left_panel(), alignment=Qt.AlignTop)
        top_layout.addWidget(self._build_board_view(), stretch=1)

        root.addWidget(self._build_bottom_bar())

        self._hovered = None
        self._blink_state = False

        self._recolor()
        self._refresh_dynamic_info()

        self._timer = QTimer()
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._poll_everything)

    # ── left panel ────────────────────────────────────────────────────────────

    def _build_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setAlignment(Qt.AlignTop)

        info = QGroupBox("Active function")
        info_l = QVBoxLayout(info)

        func_lbl = QLabel(FUNCTION_DESCRIPTION)
        func_lbl.setWordWrap(True)
        func_lbl.setFont(self._app.font())
        info_l.addWidget(func_lbl)

        hint = QLabel("Edit motor_function() in the source\nto change the behaviour.")
        hint.setStyleSheet("color: gray;")
        hint.setWordWrap(True)
        info_l.addWidget(hint)

        layout.addWidget(info)

        timing = QGroupBox("Timing")
        timing_l = QVBoxLayout(timing)
        timing_l.addWidget(QLabel(f"Update rate: {UPDATE_HZ} Hz"))
        layout.addWidget(timing)

        run = QGroupBox("Run")
        run_l = QVBoxLayout(run)

        # static t
        t_row = QWidget()
        t_layout = QHBoxLayout(t_row)
        t_layout.setContentsMargins(0, 0, 0, 0)

        t_layout.addWidget(QLabel("static t ="))
        self._static_t = QDoubleSpinBox()
        self._static_t.setRange(-1e9, 1e9)
        self._static_t.setSingleStep(0.1)
        self._static_t.setDecimals(2)
        t_layout.addWidget(self._static_t)
        t_layout.addStretch(1)

        run_l.addWidget(t_row)

        run_static_btn = QPushButton("Run statically")
        run_static_btn.clicked.connect(self._run_static)
        run_l.addWidget(run_static_btn)

        # editable dynamic frequency
        mu_row = QWidget()
        mu_layout = QHBoxLayout(mu_row)
        mu_layout.setContentsMargins(0, 0, 0, 0)

        mu_layout.addWidget(QLabel("μ ="))
        self._mu_input = QDoubleSpinBox()
        self._mu_input.setRange(0.001, 1000.0)
        self._mu_input.setSingleStep(0.1)
        self._mu_input.setDecimals(3)
        self._mu_input.setValue(1.0)
        self._mu_input.valueChanged.connect(self._mu_changed)
        mu_layout.addWidget(self._mu_input)
        mu_layout.addStretch(1)

        run_l.addWidget(mu_row)

        for label, slot in [
            ("Start dynamic", self._start_dynamic),
            ("Stop dynamic", self._stop_dynamic),
            ("Reset dynamic", self._reset_dynamic),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            run_l.addWidget(btn)

        layout.addWidget(run)

        calib = QGroupBox("Calibration")
        calib_l = QVBoxLayout(calib)
        reload_btn = QPushButton("Reload limits")
        reload_btn.clicked.connect(self._reload_limits)
        calib_l.addWidget(reload_btn)
        layout.addWidget(calib)

        return panel

    # ── board grid ────────────────────────────────────────────────────────────

    def _build_board_view(self):
        container = QWidget()
        layout = QVBoxLayout(container)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setSpacing(1)

        cell_size = max(16, ceil(min(620 / self.motors_per_board, 1200 / self.board_count)))

        for board in range(self.board_count):
            lbl = QLabel(str(board + 1))
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setFixedWidth(cell_size)
            grid.addWidget(lbl, 0, board + 1)

        wc = self.engine.wing_control
        self._motor_cells = []

        for motor in range(self.motors_per_board):
            row_lbl = QLabel(str(motor + 1))
            row_lbl.setAlignment(Qt.AlignCenter)
            grid.addWidget(row_lbl, motor + 1, 0)

            for board in range(self.board_count):
                x_mm = (board - wc.x_center) * BOARD_SPACING_MM
                y_mm = (wc.y_center - motor) * MOTOR_SPACING_MM

                cell = _MotorCell(
                    on_enter=lambda b=board, m=motor, x=x_mm, y=y_mm: self._on_hover(b, m, x, y),
                    on_leave=self._on_hover_clear,
                )
                cell.setFixedSize(cell_size, cell_size)
                grid.addWidget(cell, motor + 1, board + 1)
                self._motor_cells.append(cell)

        x_min = int(-wc.x_center * BOARD_SPACING_MM)
        x_max = int(wc.x_center * BOARD_SPACING_MM)
        y_min = int(-wc.y_center * MOTOR_SPACING_MM)
        y_max = int(wc.y_center * MOTOR_SPACING_MM)

        # bottom x ruler
        x_range = QLabel(f"x : {x_min:>4} ---- 0 ---- {x_max:<4} [mm]")
        x_range.setAlignment(Qt.AlignHCenter)
        x_range.setStyleSheet("padding-top: 6px; padding-bottom: 2px;")

        # build main board + right y ruler side by side
        board_and_y = QWidget()
        board_and_y_layout = QHBoxLayout(board_and_y)
        board_and_y_layout.setContentsMargins(0, 0, 0, 0)
        board_and_y_layout.setSpacing(10)

        board_column = QWidget()
        board_column_layout = QVBoxLayout(board_column)
        board_column_layout.setContentsMargins(0, 0, 0, 0)
        board_column_layout.setSpacing(4)
        board_column_layout.addWidget(grid_widget)
        board_column_layout.addWidget(x_range)

        y_range = QLabel(f"y : {y_max:>4}\n|\n0\n|\n{y_min:<4}\n[mm]")
        y_range.setAlignment(Qt.AlignVCenter | Qt.AlignHCenter)
        y_range.setStyleSheet("padding-left: 6px; padding-right: 6px;")

        board_and_y_layout.addWidget(board_column, stretch=1)
        board_and_y_layout.addWidget(y_range, alignment=Qt.AlignVCenter)

        layout.addWidget(board_and_y)

        info_strip = QWidget()
        info_strip_layout = QHBoxLayout(info_strip)
        info_strip_layout.setContentsMargins(0, 8, 0, 0)

        # hover chunk
        hover_widget = QWidget()
        hover_layout = QHBoxLayout(hover_widget)
        hover_layout.setContentsMargins(0, 0, 0, 0)
        self._hover_labels = {}

        for h in ["board", "motor", "x", "y", "z"]:
            col = QWidget()
            col_l = QVBoxLayout(col)
            col_l.setSpacing(2)

            header = QLabel(h)
            header.setAlignment(Qt.AlignCenter)
            header.setFixedWidth(110)
            header.setStyleSheet("border: 1px solid gray; padding: 2px;")

            val = QLabel("--")
            val.setAlignment(Qt.AlignCenter)
            val.setFixedWidth(110)
            val.setStyleSheet("border: 1px solid gray; padding: 2px;")

            col_l.addWidget(header)
            col_l.addWidget(val)
            self._hover_labels[h] = val
            hover_layout.addWidget(col)

        info_strip_layout.addWidget(hover_widget)

        # dynamic chunk
        dynamic_widget = QWidget()
        dynamic_layout = QHBoxLayout(dynamic_widget)
        dynamic_layout.setContentsMargins(24, 0, 0, 0)

        self._dynamic_labels = {}
        for h in ["t", "μ", "φ", "N"]:
            col = QWidget()
            col_l = QVBoxLayout(col)
            col_l.setSpacing(2)

            header = QLabel(h)
            header.setAlignment(Qt.AlignCenter)
            header.setFixedWidth(110)
            header.setStyleSheet("border: 1px solid gray; padding: 2px;")

            val = QLabel("--")
            val.setAlignment(Qt.AlignCenter)
            val.setFixedWidth(110)
            val.setStyleSheet("border: 1px solid gray; padding: 2px;")

            col_l.addWidget(header)
            col_l.addWidget(val)
            self._dynamic_labels[h] = val
            dynamic_layout.addWidget(col)

        blink_col = QWidget()
        blink_col_l = QVBoxLayout(blink_col)
        blink_col_l.setSpacing(2)

        blink_header = QLabel("blink")
        blink_header.setAlignment(Qt.AlignCenter)
        blink_header.setFixedWidth(70)
        blink_header.setStyleSheet("border: 1px solid gray; padding: 2px;")

        self._blink_label = QLabel("")
        self._blink_label.setFixedSize(70, 28)
        self._blink_label.setStyleSheet("border: 1px solid gray; background: rgb(50,50,50);")

        blink_col_l.addWidget(blink_header)
        blink_col_l.addWidget(self._blink_label, alignment=Qt.AlignCenter)
        self._dynamic_labels["blink"] = self._blink_label
        dynamic_layout.addWidget(blink_col)

        info_strip_layout.addWidget(dynamic_widget)
        info_strip_layout.addStretch(1)

        layout.addWidget(info_strip)

        return container

    # ── bottom config bar ─────────────────────────────────────────────────────

    def _build_bottom_bar(self):
        bar = QGroupBox("Board config packet")
        bar_layout = QHBoxLayout(bar)

        sliders_widget = QWidget()
        sliders_layout = QHBoxLayout(sliders_widget)
        self._kp = self._add_slider(sliders_layout, "Kp", default=51)
        self._ki = self._add_slider(sliders_layout, "Ki", default=26)
        self._kd = self._add_slider(sliders_layout, "Kd", default=0)
        self._alpha = self._add_slider(sliders_layout, "Alpha", default=51)
        self._limit_signal = self._add_slider(sliders_layout, "Limit signal", default=100)
        self._deadband = self._add_slider(sliders_layout, "Deadband", default=10)
        bar_layout.addWidget(sliders_widget)

        btn_widget = QWidget()
        btn_layout = QVBoxLayout(btn_widget)

        send_all = QPushButton("Send to all boards")
        send_all.clicked.connect(self._send_config_to_all_boards)

        pick = QPushButton("Pick boards")
        pick.clicked.connect(self._open_pick_boards_window)

        btn_layout.addWidget(send_all)
        btn_layout.addWidget(pick)
        bar_layout.addWidget(btn_widget)

        return bar

    def _add_slider(self, layout, title, default=0):
        col = QWidget()
        col_l = QVBoxLayout(col)
        col_l.addWidget(QLabel(title))

        row = QWidget()
        row_l = QHBoxLayout(row)
        row_l.setContentsMargins(0, 0, 0, 0)
        row_l.setSpacing(4)

        slider = QSlider(Qt.Horizontal)
        slider.setRange(0, 255)
        slider.setFixedWidth(130)

        spinbox = QSpinBox()
        spinbox.setRange(0, 255)
        spinbox.setFixedWidth(55)

        slider.valueChanged.connect(spinbox.setValue)
        spinbox.valueChanged.connect(slider.setValue)

        spinbox.setValue(default)

        row_l.addWidget(slider)
        row_l.addWidget(spinbox)
        col_l.addWidget(row)
        layout.addWidget(col)
        return spinbox

    # ── recolor ───────────────────────────────────────────────────────────────

    def _recolor(self):
        counter = 0
        for motor in range(self.motors_per_board):
            for board in range(self.board_count):
                shown = self.engine.displayed_value(board, motor)
                t = max(-1.0, min(1.0, (shown / 255.0) * 2.0 - 1.0))
                if t >= 0:
                    r, g, b = 255, round(255 * (1 - t)), round(255 * (1 - t))
                else:
                    r, g, b = round(255 * (1 + t)), round(255 * (1 + t)), 255
                self._motor_cells[counter].set_color(r, g, b)
                counter += 1
        self._refresh_hover()

    # ── hover ─────────────────────────────────────────────────────────────────

    def _on_hover(self, board, motor, x_mm, y_mm):
        self._hovered = (board, motor, x_mm, y_mm)
        self._refresh_hover()

    def _on_hover_clear(self):
        self._hovered = None
        for v in self._hover_labels.values():
            v.setText("--")

    def _refresh_hover(self):
        if self._hovered is None:
            return

        b, m, x, y = self._hovered
        shown = self.engine.displayed_value(b, m)
        z = (shown / 255.0) * 2.0 - 1.0

        self._hover_labels["board"].setText(str(b + 1))
        self._hover_labels["motor"].setText(str(m + 1))
        self._hover_labels["x"].setText(f"{x:+.1f} mm")
        self._hover_labels["y"].setText(f"{y:+.1f} mm")
        self._hover_labels["z"].setText(f"{z:+.3f}")

    # ── dynamic info ──────────────────────────────────────────────────────────

    def _refresh_dynamic_info(self):
        info = self.engine.get_dynamic_info()

        self._dynamic_labels["t"].setText(f"{info['t']:.3f} [s]")
        self._dynamic_labels["μ"].setText(f"{info['mu']:.3f} [Hz]")
        self._dynamic_labels["φ"].setText(f"{info['phi']:.3f}")
        self._dynamic_labels["N"].setText(str(info["N"]))

        blink_now = bool(info["blink"])
        if blink_now != self._blink_state:
            self._blink_state = blink_now
            if blink_now:
                self._blink_label.setStyleSheet("border: 1px solid gray; background: rgb(0,255,0);")
            else:
                self._blink_label.setStyleSheet("border: 1px solid gray; background: rgb(50,50,50);")

    def _mu_changed(self, value):
        self.engine.set_dynamic_mu(value)
        self._refresh_dynamic_info()

    # ── run controls ──────────────────────────────────────────────────────────

    def _run_static(self):
        self.engine.run_static(self._static_t.value())
        self._recolor()
        self._refresh_dynamic_info()

    def _start_dynamic(self):
        self.engine.set_dynamic_mu(self._mu_input.value())
        self.engine.start_dynamic()
        self._refresh_dynamic_info()
        self._timer.start()

    def _poll_everything(self):
        locations = self.engine.drain_frame_queue()
        if locations is not None:
            self.engine.wing_control.locations = locations
            self._recolor()
        self._refresh_dynamic_info()

    def _stop_dynamic(self):
        self.engine.stop_dynamic()
        self._timer.stop()
        self._refresh_dynamic_info()

    def _reset_dynamic(self):
        self.engine.reset_dynamic()
        self._refresh_dynamic_info()
        self._recolor()

    def _reload_limits(self):
        self.engine.reload_limits()
        self._recolor()

    # ── config send ───────────────────────────────────────────────────────────

    def _config_values(self):
        return (
            self._kp.value(), self._ki.value(), self._kd.value(),
            self._alpha.value(), self._limit_signal.value(), self._deadband.value(),
        )

    def _send_config_to_all_boards(self):
        self.engine.send_config(range(1, self.board_count + 1), *self._config_values())

    def _open_pick_boards_window(self):
        dialog = QDialog(self._window)
        dialog.setWindowTitle("Pick boards")
        layout = QVBoxLayout(dialog)

        grid = QWidget()
        grid_l = QGridLayout(grid)
        checks = []
        for i in range(self.board_count):
            cb = QCheckBox(f"Board {i + 1}")
            checks.append(cb)
            grid_l.addWidget(cb, i // 4, i % 4)
        layout.addWidget(grid)

        buttons = QWidget()
        btn_l = QHBoxLayout(buttons)

        send_btn = QPushButton("Send")
        send_btn.clicked.connect(lambda: [
            self.engine.send_config(
                [i + 1 for i, cb in enumerate(checks) if cb.isChecked()],
                *self._config_values()
            ),
            dialog.accept(),
        ])

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)

        btn_l.addWidget(send_btn)
        btn_l.addWidget(cancel_btn)
        layout.addWidget(buttons)

        dialog.exec()

    # ── entry point ───────────────────────────────────────────────────────────

    def start(self):
        self._window.show()
        self._app.exec()