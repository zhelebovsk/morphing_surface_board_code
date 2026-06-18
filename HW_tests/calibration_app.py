"""
calibration_app.py — Standalone motor calibration UI.

Runs in parallel across selected boards simultaneously.
Results auto-save to calibrations/ and are sent to boards the moment
each board finishes — no button press required.

No OpenOCD / ST-LINK needed — initial positions read via CAN stream.

Usage:
    cd HW_tests
    python calibration_app.py
"""

import json
import math
import os
import sys
import time
from datetime import datetime

import can
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QDoubleSpinBox,
    QFormLayout, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton,
    QSpinBox, QSplitter, QTabWidget, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

# ── Hardware constants ────────────────────────────────────────────────────────

LOCATION_MUL  = 7
POT_ZERO      = 1048
ACTIVE_MOTORS = list(range(1, 15))   # motor_ids 1–14
LO_LIMIT      = 680
HI_LIMIT      = 3415
STREAM_MS     = 10                   # 100 Hz CAN streaming

CALIBRATION_DIR = os.path.join(os.path.dirname(__file__), "calibrations")

# Sent to each board after calibration to restore normal running config
_RUNNING_CONFIG = [51, 26, 0, 51, 100, 10]  # Kp Ki Kd alpha u_limit deadband

# Result sanity: if a motor moved this many times more than commanded,
# it is flagged as suspicious (likely not physically connected)
_SANE_MOVEMENT_FACTOR  = 3
_SANE_OVERSHOOT_FACTOR = 2

# ── Pure calibration helpers ──────────────────────────────────────────────────

def _pot_to_can(pot):
    return max(0, min(255, round((pot - POT_ZERO) / LOCATION_MUL)))


def _build_frames(park_vals, active_idx, target_can):
    vals = list(park_vals)
    vals[active_idx] = target_can
    return bytes([0x01] + vals[0:7]), bytes([0x02] + vals[7:14])


def _send_config(bus, can_id, kp, ki, kd, alpha, u_limit, deadband, min_pwm):
    bus.send(can.Message(
        arbitration_id=can_id,
        data=bytes([0x03, kp, ki, kd, alpha, u_limit, deadband, min_pwm]),
        is_extended_id=False,
    ))


def _parse_stream(msg, motor_id):
    if len(msg.data) < 8 or msg.data[0] != 0xA0 or msg.data[1] != motor_id:
        return None
    raw    = msg.data[2] | (msg.data[3] << 8)
    filt_u = msg.data[4] | (msg.data[5] << 8)
    filt   = filt_u if filt_u < 32768 else filt_u - 65536
    return raw, filt


def _record_step(bus, can_id, motor_id, duration_s):
    bus.set_filters([{"can_id": can_id, "can_mask": 0x7FF, "extended": False}])
    raws, times = [], []
    t0 = time.perf_counter()
    while time.perf_counter() - t0 < duration_s:
        msg = bus.recv(timeout=0.05)
        if msg is None:
            continue
        parsed = _parse_stream(msg, motor_id)
        if parsed:
            raws.append(parsed[0])
            times.append(round(time.perf_counter() - t0, 4))
    return raws, times


def _movement(raws, initial):
    if not raws:
        return 0
    tail = raws[int(len(raws) * 0.7):]
    return abs(sum(tail) / len(tail) - initial)


def _fit_tau(times, raws, initial, final):
    span = initial - final
    if abs(span) < 1:
        return None
    t0 = 0.0
    for t, v in zip(times, raws):
        if abs(v - initial) > 5:
            t0 = t
            break
    pts = [
        (t - t0, math.log((v - final) / span))
        for t, v in zip(times, raws)
        if t >= t0 and (v - final) / span > 0.01
    ]
    if len(pts) < 3:
        return None
    n   = len(pts)
    sx  = sum(p[0] for p in pts)
    sy  = sum(p[1] for p in pts)
    sxy = sum(p[0] * p[1] for p in pts)
    sxx = sum(p[0] ** 2 for p in pts)
    d   = n * sxx - sx * sx
    if abs(d) < 1e-12:
        return None
    slope = (n * sxy - sx * sy) / d
    if abs(slope) < 1e-12:
        return None
    tau = -1.0 / slope
    if tau <= 0 or tau > 30.0:   # negative or >30 s is physical nonsense for a DC motor
        return None
    return tau


