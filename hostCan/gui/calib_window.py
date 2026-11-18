import sys

from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QTabWidget, QWidget, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QSpinBox, QHeaderView, QAbstractItemView,
    QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from limits import save_limit_file, load_all_limits
from config import MIN_LIMITS_FILE


class CalibrationWindow:
    def __init__(self, engine, parent=None):
        self._engine = engine
        self._board_count = engine.board_count
        self._motors = engine.motors_per_board

        self._app = QApplication.instance() or QApplication(sys.argv)

        self._dialog = QDialog(parent)
        self._dialog.setWindowTitle("Calibration — Edit limits")
        self._dialog.resize(1100, 560)

        root = QVBoxLayout(self._dialog)

        self._tabs = QTabWidget()
        self._min_table = self._make_table()
        self._tabs.addTab(self._wrap_tab(self._min_table, "min"), "Min limits")
        root.addWidget(self._tabs, stretch=1)

        # bottom buttons
        btn_row = QWidget()
        btn_l = QHBoxLayout(btn_row)
        btn_l.setContentsMargins(0, 4, 0, 0)

        save_btn = QPushButton("Save to files")
        save_btn.clicked.connect(self._save)

        reload_btn = QPushButton("Reload from files")
        reload_btn.clicked.connect(self._reload)

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self._dialog.reject)

        btn_l.addWidget(save_btn)
        btn_l.addWidget(reload_btn)
        btn_l.addStretch(1)
        btn_l.addWidget(close_btn)
        root.addWidget(btn_row)

        min_limits, _ = load_all_limits()
        self._load_data(min_limits)

    # ── table factory ─────────────────────────────────────────────────────────

    def _make_table(self):
        t = QTableWidget(self._motors, self._board_count)
        t.setHorizontalHeaderLabels([str(b + 1) for b in range(self._board_count)])
        t.setVerticalHeaderLabels([f"M{m + 1}" for m in range(self._motors)])
        t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        t.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        t.setSelectionMode(QAbstractItemView.ContiguousSelection)
        return t

    def _wrap_tab(self, table, which):
        w = QWidget()
        l = QVBoxLayout(w)

        # fill-all convenience row
        fill_row = QWidget()
        fill_l = QHBoxLayout(fill_row)
        fill_l.setContentsMargins(0, 0, 0, 4)

        fill_l.addWidget(QLabel("Fill selection with:"))
        spin = QSpinBox()
        spin.setRange(0, 255)
        spin.setFixedWidth(70)
        fill_l.addWidget(spin)

        fill_sel_btn = QPushButton("Fill selection")
        fill_sel_btn.clicked.connect(lambda: self._fill_selection(table, spin.value()))

        fill_all_btn = QPushButton("Fill all")
        fill_all_btn.clicked.connect(lambda: self._fill_all(table, spin.value()))

        fill_l.addWidget(fill_sel_btn)
        fill_l.addWidget(fill_all_btn)
        fill_l.addStretch(1)
        l.addWidget(fill_row)
        l.addWidget(table, stretch=1)
        return w

    # ── data helpers ──────────────────────────────────────────────────────────

    def _load_data(self, min_limits):
        for m in range(self._motors):
            for b in range(self._board_count):
                self._set_cell(self._min_table, m, b, min_limits[b][m])

    def _set_cell(self, table, row, col, value):
        item = QTableWidgetItem(str(int(value)))
        item.setTextAlignment(Qt.AlignCenter)
        table.setItem(row, col, item)

    def _read_table(self, table, default):
        limits = [[default] * self._motors for _ in range(self._board_count)]
        for m in range(self._motors):
            for b in range(self._board_count):
                item = table.item(m, b)
                if item is None:
                    continue
                try:
                    v = int(item.text())
                    limits[b][m] = max(0, min(255, v))
                except ValueError:
                    limits[b][m] = default
        return limits

    # ── fill helpers ──────────────────────────────────────────────────────────

    def _fill_selection(self, table, value):
        for item in table.selectedItems():
            item.setText(str(value))

    def _fill_all(self, table, value):
        for m in range(self._motors):
            for b in range(self._board_count):
                item = table.item(m, b)
                if item:
                    item.setText(str(value))

    # ── save / reload ─────────────────────────────────────────────────────────

    def _save(self):
        from config import DEFAULT_MIN_LIMIT
        min_limits = self._read_table(self._min_table, DEFAULT_MIN_LIMIT)
        save_limit_file(MIN_LIMITS_FILE, min_limits)
        self._engine.reload_limits()

    def _reload(self):
        min_limits, _ = load_all_limits()
        self._load_data(min_limits)

    # ── entry point ───────────────────────────────────────────────────────────

    def show(self):
        self._dialog.exec()
