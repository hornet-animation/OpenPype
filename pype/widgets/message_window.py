import sys
import logging

from avalon.vendor.Qt.QtWidgets import QApplication, QWidget, QPushButton, QMessageBox

log = logging.getLogger(__name__)


class Window(QWidget):
    def __init__(self, title, message, level):
        super().__init__()
        self.title = title
        self.message = message
        self.level = level

        if self.level is "info":
            self._info()
        elif self.level is "warning":
            self._warning()
        elif self.level is "critical":
            self._critical()

    def _info(self):
        self.setWindowTitle(self.title)
        rc = QMessageBox.information(
            self, self.title, self.message)
        if rc:
            sys.exit(app.exec_())

    def _warning(self):
        self.setWindowTitle(self.title)
        rc = QMessageBox.warning(
            self, self.title, self.message)
        if rc:
            sys.exit(app.exec_())

    def _critical(self):
        self.setWindowTitle(self.title)
        rc = QMessageBox.critical(
            self, self.title, self.message)
        if rc:
            sys.exit(app.exec_())


def message(title=None, message=None, level="info"):
    global app
    app = QApplication(sys.argv)
    ex = Window(title, message, level)
    ex.show()
    sys.exit(app.exec_())