def _read_motor_positions(bus, can_id):
    """Stream each motor briefly to read its current raw pot value."""
    # Filter to this board's CAN ID only — critical when boards run in parallel,
    # otherwise every socket drowns in frames from all other boards.
    bus.set_filters([{"can_id": can_id, "can_mask": 0x7FF, "extended": False}])
    pots = {}
    for motor_id in ACTIVE_MOTORS:
        bus.send(can.Message(
            arbitration_id=can_id,
            data=bytes([0x04, motor_id, STREAM_MS, 0, 0, 0, 0, 0]),
            is_extended_id=False,
        ))
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 0.3:
            msg = bus.recv(timeout=0.05)
            if msg is None or msg.arbitration_id != can_id:
                continue
            parsed = _parse_stream(msg, motor_id)
            if parsed:
                pots[motor_id] = parsed[0]
                break
        bus.send(can.Message(
            arbitration_id=can_id,
            data=bytes([0x05, 0, 0, 0, 0, 0, 0, 0]),
            is_extended_id=False,
        ))
        time.sleep(0.02)
    return pots


def _is_sane(result, step_size):
    actual   = result.get("actual_step", 0)
    expected = result.get("step_delta", step_size)
    # Moved in the wrong direction
    if expected != 0 and actual * expected < 0:
        return False
    # Moved less than 40% of the commanded step — motor not responding properly
    if abs(actual) < step_size * 0.4:
        return False
    # Moved way more than commanded
    if abs(actual) > step_size * _SANE_MOVEMENT_FACTOR:
        return False
    if abs(result.get("overshoot", 0)) > step_size * _SANE_OVERSHOOT_FACTOR:
        return False
    return True


# ── Background worker (one per board) ────────────────────────────────────────

