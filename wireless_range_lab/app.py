"""Launch the Wireless Range Lab desktop application."""

import sys

from PyQt5.QtWidgets import QApplication

from range_lab.storage import TrialRepository
from range_lab.ui.main_window import MainWindow


def main() -> int:
    application = QApplication(sys.argv)
    repository = TrialRepository.from_project_root()
    window = MainWindow(repository)
    window.show()
    return application.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
