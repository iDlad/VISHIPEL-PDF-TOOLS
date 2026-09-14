"""
Vishipel PDF Tools — điểm khởi chạy ứng dụng.
Giai đoạn 1: chỉ dựng khung sườn giao diện, chưa gắn logic xử lý PDF thật.
"""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from src.ui.main_window import MainWindow
from src.ui.vishipel_theme import GLOBAL_STYLESHEET


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(GLOBAL_STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