class CalibrationWorker(QThread):
    log          = Signal(str)
    motor_status = Signal(int, str)
    motor_result = Signal(int, object)
    finished     = Signal(object)

    def __init__(self, params):
        super().__init__()
        self.params = params
        self._abort = False

    def abort(self):
        self._abort = True

    def run(self):
        p         = self.params
        board_id  = p["board_id"]
        can_id    = 0x100 + board_id
        step_size = p["step_size_adc"]
        kp        = p["calib_kp"]
        ki        = p["calib_ki"]
        kd        = p["calib_kd"]
        alpha     = p["calib_alpha"]
        u_limit   = p["calib_u_limit"]
        deadband  = p["calib_deadband"]

        try:
            bus = can.interface.Bus(channel=p["channel"], interface="socketcan")
        except OSError as e:
            self.log.emit(f"[Board {board_id}] ERROR opening CAN: {e}")
            self.finished.emit({})
            return

        pots = _read_motor_positions(bus, can_id)

        connected = []
        for active_idx, motor_id in enumerate(ACTIVE_MOTORS):
            pot = pots.get(motor_id)
            if pot is not None and LO_LIMIT <= pot <= HI_LIMIT:
                connected.append(active_idx)
                self.motor_status.emit(active_idx, f"connected  (pot={pot})")
            else:
                self.motor_status.emit(active_idx, "not connected")

        if not connected:
            bus.shutdown()
            self.finished.emit({})
            return

        self.log.emit(
            f"[Board {board_id}] {len(connected)} motors connected: "
            f"{[ACTIVE_MOTORS[i] + 1 for i in connected]}"
        )

        park_vals = [_pot_to_can(pots.get(mid, POT_ZERO)) for mid in ACTIVE_MOTORS]
        bus.send(can.Message(arbitration_id=can_id,
                             data=bytes([0x01] + park_vals[0:7]), is_extended_id=False))
        bus.send(can.Message(arbitration_id=can_id,
                             data=bytes([0x02] + park_vals[7:14]), is_extended_id=False))
        time.sleep(0.2)

        results   = {}
        direction = 1

        for active_idx in connected:
            if self._abort:
                self.log.emit(f"[Board {board_id}] Aborted.")
                break

            motor_id = ACTIVE_MOTORS[active_idx]
            pot      = pots[motor_id]
            self.motor_status.emit(active_idx, "testing…")
            self.log.emit(f"\n[Board {board_id}] ── Motor {motor_id + 1}  pot={pot} ──")

            step_delta = direction * step_size
            target_adc = pot + step_delta
            if not (LO_LIMIT <= target_adc <= HI_LIMIT):
                step_delta  = -step_delta
                target_adc  = pot + step_delta
            target_can = _pot_to_can(target_adc)

            bus.send(can.Message(
                arbitration_id=can_id,
                data=bytes([0x04, motor_id, STREAM_MS, 0, 0, 0, 0, 0]),
                is_extended_id=False,
            ))
            time.sleep(0.05)

            best = None
            for min_pwm in range(p["min_pwm_low"], p["min_pwm_high"] + 1, p["min_pwm_step"]):
                if self._abort:
                    break

                _send_config(bus, can_id, kp, ki, kd, alpha, u_limit, deadband, min_pwm)
                time.sleep(0.02)

                d1, d2 = _build_frames(park_vals, active_idx, target_can)
                bus.send(can.Message(arbitration_id=can_id, data=d1, is_extended_id=False))
                bus.send(can.Message(arbitration_id=can_id, data=d2, is_extended_id=False))

                raws, times = _record_step(bus, can_id, motor_id, p["step_timeout_s"])
                moved = _movement(raws, pot)
                self.log.emit(f"  min_pwm={min_pwm:3d}  moved={moved:.0f} ADC")

                if moved >= p["movement_thresh"]:
                    tail      = raws[int(len(raws) * 0.7):]
                    final     = sum(tail) / len(tail)
                    overshoot = final - (pot + step_delta)
                    tau       = _fit_tau(times, raws, pot, final)
                    tau_ms    = round(tau * 1000, 1) if tau else None
                    best = {
                        "min_pwm":     min_pwm,
                        "tau_ms":      tau_ms,
                        "step_delta":  step_delta,
                        "actual_step": round(final - pot, 1),
                        "overshoot":   round(overshoot, 1),
                    }
                    self.log.emit(
                        f"  → min_pwm={min_pwm}  τ={tau_ms} ms  overshoot={overshoot:+.0f}"
                    )
                    break

                rc = _pot_to_can(pot)
                r1, r2 = _build_frames(park_vals, active_idx, rc)
                bus.send(can.Message(arbitration_id=can_id, data=r1, is_extended_id=False))
                bus.send(can.Message(arbitration_id=can_id, data=r2, is_extended_id=False))
                time.sleep(0.2)  # motor didn't move; no need for full settle

            bus.send(can.Message(
                arbitration_id=can_id,
                data=bytes([0x05, 0, 0, 0, 0, 0, 0, 0]),
                is_extended_id=False,
            ))

            if best:
                _send_config(bus, can_id, kp, ki, kd, alpha, u_limit, deadband, best["min_pwm"])
                rc = _pot_to_can(pot)
                r1, r2 = _build_frames(park_vals, active_idx, rc)
                bus.send(can.Message(arbitration_id=can_id, data=r1, is_extended_id=False))
                bus.send(can.Message(arbitration_id=can_id, data=r2, is_extended_id=False))
                time.sleep(p["settle_s"])

                sane = _is_sane(best, step_size)
                if not sane:
                    best["suspicious"] = True
                    self.log.emit(
                        f"  !! Suspicious — moved {abs(best['actual_step']):.0f} ADC "
                        f"for a {step_size}-count step. Motor may not be connected."
                    )
                results[active_idx] = best
                self.motor_result.emit(active_idx, best)
                self.motor_status.emit(active_idx, "done" if sane else "suspicious")
            else:
                results[active_idx] = None
                self.motor_result.emit(active_idx, None)
                self.motor_status.emit(active_idx, "no response")

            direction *= -1

        bus.shutdown()
        self.finished.emit(results)


