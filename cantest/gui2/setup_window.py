import sys
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QComboBox, QPushButton

from communication import can_search


class SetupWindow:
    def __init__(self):
        self._app = QApplication.instance() or QApplication(sys.argv)

        channels = can_search()
        self.started = False
        self._channel = channels[0]

        dialog = QDialog()
        dialog.setWindowTitle("Setup")
        dialog.setFixedHeight(60)

        layout = QHBoxLayout(dialog)
        layout.addWidget(QLabel("CAN channel:"))

        self._combo = QComboBox()
        self._combo.addItems(channels)
        layout.addWidget(self._combo)

        btn = QPushButton("Start")
        btn.clicked.connect(lambda: self._on_start(dialog))
        layout.addWidget(btn)

        dialog.exec()

    def _on_start(self, dialog):
        self.started = True
        self._channel = self._combo.currentText()
        dialog.accept()

    def get_channel(self):
        return self._channel
