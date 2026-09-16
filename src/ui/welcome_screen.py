"""
Màn hình chào — hiển thị mặc định khi mở app, trước khi người dùng chọn bất kỳ
tính năng nào ở sidebar (xem 01_dac_ta_giao_dien.md mục 7). Không có nút bấm
hay thao tác nào khác trên màn hình này.
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
    """
    Màn hình chào thiết kế mới: Layout 2 cột (Text bên trái, Minh họa bên phải)
    với cỡ chữ lớn và khoảng cách tối ưu.
    """

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

        # Thêm các Widget vào Layout chính:
        # Dùng addStretch() ở 2 đầu để "đẩy" khối Text đến vị trí bạn muốn
        
        main_layout.addStretch(1)                  # 👈 Khoảng trống bên trái ngoài cùng
        main_layout.addWidget(left_container)       # Khối Text
        main_layout.addSpacing(40)                 # 👈 KHOẢNG CÁCH CHÍNH XÁC GIỮA TEXT VÀ ẢNH (Sửa số này để tăng/giảm)
        main_layout.addWidget(illustration_label)  # Khối Ảnh
        main_layout.addStretch(1)                  # 👈 Khoảng trống bên phải ngoài cùng