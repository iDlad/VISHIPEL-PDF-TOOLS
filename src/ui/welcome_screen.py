"""
Màn hình chào — hiển thị mặc định khi mở app, trước khi người dùng chọn bất kỳ
tính năng nào ở sidebar (xem 01_dac_ta_giao_dien.md mục 7). Không có nút bấm
hay thao tác nào khác trên màn hình này.
"""
from __future__ import annotations

import qtawesome as qta
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.vishipel_theme import COLOR_ACCENT, COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY


class WelcomeScreen(QWidget):
    """Logo + tên app + dòng hướng dẫn ngắn, căn giữa khung nội dung."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        # Khối vuông bo góc màu accent chứa icon file PDF màu trắng
        icon_label = QLabel()
        icon_label.setFixedSize(56, 56)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; border-radius: 14px;"
        )
        icon_label.setPixmap(qta.icon("mdi6.file-pdf-box", color="white").pixmap(28, 28))
        layout.addWidget(icon_label, alignment=Qt.AlignCenter)

        title_label = QLabel("Vishipel PDF Tools")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 20px; font-weight: 500;"
        )
        layout.addWidget(title_label)

        subtitle_label = QLabel("Chọn một tính năng ở thanh bên trái để bắt đầu")
        subtitle_label.setAlignment(Qt.AlignCenter)
        subtitle_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px;")
        layout.addWidget(subtitle_label)
