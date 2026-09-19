"""
Protect Feature Widget - Giao diện tính năng Bảo vệ / Đặt mật khẩu & Mở khóa PDF.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.ui.vishipel_theme import (
    COLOR_ACCENT,
    COLOR_BORDER,
    COLOR_BORDER_STRONG,
    COLOR_CONTENT_BG,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    CONTROL_HEIGHT,
    CORNER_RADIUS,
)

# Kích thước khung Preview
_THUMB_STRIP_WIDTH = 130


class PasswordStrengthBar(QWidget):
    """Thanh đo độ mạnh mật khẩu (3 vạch: Đỏ - Vàng - Xanh)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(6)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        spacing = 6
        segment_w = (w - spacing * 2) / 3

        # Đỏ (Yếu), Vàng (Trung bình), Xanh lá (Mạnh)
        colors = [QColor("#EF4444"), QColor("#F59E0B"), QColor("#10B981")]

        for i in range(3):
            painter.setBrush(colors[i])
            painter.setPen(Qt.PenStyle.NoPen)
            rect_x = i * (segment_w + spacing)
            painter.drawRoundedRect(int(rect_x), 0, int(segment_w), 6, 3, 3)


class PasswordInputField(QFrame):
    """Input field mật khẩu custom có Icon khóa ở trái và Icon mắt ở phải."""

    def __init__(self, placeholder: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(CONTROL_HEIGHT)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: #FFFFFF;
                border: 1px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
            }}
            QFrame:focus-within {{
                border: 1px solid {COLOR_ACCENT};
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        # Icon Khóa (Trái)
        self.lbl_icon = QLabel("🔒")
        self.lbl_icon.setStyleSheet("border: none; font-size: 14px;")
        layout.addWidget(self.lbl_icon)

        # Input field
        self.edit = QLineEdit()
        self.edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setStyleSheet(
            f"""
            QLineEdit {{
                border: none;
                background: transparent;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 13px;
            }}
            """
        )
        layout.addWidget(self.edit)

        # Icon Mắt (Phải)
        self.btn_toggle = QPushButton("👁")
        self.btn_toggle.setFixedSize(24, 24)
        self.btn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_toggle.setStyleSheet(
            f"""
            QPushButton {{
                border: none;
                background: transparent;
                color: {COLOR_TEXT_SECONDARY};
                font-size: 13px;
            }}
            QPushButton:hover {{
                color: {COLOR_TEXT_PRIMARY};
            }}
            """
        )
        layout.addWidget(self.btn_toggle)


class ProtectFeatureWidget(QWidget):
    """Widget chính cho tính năng Bảo vệ (Đặt mật khẩu & Mở khóa PDF)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # --- CỘT A: BẢNG ĐIỀU KHIỂN (TRÁI - 40%) ---
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(16)

        # A1. Khối Dropzone chọn file (Chỉ nhận 1 file)
        self.dropzone = QFrame()
        self.dropzone.setFixedHeight(110)
        self.dropzone.setStyleSheet(
            f"""
            QFrame {{
                background-color: {COLOR_CONTENT_BG};
                border: 2px dashed {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
            }}
            """
        )
        dz_layout = QVBoxLayout(self.dropzone)
        dz_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dz_layout.setSpacing(4)

        lbl_dz_icon = QLabel("📁")
        lbl_dz_icon.setStyleSheet("font-size: 24px; border: none;")
        lbl_dz_text = QLabel("Chọn file hoặc kéo-thả file vào đây")
        lbl_dz_text.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold; border: none; font-size: 13px;")
        lbl_dz_note = QLabel("Lưu ý: CHỈ CHỌN 1 FILE")
        lbl_dz_note.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; border: none;")

        dz_layout.addWidget(lbl_dz_icon, alignment=Qt.AlignmentFlag.AlignCenter)
        dz_layout.addWidget(lbl_dz_text, alignment=Qt.AlignmentFlag.AlignCenter)
        dz_layout.addWidget(lbl_dz_note, alignment=Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(self.dropzone)

        # A2. Khối Cài đặt (Tab Đặt mật khẩu / Mở khóa)
        settings_card = QFrame()
        settings_card.setStyleSheet(
            f"""
            QFrame#SettingsCard {{
                background-color: {COLOR_CONTENT_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: {CORNER_RADIUS}px;
            }}
            """
        )
        settings_card.setObjectName("SettingsCard")
        settings_layout = QVBoxLayout(settings_card)
        settings_layout.setContentsMargins(16, 16, 16, 16)
        settings_layout.setSpacing(16)

        # Tab Widget Custom
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: none;
            }}
            QTabBar::tab {{
                background: transparent;
                color: {COLOR_TEXT_SECONDARY};
                font-weight: bold;
                font-size: 13px;
                padding: 8px 16px;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: {COLOR_ACCENT};
                border-bottom: 2px solid {COLOR_ACCENT};
            }}
            """
        )

        # Tab 1: Đặt mật khẩu
        tab_set_pass = QWidget()
        tab_set_layout = QVBoxLayout(tab_set_pass)
        tab_set_layout.setContentsMargins(0, 12, 0, 0)
        tab_set_layout.setSpacing(12)

        # Pass inputs box
        pass_box = QFrame()
        pass_box.setStyleSheet(
            f"background-color: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: {CORNER_RADIUS}px;"
        )
        pass_box_layout = QVBoxLayout(pass_box)
        pass_box_layout.setContentsMargins(12, 12, 12, 12)
        pass_box_layout.setSpacing(8)

        lbl_p1 = QLabel("Nhập mật khẩu")
        lbl_p1.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none;")
        self.inp_pass1 = PasswordInputField("Tối thiểu 6 ký tự")

        lbl_p2 = QLabel("Xác nhận mật khẩu")
        lbl_p2.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none;")
        self.inp_pass2 = PasswordInputField("Nhập lại mật khẩu")

        self.strength_bar = PasswordStrengthBar()

        lbl_strength_title = QLabel("Độ mạnh mật khẩu")
        lbl_strength_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_strength_title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 11px; font-weight: bold; border: none;")

        pass_box_layout.addWidget(lbl_p1)
        pass_box_layout.addWidget(self.inp_pass1)
        pass_box_layout.addWidget(lbl_p2)
        pass_box_layout.addWidget(self.inp_pass2)
        pass_box_layout.addWidget(self.strength_bar)
        pass_box_layout.addWidget(lbl_strength_title)

        tab_set_layout.addWidget(pass_box)

        # Advanced Options (Luôn mở)
        adv_box = QFrame()
        adv_box.setStyleSheet(
            f"background-color: #FFFFFF; border: 1px solid {COLOR_BORDER}; border-radius: {CORNER_RADIUS}px;"
        )
        adv_layout = QVBoxLayout(adv_box)
        adv_layout.setContentsMargins(12, 12, 12, 12)
        adv_layout.setSpacing(10)

        adv_header = QHBoxLayout()
        lbl_adv_title = QLabel("Advanced Options")
        lbl_adv_title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold; font-size: 12px; border: none;")
        lbl_adv_arrow = QLabel("▼")
        lbl_adv_arrow.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; border: none;")
        adv_header.addWidget(lbl_adv_title)
        adv_header.addStretch()
        adv_header.addWidget(lbl_adv_arrow)
        adv_layout.addLayout(adv_header)

        lbl_perm_title = QLabel("Quyền truy cập và Chỉnh sửa")
        lbl_perm_title.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; border: none;")
        adv_layout.addWidget(lbl_perm_title)

        # Checkboxes
        chk_style = f"""
            QCheckBox {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 12px;
                border: none;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid {COLOR_BORDER_STRONG};
            }}
            QCheckBox::indicator:checked {{
                background-color: {COLOR_ACCENT};
                border-color: {COLOR_ACCENT};
            }}
        """
        self.chk_no_print = QCheckBox("Cấm in")
        self.chk_no_print.setChecked(True)
        self.chk_no_print.setStyleSheet(chk_style)

        self.chk_no_edit = QCheckBox("Cấm chỉnh sửa")
        self.chk_no_edit.setStyleSheet(chk_style)

        self.chk_no_copy = QCheckBox("Cấm sao chép nội dung")
        self.chk_no_copy.setChecked(True)
        self.chk_no_copy.setStyleSheet(chk_style)

        adv_layout.addWidget(self.chk_no_print)
        adv_layout.addWidget(self.chk_no_edit)
        adv_layout.addWidget(self.chk_no_copy)

        # Encryption Info Tag
        enc_info = QFrame()
        enc_info.setFixedHeight(CONTROL_HEIGHT - 6)
        enc_info.setStyleSheet(
            f"background-color: {COLOR_CONTENT_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 6px;"
        )
        enc_info_layout = QHBoxLayout(enc_info)
        enc_info_layout.setContentsMargins(8, 0, 8, 0)
        lbl_shield = QLabel("🛡️")
        lbl_shield.setStyleSheet("border: none;")
        lbl_enc_text = QLabel("Mã hóa AES 256-bit")
        lbl_enc_text.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; border: none;")
        enc_info_layout.addWidget(lbl_shield)
        enc_info_layout.addWidget(lbl_enc_text)
        enc_info_layout.addStretch()
        adv_layout.addWidget(enc_info)

        # Warning Note Box
        note_box = QFrame()
        note_box.setStyleSheet("background-color: #FEF3C7; border: none; border-radius: 6px;")
        note_layout = QVBoxLayout(note_box)
        note_layout.setContentsMargins(10, 8, 10, 8)
        lbl_note_txt = QLabel("Lưu ý: Mật khẩu này áp dụng cho cả quyền xem và chỉnh sửa file PDF.")
        lbl_note_txt.setWordWrap(True)
        lbl_note_txt.setStyleSheet("color: #92400E; font-size: 11px; border: none;")
        note_layout.addWidget(lbl_note_txt)
        adv_layout.addWidget(note_box)

        tab_set_layout.addWidget(adv_box)

        # Tab 2: Mở khóa
        tab_unlock = QWidget()
        tab_un_layout = QVBoxLayout(tab_unlock)
        tab_un_layout.setContentsMargins(0, 16, 0, 0)
        tab_un_layout.setSpacing(12)

        lbl_un_desc = QLabel("Nhập mật khẩu hiện tại của file PDF để tiến hành gỡ bỏ lớp bảo vệ.")
        lbl_un_desc.setWordWrap(True)
        lbl_un_desc.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; border: none;")

        lbl_un_pass = QLabel("Mật khẩu mở khóa")
        lbl_un_pass.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; font-weight: 500; border: none;")
        self.inp_unlock_pass = PasswordInputField("Nhập mật khẩu file PDF")

        tab_un_layout.addWidget(lbl_un_desc)
        tab_un_layout.addWidget(lbl_un_pass)
        tab_un_layout.addWidget(self.inp_unlock_pass)
        tab_un_layout.addStretch()

        # Add Tabs
        self.tab_widget.addTab(tab_set_pass, "Đặt mật khẩu")
        self.tab_widget.addTab(tab_unlock, "Mở khóa")

        settings_layout.addWidget(self.tab_widget)
        left_layout.addWidget(settings_card)

        # A3. Hàng Nút Hành Động Bottom
        actions_layout = QHBoxLayout()
        actions_layout.setSpacing(12)

        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setFixedHeight(CONTROL_HEIGHT)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setStyleSheet(
            f"""
            QPushButton {{
                background-color: #FFFFFF;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                font-weight: bold;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_CONTENT_BG};
            }}
            """
        )

        self.btn_submit = QPushButton("🔒 Đặt mật khẩu")
        self.btn_submit.setFixedHeight(CONTROL_HEIGHT)
        self.btn_submit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_submit.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
                border: none;
                border-radius: {CORNER_RADIUS}px;
                font-weight: bold;
                padding: 0 20px;
            }}
            QPushButton:hover {{
                background-color: #D97706;
            }}
            """
        )

        actions_layout.addWidget(self.btn_clear)
        actions_layout.addWidget(self.btn_submit, stretch=1)
        left_layout.addLayout(actions_layout)

        root_layout.addWidget(left_panel, stretch=4)

        # --- CỘT B: BẢNG PREVIEW (PHẢI - 60%) ---
        right_panel = QFrame()
        right_panel.setStyleSheet(
            f"""
            QFrame {{
                background-color: {COLOR_CONTENT_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: {CORNER_RADIUS}px;
            }}
            """
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        # Header Preview
        preview_header = QHBoxLayout()
        lbl_preview_title = QLabel("Xem trước: Tai lieu 02.pdf")
        lbl_preview_title.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-weight: bold; font-size: 13px; border: none;")

        # Zoom Controls
        zoom_box = QHBoxLayout()
        zoom_box.setSpacing(4)
        btn_zoom_out = QPushButton("−")
        lbl_zoom_val = QLabel("100%")
        btn_zoom_in = QPushButton("+")

        btn_zoom_style = f"""
            QPushButton {{
                background-color: #FFFFFF;
                border: 1px solid {COLOR_BORDER_STRONG};
                border-radius: 4px;
                min-width: 24px;
                max-width: 24px;
                min-height: 24px;
                max-height: 24px;
                font-weight: bold;
            }}
        """
        btn_zoom_out.setStyleSheet(btn_zoom_style)
        btn_zoom_in.setStyleSheet(btn_zoom_style)
        lbl_zoom_val.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; padding: 0 4px; border: none;")

        zoom_box.addWidget(btn_zoom_out)
        zoom_box.addWidget(lbl_zoom_val)
        zoom_box.addWidget(btn_zoom_in)

        preview_header.addWidget(lbl_preview_title)
        preview_header.addStretch()
        preview_header.addLayout(zoom_box)
        right_layout.addLayout(preview_header)

        # Area Preview Body (Thumbnails + Main View)
        preview_body = QHBoxLayout()
        preview_body.setSpacing(12)

        # Dải Thumbnails
        thumb_scroll = QScrollArea()
        thumb_scroll.setFixedWidth(_THUMB_STRIP_WIDTH)
        thumb_scroll.setWidgetResizable(True)
        thumb_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        thumb_container = QWidget()
        thumb_layout = QVBoxLayout(thumb_container)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setSpacing(10)

        # Tạo 4 trang mẫu ở dải thumbnail
        for idx in range(1, 5):
            thumb_item = QFrame()
            thumb_item.setFixedHeight(130)
            is_active = idx == 1
            border_col = COLOR_ACCENT if is_active else COLOR_BORDER
            thumb_item.setStyleSheet(
                f"background-color: #FFFFFF; border: 2px solid {border_col}; border-radius: 6px;"
            )
            item_layout = QVBoxLayout(thumb_item)
            item_layout.setContentsMargins(4, 4, 4, 4)

            lbl_page_num = QLabel(f"Trang {idx}")
            lbl_page_num.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_page_num.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px; border: none;")

            # Mock mini content
            mini_preview = QLabel("📄")
            mini_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            mini_preview.setStyleSheet("font-size: 28px; border: none;")

            item_layout.addWidget(mini_preview, stretch=1)
            item_layout.addWidget(lbl_page_num)
            thumb_layout.addWidget(thumb_item)

        thumb_layout.addStretch()
        thumb_scroll.setWidget(thumb_container)
        preview_body.addWidget(thumb_scroll)

        # Khung Preview chính lớn bên phải
        main_preview_scroll = QScrollArea()
        main_preview_scroll.setWidgetResizable(True)
        main_preview_scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        main_preview_widget = QWidget()
        main_preview_layout = QVBoxLayout(main_preview_widget)
        main_preview_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Trang PDF xem trước giả lập
        doc_page = QFrame()
        doc_page.setFixedSize(360, 500)
        doc_page.setStyleSheet(
            """
            QFrame {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 4px;
            }
            """
        )
        doc_layout = QVBoxLayout(doc_page)
        doc_layout.setContentsMargins(24, 24, 24, 24)

        # Dòng văn bản giả lập (Placeholder text lines)
        for _ in range(8):
            line = QFrame()
            line.setFixedHeight(8)
            line.setStyleSheet("background-color: #E2E8F0; border: none; border-radius: 4px;")
            doc_layout.addWidget(line)

        # Watermark mẫu chữ "CONFIDENTIAL"
        lbl_watermark = QLabel("CONFIDENTIAL")
        lbl_watermark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_watermark.setStyleSheet(
            """
            color: rgba(239, 68, 68, 0.25);
            font-size: 32px;
            font-weight: bold;
            border: none;
            """
        )
        doc_layout.addWidget(lbl_watermark, stretch=1)

        for _ in range(6):
            line = QFrame()
            line.setFixedHeight(8)
            line.setStyleSheet("background-color: #E2E8F0; border: none; border-radius: 4px;")
            doc_layout.addWidget(line)

        main_preview_layout.addWidget(doc_page)
        main_preview_scroll.setWidget(main_preview_widget)
        preview_body.addWidget(main_preview_scroll, stretch=1)

        right_layout.addLayout(preview_body)
        root_layout.addWidget(right_panel, stretch=6)

        # Cập nhật nhãn nút khi đổi Tab
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def _on_tab_changed(self, index: int) -> None:
        """Đổi văn bản nút Submit khi chuyển đổi tab."""
        if index == 0:
            self.btn_submit.setText("🔒 Đặt mật khẩu")
        else:
            self.btn_submit.setText("🔓 Mở khóa PDF")