# ── Per-board results tab ─────────────────────────────────────────────────────

_NCOLS = 6
_COL_MOTOR, _COL_STATUS, _COL_MIN_PWM, _COL_TAU, _COL_OVERSHOOT, _COL_STEP = range(_NCOLS)

_STATUS_COLOR = {
    "waiting":       ("#e8e8e8", "#888888"),
    "not connected": ("#f0f0f0", "#b0b0b0"),
    "connected":     ("#e8f5e9", "#2e7d32"),
    "testing":       ("#fffde7", "#e65100"),
    "done":          ("#c8e6c9", "#1b5e20"),
    "suspicious":    ("#fff3e0", "#bf360c"),
    "no response":   ("#ffebee", "#c62828"),
}


def _status_key(status: str) -> str:
    if status.startswith("connected"):
        return "connected"
    if status.startswith("testing"):
        return "testing"
    return status


class BoardResultsTab(QWidget):
    def __init__(self, board_id, parent=None):
        super().__init__(parent)
        self.board_id = board_id
        self._results = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._table = QTableWidget(len(ACTIVE_MOTORS), _NCOLS)
        self._table.setHorizontalHeaderLabels(
            ["Motor", "Status", "min_pwm", "τ (ms)", "Overshoot (ADC)", "Actual step (ADC)"]
        )
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)

        for i in range(len(ACTIVE_MOTORS)):
            self._set_cell(i, _COL_MOTOR, f"M{ACTIVE_MOTORS[i] + 1}")
            self._set_cell(i, _COL_STATUS, "waiting", "waiting")
            for col in (_COL_MIN_PWM, _COL_TAU, _COL_OVERSHOOT, _COL_STEP):
                self._set_cell(i, col, "—")

        layout.addWidget(self._table)

        self._footer = QLabel("—")
        self._footer.setFont(QFont("Monospace", 9))
        layout.addWidget(self._footer)

    def on_motor_status(self, active_idx, status):
        self._set_cell(active_idx, _COL_STATUS, status, _status_key(status))

    def on_motor_result(self, active_idx, result):
        self._results[active_idx] = result
        if not result:
            return
        self._set_cell(active_idx, _COL_MIN_PWM, result["min_pwm"])
        tau = result.get("tau_ms")
        self._set_cell(active_idx, _COL_TAU, f"{tau:.0f}" if tau else "—")
        self._set_cell(active_idx, _COL_OVERSHOOT, f"{result['overshoot']:+.1f}")
        self._set_cell(active_idx, _COL_STEP, f"{result['actual_step']:+.1f}")

    def set_footer(self, text):
        self._footer.setText(text)

    def get_results(self):
        return self._results

    def get_summary(self):
        good       = {k: v for k, v in self._results.items() if v and not v.get("suspicious")}
        suspicious = {k: v for k, v in self._results.items() if v and v.get("suspicious")}
        all_valid  = {**good, **suspicious}
        if not all_valid:
            return None
        taus = [v["tau_ms"] for v in good.values() if v.get("tau_ms")]
        good_pwms = [v["min_pwm"] for v in good.values()]
        return {
            "board_id":            self.board_id,
            "responded":           len(all_valid),
            "suspicious":          len(suspicious),
            "recommended_min_pwm": max(good_pwms) if good_pwms else None,
            "avg_tau":             f"{sum(taus)/len(taus):.0f} ms" if taus else "n/a",
        }

    def _set_cell(self, row, col, text, status_key=None):
        item = QTableWidgetItem(str(text))
        item.setTextAlignment(Qt.AlignCenter)
        if status_key and status_key in _STATUS_COLOR:
            bg, fg = _STATUS_COLOR[status_key]
            item.setBackground(QColor(bg))
            item.setForeground(QColor(fg))
        self._table.setItem(row, col, item)


