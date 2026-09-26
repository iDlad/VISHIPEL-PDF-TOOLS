"""
/src/ui/welcome_screen.py
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QLabel

from src.ui.vishipel_theme import COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY

# Lấy đường dẫn tới thư mục src/ui/
CURRENT_DIR = Path(__file__).resolve().parent
# Đường dẫn chính xác tới file ảnh trong src/ui/assets/welcome_illustration.png
ILLUSTRATION_PATH = CURRENT_DIR / "assets" / "welcome_illustration.png"


class WelcomeScreen(QWidget):

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Layout chính dạng Hàng ngang (Thu hẹp spacing từ 40 xuống 10)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(40, 40, 40, 40)
        main_layout.setSpacing(30)

        # ==========================================
        # CỘT TRÁI: KHỐI VĂN BẢN VÀ HƯỚNG DẪN
        # ==========================================
        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)
        left_layout.setAlignment(Qt.AlignVCenter | Qt.AlignLeft) 
        left_layout.setSpacing(18)
        left_layout.setContentsMargins(0, 0, 0, 0)

        # 1. Tiêu đề chính (Tăng lên 42px)
        title_label = QLabel("Vishipel PDF Tools")
        title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 55px; font-weight: 700;"
        )
        left_layout.addWidget(title_label)

        # 2. Dòng mô tả ngắn (Tăng lên 16px)
        description_label = QLabel(
            "Bộ công cụ xử lý, chỉnh sửa và quản lý file PDF\n"
            "nhanh chóng, an toàn và dễ dàng."
        )
        description_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 16px; line-height: 1.4;"
        )
        left_layout.addWidget(description_label)

        # Khoảng cách giữa mô tả và dòng hướng dẫn
        left_layout.addSpacing(15)

        # 3. Dòng hướng dẫn người dùng (Tăng lên 20px)
        instruction_label = QLabel("Chọn một tính năng ở thanh\nbên trái để bắt đầu")
        instruction_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 20px; font-weight: 600;"
        )
        left_layout.addWidget(instruction_label)

        # ==========================================
        # CỘT PHẢI: HÌNH ẢNH MINH HỌA
        # ==========================================
        illustration_label = QLabel()
        illustration_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)  # Căn sát lề trái để gần chữ hơn

        # Load hình ảnh minh họa
        pixmap = QPixmap(str(ILLUSTRATION_PATH))
        if not pixmap.isNull():
            illustration_label.setPixmap(
                pixmap.scaled(QSize(450, 450), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            illustration_label.setText(
                f"[ Chưa tìm thấy ảnh: {ILLUSTRATION_PATH.name} ]"
            )
            illustration_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px;"
            )
     
        main_layout.addStretch(1)                 
        main_layout.addWidget(left_container)      
        main_layout.addSpacing(40)                 
        main_layout.addWidget(illustration_label)  
        main_layout.addStretch(1)                  