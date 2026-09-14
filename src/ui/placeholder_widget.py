"""
Widget placeholder tạm thời cho từng tính năng — dùng ở Giai đoạn 1 khi chưa
gắn logic thật. Mỗi tính năng sẽ được thay bằng widget riêng trong
src/ui/tools/ ở Giai đoạn 3 (xem 05_lo_trinh_phat_trien.md).
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from src.ui.vishipel_theme import COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY


class PlaceholderFeatureWidget(QWidget):
    """Hiển thị tạm tiêu đề tính năng, chưa có chức năng xử lý PDF thật."""

    def __init__(self, feature_title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(8)

        title_label = QLabel(feature_title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 20px; font-weight: 500;"
        )
        layout.addWidget(title_label)

        note_label = QLabel("Tính năng đang được phát triển")
        note_label.setAlignment(Qt.AlignCenter)
        note_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px;")
        layout.addWidget(note_label)