# ── Stylesheet ────────────────────────────────────────────────────────────────

_STYLE = """
QWidget { background: #f0f0f0; color: #111; font-size: 13px; }

QGroupBox {
    border: 1px solid #bbb;
    border-radius: 6px;
    margin-top: 14px;
    padding: 10px 8px 8px 8px;
    font-weight: bold;
    font-size: 12px;
    color: #444;
    background: #f8f8f8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 5px;
    background: #f0f0f0;
}

QSpinBox, QDoubleSpinBox, QLineEdit {
    background: white;
    border: 1px solid #bbb;
    border-radius: 4px;
    padding: 3px 7px;
    color: #111;
    min-height: 24px;
    min-width: 75px;
}
QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus { border-color: #4a7a4a; }

QPushButton {
    background: #e4e4e4;
    border: 1px solid #bbb;
    border-radius: 5px;
    padding: 5px 14px;
    color: #111;
    min-height: 28px;
}
QPushButton:hover   { background: #d8d8d8; border-color: #999; }
QPushButton:pressed { background: #ccc; }
QPushButton:disabled { color: #aaa; background: #eee; border-color: #ddd; }
QPushButton#start {
    background: #d4edda;
    border-color: #5a9a5a;
    color: #1a4a1a;
    font-weight: bold;
    font-size: 14px;
}
QPushButton#start:hover    { background: #c3e6cb; }
QPushButton#start:disabled { background: #eee; border-color: #ddd; color: #aaa; }

QTabWidget::pane { border: 1px solid #bbb; border-radius: 4px; }
QTabBar::tab {
    background: #e0e0e0;
    border: 1px solid #bbb;
    border-bottom: none;
    padding: 6px 16px;
    color: #666;
    border-radius: 4px 4px 0 0;
    margin-right: 2px;
    font-size: 12px;
}
QTabBar::tab:selected       { background: #f8f8f8; color: #111; }
QTabBar::tab:hover:!selected { background: #d4d4d4; color: #333; }

QTableWidget {
    background: white;
    gridline-color: #ddd;
    border: 1px solid #bbb;
    border-radius: 4px;
    font-size: 13px;
}
QTableWidget::item { padding: 5px; }
QHeaderView::section {
    background: #e8e8e8;
    border: none;
    border-right: 1px solid #ccc;
    border-bottom: 1px solid #ccc;
    padding: 6px;
    color: #444;
    font-weight: bold;
    font-size: 12px;
}

QTextEdit {
    background: #1e1e1e;
    border: 1px solid #bbb;
    border-radius: 4px;
    color: #7ec87e;
    font-family: monospace;
    font-size: 12px;
    padding: 4px;
}

QProgressBar {
    border: 1px solid #bbb;
    border-radius: 5px;
    background: #e0e0e0;
    text-align: center;
    color: #222;
    min-height: 24px;
    font-size: 13px;
}
QProgressBar::chunk { background: #5a9a5a; border-radius: 4px; margin: 1px; }

QCheckBox { spacing: 5px; font-size: 13px; }
QCheckBox::indicator {
    width: 15px; height: 15px;
    border: 1px solid #bbb;
    border-radius: 3px;
    background: white;
}
QCheckBox::indicator:checked { background: #5a9a5a; border-color: #3a7a3a; }
QCheckBox::indicator:hover   { border-color: #777; }

QSplitter::handle { background: #ccc; }
QLabel { font-size: 13px; }
"""

# ── Main window ───────────────────────────────────────────────────────────────

class CalibrationApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Motor Calibration")
        self.resize(1100, 880)

        self._workers         = []
        self._board_tabs      = {}
        self._boards_finished = 0
        self._boards_total    = 0
        self._run_timestamp   = ""

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(10, 10, 10, 10)

        root.addWidget(self._build_top())
        root.addWidget(self._build_controls())

        splitter = QSplitter(Qt.Vertical)
        splitter.addWidget(self._build_results())
        splitter.addWidget(self._build_bottom())
        splitter.setSizes([520, 230])
        root.addWidget(splitter, stretch=1)

    # ── panels ────────────────────────────────────────────────────────────────

    def _build_top(self):
        """Board selection + all parameter groups in one horizontal row."""
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        # Board selection
        boards = QGroupBox("Board selection")
        bl = QVBoxLayout(boards)
        bl.setSpacing(8)

        chan_row = QWidget()
        cl = QHBoxLayout(chan_row)
        cl.setContentsMargins(0, 0, 0, 0)
        cl.setSpacing(8)
        cl.addWidget(QLabel("CAN:"))
        self._channel = QLineEdit("can0")
        self._channel.setFixedWidth(80)
        cl.addWidget(self._channel)
        cl.addSpacing(8)
        all_btn = QPushButton("All")
        none_btn = QPushButton("None")
        all_btn.clicked.connect(lambda: [cb.setChecked(True) for cb in self._board_checks])
        none_btn.clicked.connect(lambda: [cb.setChecked(False) for cb in self._board_checks])
        cl.addWidget(all_btn)
        cl.addWidget(none_btn)
        cl.addStretch(1)
        bl.addWidget(chan_row)

        grid_w = QWidget()
        grid   = QGridLayout(grid_w)
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)
        self._board_checks = []
        for i in range(30):
            cb = QCheckBox(str(i + 1))
            self._board_checks.append(cb)
            grid.addWidget(cb, i // 10, i % 10)
        bl.addWidget(grid_w)
        layout.addWidget(boards)

        # Motion & Timing
        mt = QGroupBox("Motion && Timing")
        f1 = QFormLayout(mt)
        f1.setSpacing(8)
        f1.setContentsMargins(8, 12, 8, 8)
        f1.setLabelAlignment(Qt.AlignRight)
        self._step_size    = self._sb(60,  10, 200)
        self._move_thresh  = self._sb(10,   1, 100)
        self._step_timeout = self._dsb(2.0, 0.5, 30.0)
        self._settle_s     = self._dsb(1.5, 0.1, 10.0)
        f1.addRow("Step size (ADC):",      self._step_size)
        f1.addRow("Movement thresh (ADC):", self._move_thresh)
        f1.addRow("Step timeout (s):",     self._step_timeout)
        f1.addRow("Settle time (s):",      self._settle_s)
        layout.addWidget(mt)

        # PWM search
        pwm = QGroupBox("PWM stiction search")
        f2  = QFormLayout(pwm)
        f2.setSpacing(8)
        f2.setContentsMargins(8, 12, 8, 8)
        f2.setLabelAlignment(Qt.AlignRight)
        self._pwm_low  = self._sb(20, 0, 255)
        self._pwm_high = self._sb(90, 0, 255)
        self._pwm_step = self._sb(10, 1,  50)
        f2.addRow("Min PWM low:",  self._pwm_low)
        f2.addRow("Min PWM high:", self._pwm_high)
        f2.addRow("PWM step:",     self._pwm_step)
        layout.addWidget(pwm)

        # Calibration PID
        pid = QGroupBox("Calibration PID")
        f3  = QFormLayout(pid)
        f3.setSpacing(8)
        f3.setContentsMargins(8, 12, 8, 8)
        f3.setLabelAlignment(Qt.AlignRight)
        self._calib_kp       = self._sb(51, 0, 255)
        self._calib_ki       = self._sb( 0, 0, 255)
        self._calib_kd       = self._sb( 0, 0, 255)
        self._calib_alpha    = self._sb(51, 0, 255)
        self._calib_u_limit  = self._sb(60, 0, 255)
        self._calib_deadband = self._sb(10, 0, 255)
        f3.addRow("Kp:",       self._calib_kp)
        f3.addRow("Ki:",       self._calib_ki)
        f3.addRow("Kd:",       self._calib_kd)
        f3.addRow("Alpha:",    self._calib_alpha)
        f3.addRow("u_limit:",  self._calib_u_limit)
        f3.addRow("Deadband:", self._calib_deadband)
        layout.addWidget(pid)

        return row

    def _build_controls(self):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)

        self._start_btn = QPushButton("Start calibration")
        self._start_btn.setObjectName("start")
        self._start_btn.setFixedWidth(180)
        self._start_btn.clicked.connect(self._start)

        self._abort_btn = QPushButton("Abort")
        self._abort_btn.setFixedWidth(90)
        self._abort_btn.setEnabled(False)
        self._abort_btn.clicked.connect(self._abort)

        self._progress = QProgressBar()
        self._progress.setRange(0, 1)
        self._progress.setValue(0)
        self._progress.setFormat("boards: %v / %m")

        layout.addWidget(self._start_btn)
        layout.addWidget(self._abort_btn)
        layout.addWidget(self._progress, stretch=1)
        return row

    def _build_results(self):
        box = QGroupBox("Results")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(6, 6, 6, 6)
        self._tab_widget = QTabWidget()
        layout.addWidget(self._tab_widget)
        return box

    def _build_bottom(self):
        splitter = QSplitter(Qt.Horizontal)

        log_box = QGroupBox("Log")
        log_l   = QVBoxLayout(log_box)
        log_l.setContentsMargins(6, 6, 6, 6)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        log_l.addWidget(self._log)
        splitter.addWidget(log_box)

        summary_box = QGroupBox("Summary")
        summary_l   = QVBoxLayout(summary_box)
        summary_l.setContentsMargins(10, 10, 10, 10)
        self._summary = QLabel("Run calibration to see results.")
        self._summary.setFont(QFont("Monospace", 10))
        self._summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._summary.setWordWrap(True)
        summary_l.addWidget(self._summary)
        splitter.addWidget(summary_box)

        splitter.setSizes([560, 320])
        return splitter

    # ── widget factories ──────────────────────────────────────────────────────

    def _sb(self, default, lo, hi):
        w = QSpinBox()
        w.setRange(lo, hi)
        w.setValue(default)
        return w

    def _dsb(self, default, lo, hi):
        w = QDoubleSpinBox()
        w.setRange(lo, hi)
        w.setValue(default)
        w.setDecimals(1)
        return w

    # ── run logic ─────────────────────────────────────────────────────────────

    def _selected_boards(self):
        return [i + 1 for i, cb in enumerate(self._board_checks) if cb.isChecked()]

    def _collect_params(self):
        return {
            "channel":         self._channel.text().strip(),
            "step_size_adc":   self._step_size.value(),
            "movement_thresh": self._move_thresh.value(),
            "step_timeout_s":  self._step_timeout.value(),
            "settle_s":        self._settle_s.value(),
            "min_pwm_low":     self._pwm_low.value(),
            "min_pwm_high":    self._pwm_high.value(),
            "min_pwm_step":    self._pwm_step.value(),
            "calib_kp":        self._calib_kp.value(),
            "calib_ki":        self._calib_ki.value(),
            "calib_kd":        self._calib_kd.value(),
            "calib_alpha":     self._calib_alpha.value(),
            "calib_u_limit":   self._calib_u_limit.value(),
            "calib_deadband":  self._calib_deadband.value(),
        }

    def _start(self):
        boards = self._selected_boards()
        if not boards:
            self._log.append("Select at least one board before starting.")
            return

        self._log.clear()
        self._summary.setText("Running…")
        self._tab_widget.clear()
        self._board_tabs.clear()
        self._workers.clear()
        self._boards_finished = 0
        self._boards_total    = len(boards)
        self._run_timestamp   = datetime.now().strftime("%d.%m.%y_%H:%M")

        self._progress.setRange(0, self._boards_total)
        self._progress.setValue(0)
        self._progress.setFormat(f"boards: %v / {self._boards_total}")

        self._start_btn.setEnabled(False)
        self._abort_btn.setEnabled(True)

        params = self._collect_params()
        self._run_params = params  # snapshot — not re-read at save time

        for board_id in boards:
            tab = BoardResultsTab(board_id)
            self._tab_widget.addTab(tab, f"Board {board_id}")
            self._board_tabs[board_id] = tab

            worker = CalibrationWorker({**params, "board_id": board_id})
            worker.log.connect(self._on_log)
            worker.motor_status.connect(tab.on_motor_status)
            worker.motor_result.connect(tab.on_motor_result)
            worker.finished.connect(
                lambda r, bid=board_id: self._on_board_finished(bid, r)
            )
            self._workers.append(worker)

        for w in self._workers:
            w.start()

    def _abort(self):
        for w in self._workers:
            w.abort()
        self._abort_btn.setEnabled(False)

    def _on_log(self, msg):
        self._log.append(msg)

    def _on_board_finished(self, board_id, results):
        self._boards_finished += 1
        self._progress.setValue(self._boards_finished)

        tab = self._board_tabs.get(board_id)
        s   = tab.get_summary() if tab else None

        if s and s["recommended_min_pwm"] is not None:
            self._send_to_board(board_id, s["recommended_min_pwm"])

        if tab and s:
            parts = [f"{s['responded']} responded"]
            if s["suspicious"]:
                parts.append(f"{s['suspicious']} suspicious")
            parts += [f"min_pwm={s['recommended_min_pwm']}", f"τ={s['avg_tau']}"]
            tab.set_footer("   |   ".join(parts))
        elif tab:
            tab.set_footer("No motors responded.")

        if self._boards_finished >= self._boards_total:
            self._on_all_finished()

    def _save_all(self):
        os.makedirs(CALIBRATION_DIR, exist_ok=True)
        boards_out = {}
        for board_id, tab in self._board_tabs.items():
            results = tab.get_results()
            good_only = {k: v for k, v in results.items() if v and not v.get("suspicious")}
            boards_out[str(board_id)] = {
                "recommended_min_pwm": (
                    max(v["min_pwm"] for v in good_only.values()) if good_only else None
                ),
                "motors": {
                    str(ACTIVE_MOTORS[idx] + 1): r for idx, r in results.items()
                },
            }
        out = {
            "timestamp": self._run_timestamp,
            "params":    self._run_params,
            "boards":    boards_out,
        }
        fname = f"{self._run_timestamp}.json"
        path  = os.path.join(CALIBRATION_DIR, fname)
        with open(path, "w") as f:
            json.dump(out, f, indent=2)
        self._log.append(f"Saved → calibrations/{fname}")

    def _send_to_board(self, board_id, recommended_min_pwm):
        try:
            bus    = can.interface.Bus(channel=self._channel.text().strip(), interface="socketcan")
            can_id = 0x100 + board_id
            kp, ki, kd, alpha, u_limit, deadband = _RUNNING_CONFIG
            _send_config(bus, can_id, kp, ki, kd, alpha, u_limit, deadband, recommended_min_pwm)
            bus.shutdown()
            self._log.append(
                f"[Board {board_id}] Sent min_pwm={recommended_min_pwm} with running config."
            )
        except OSError as e:
            self._log.append(f"[Board {board_id}] Send failed: {e}")

    def _on_all_finished(self):
        self._start_btn.setEnabled(True)
        self._abort_btn.setEnabled(False)
        self._save_all()
        self._log.append("\n── All boards complete ──")

        lines = ["=== Final summary ==="]
        for board_id, tab in sorted(self._board_tabs.items()):
            s = tab.get_summary()
            if s:
                flag = f"  [{s['suspicious']} suspicious]" if s["suspicious"] else ""
                lines.append(
                    f"Board {board_id:2d}: {s['responded']:2d} responded{flag}"
                    f"  min_pwm={s['recommended_min_pwm']}  τ={s['avg_tau']}"
                )
            else:
                lines.append(f"Board {board_id:2d}: no motors responded")
        self._summary.setText("\n".join(lines))


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(_STYLE)
    win = CalibrationApp()
    win.show()
    sys.exit(app.exec())
