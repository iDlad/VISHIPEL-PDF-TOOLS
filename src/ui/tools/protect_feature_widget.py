"""
Giao diện tính năng Bảo vệ (Protect) — Đặt mật khẩu / Mở khóa file PDF.

Đồng bộ hoàn toàn với thiết kế của merge_widget.py:
- Cột A (40%): Drop zone (CHỈ CHỌN 1 FILE) → segmented tab Đặt mật khẩu / Mở khóa
  → nội dung thay đổi theo tab → hàng nút hành động cuối cùng.
- Cột B (60%): Card xem trước giống Merge — header có cụm Zoom In/Out ±15%
  (50%-200%), dải thumbnail trái (đồng bộ 1 chiều: click → cuộn khung lớn),
  khung lớn dùng _PannablePreviewScrollArea (cuộn chuột + pan chuột trái).

Luồng nghiệp vụ THẬT (đã nối pdf_core, xem 02_dac_ta_tinh_nang.md mục 6):
- Tab Đặt mật khẩu: chọn 1 file KHÔNG có mật khẩu → render preview thật ngay.
  Nếu file đã có mật khẩu/giới hạn → báo lỗi, yêu cầu dùng tab Mở khóa trước.
  Validate: đã chọn file, mật khẩu không trống, 2 ô khớp nhau → protect_pdf().
- Tab Mở khóa: chọn file đã có mật khẩu/giới hạn.
  * Cần User Password (needs_password): Cột B giữ trạng thái "khóa", KHÔNG render
    nội dung cho tới khi nhập đúng mật khẩu và authenticate() thành công.
  * Chỉ có Owner Password (owner-only, không cần mật khẩu mở): render Cột B ngay
    (nội dung vốn đọc tự do được), ẩn ô mật khẩu, hỏi xác nhận riêng lúc bấm Lưu File.
  Lưu File luôn xuất ra 1 file MỚI hoàn toàn không còn mật khẩu/giới hạn.

Advanced Options luôn mở, cố định — không có trạng thái thu gọn.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QButtonGroup,
    QStackedWidget,
    QScrollArea,
    QFrame,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QDialog,
)

from src import pdf_core
from src import logger

from src.ui.vishipel_theme import (
    COLOR_ACCENT,
    COLOR_ACCENT_LIGHT,
    COLOR_BORDER,
    COLOR_BORDER_STRONG,
    COLOR_CONTENT_BG,
    COLOR_TEXT_PRIMARY,
    COLOR_TEXT_SECONDARY,
    COLOR_SUCCESS,
    COLOR_ERROR,
    CONTROL_HEIGHT,
    CORNER_RADIUS,
)

# ---------------------------------------------------------------------------
# Hằng số layout
# ---------------------------------------------------------------------------
_ROW_ICON_SIZE = 34
_DROPZONE_ICON_BOX = 56

# Cột B — giữ nguyên hằng số giống merge_widget.py để 2 màn hình zoom giống nhau.
_THUMB_STRIP_WIDTH = 115
_THUMB_W, _THUMB_H = 72, 94
_BADGE_SIZE = 18

_ZOOM_MIN = 0.5
_ZOOM_MAX = 2.0
_ZOOM_STEP = 0.15
_ZOOM_DEFAULT = 1.0

_PREVIEW_SIDE_MARGIN = 12
_PREVIEW_MIN_PAGE_WIDTH = 220
_PREVIEW_PAGE_WIDTH_FALLBACK = 340
_PREVIEW_PAGE_HEIGHT_DEFAULT = 460
_DEFAULT_ASPECT_RATIO = _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK

# Chiều cao ô nhập mật khẩu + nút con mắt (nút mắt nền cam, theo ảnh thiết kế).
_PASSWORD_INPUT_HEIGHT = 52
_EYE_BUTTON_WIDTH = 52
_EYE_BUTTON_HEIGHT = 40
# Nút "Bắt đầu Mở khóa" full-width, cao hơn nút thường (theo ảnh Mở khóa).
_UNLOCK_CTA_HEIGHT = 52

# Advanced Options — màu chip + banner cảnh báo.
_CHIP_BG = "#F3F4F6"

# Tên file gợi ý mặc định (chưa có trong 02_dac_ta_tinh_nang.md mục 6, đã thống nhất
# riêng cho lần nối logic này — theo đúng khuôn mẫu "<gốc>_<hậu tố>.pdf" như Edit/Chèn).
_DEFAULT_SUFFIX_PROTECT = "_protected"
_DEFAULT_SUFFIX_UNLOCK = "_unlocked"

# Ngưỡng quy đổi điểm 0-100 của pdf_core.calculate_password_strength() sang 3 mức
# hiển thị trên _StrengthMeter (đã thống nhất riêng cho lần nối logic này).
_STRENGTH_WEAK_MAX = 40
_STRENGTH_MEDIUM_MAX = 70

_SCROLLBAR_QSS = f"""
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 4px 2px 4px 0px;
    }}
    QScrollBar::handle:vertical {{
        background: {COLOR_BORDER_STRONG};
        border-radius: 4px;
        min-height: 32px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {COLOR_ACCENT};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
        background: transparent;
        border: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
"""


def _zoom_button_style() -> str:
    """Style cụm Zoom In/Out ở header Cột B — copy nguyên từ merge_widget.py."""
    return f"""
        QToolButton {{
            background-color: white;
            border: 1.5px solid {COLOR_BORDER_STRONG};
            border-radius: 6px;
        }}
        QToolButton:hover:enabled {{
            background-color: {COLOR_ACCENT_LIGHT};
            border-color: {COLOR_ACCENT};
        }}
        QToolButton:pressed:enabled {{
            background-color: {COLOR_ACCENT};
        }}
        QToolButton:disabled {{
            background-color: #F3F4F6;
            border-color: {COLOR_BORDER};
        }}
        """


def _primary_button_style() -> str:
    """Style nút hành động chính (Accent) — dùng chung cho ProtectFeatureWidget và các
    dialog tự vẽ bên dưới (_OverwriteConfirmDialog/_ConfirmDialog)."""
    return f"""
        QPushButton {{
            background-color: {COLOR_ACCENT};
            color: white;
            border: none;
            border-radius: {CORNER_RADIUS}px;
            font-size: 13px;
            font-weight: 700;
            padding: 0 16px;
        }}
        QPushButton:hover:enabled {{ background-color: #E28104; }}
        QPushButton:pressed:enabled {{ background-color: #C87203; }}
        QPushButton:disabled {{ background-color: #FDBA74; }}
        """


def _secondary_button_style() -> str:
    """Style nút phụ (viền, nền trắng) — dùng chung cho ProtectFeatureWidget và các
    dialog tự vẽ bên dưới."""
    return f"""
        QPushButton {{
            background-color: white;
            color: {COLOR_TEXT_PRIMARY};
            border: 1.5px solid {COLOR_BORDER_STRONG};
            border-radius: {CORNER_RADIUS}px;
            font-size: 13px;
            font-weight: 700;
            padding: 0 16px;
        }}
        QPushButton:hover {{ background-color: #F3F4F6; }}
        QPushButton:pressed {{ background-color: #E5E7EB; }}
        """


# ---------------------------------------------------------------------------
# A1 — Drop zone (CHỈ CHỌN 1 FILE) — copy layout từ merge_widget.py
# ---------------------------------------------------------------------------
class _DropZone(QFrame):
    files_selected = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(96)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 1.5px dashed {COLOR_BORDER_STRONG};
                border-radius: 14px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        icon_box = QFrame()
        icon_box.setFixedSize(_DROPZONE_ICON_BOX, _DROPZONE_ICON_BOX)
        icon_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 2px solid {COLOR_ACCENT};
                border-radius: 12px;
            }}
            """
        )
        icon_box_layout = QVBoxLayout(icon_box)
        icon_box_layout.setContentsMargins(0, 0, 0, 0)
        icon_box_layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.tray-arrow-up", color=COLOR_ACCENT).pixmap(QSize(28, 28)))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_box_layout.addWidget(icon_label)
        layout.addWidget(icon_box)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        main_label = QLabel("Chọn file hoặc kéo-thả file vào đây")
        main_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(main_label)

        note_label = QLabel("Lưu ý: CHỈ CHỌN 1 FILE")
        note_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(note_label)

        layout.addLayout(text_col)

    def _open_file_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file PDF", "", "PDF Files (*.pdf)")
        if path:
            self.files_selected.emit([path])

    def mousePressEvent(self, event) -> None:
        self._open_file_dialog()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(".pdf")
        ]
        if paths:
            # Bảo vệ chỉ dùng 1 file — nếu kéo nhiều file thì chỉ lấy file đầu.
            self.files_selected.emit(paths[:1])


# ---------------------------------------------------------------------------
# A2 — Segmented tab: Đặt mật khẩu / Mở khóa
# Tự vẽ bằng 2 QPushButton checkable trong khung nền xám — dễ sửa, không phụ
# thuộc style mặc định của QTabWidget.
# ---------------------------------------------------------------------------
class _ModeTabs(QFrame):
    mode_changed = Signal(str)  # "set" | "unlock"

    MODE_SET = "set"
    MODE_UNLOCK = "unlock"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(48)
        self.setStyleSheet(
            f"QFrame {{ background-color: {_CHIP_BG}; border: none; border-radius: 10px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        self.set_tab_btn = QPushButton("Đặt mật khẩu")
        self.unlock_tab_btn = QPushButton("Mở khóa")
        for btn in (self.set_tab_btn, self.unlock_tab_btn):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(40)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: transparent;
                    border: none;
                    border-radius: 8px;
                    color: {COLOR_TEXT_SECONDARY};
                    font-size: 14px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    color: {COLOR_TEXT_PRIMARY};
                }}
                QPushButton:checked {{
                    background-color: white;
                    border: 1px solid {COLOR_BORDER};
                    color: {COLOR_TEXT_PRIMARY};
                    font-weight: 700;
                }}
                """
            )
            self.button_group.addButton(btn)
            layout.addWidget(btn)

        self.set_tab_btn.setChecked(True)
        self.set_tab_btn.clicked.connect(lambda: self.mode_changed.emit(self.MODE_SET))
        self.unlock_tab_btn.clicked.connect(lambda: self.mode_changed.emit(self.MODE_UNLOCK))

    def mode(self) -> str:
        return self.MODE_UNLOCK if self.unlock_tab_btn.isChecked() else self.MODE_SET


# ---------------------------------------------------------------------------
# A3 — Ô nhập mật khẩu: icon ổ khóa trái + nút con mắt nền cam bên phải
# ---------------------------------------------------------------------------
class _PasswordInput(QFrame):
    def __init__(self, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(_PASSWORD_INPUT_HEIGHT)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: 10px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 6, 0)
        layout.setSpacing(10)

        lock_icon = QLabel()
        lock_icon.setPixmap(qta.icon("mdi6.lock-outline", color=COLOR_TEXT_SECONDARY).pixmap(QSize(20, 20)))
        lock_icon.setStyleSheet("background: transparent; border: none;")
        lock_icon.setFixedWidth(20)
        layout.addWidget(lock_icon)

        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setEchoMode(QLineEdit.Password)  # Mặc định mã hóa mật khẩu thành dấu chấm
        self.edit.setStyleSheet(
            f"""
            QLineEdit {{
                background: transparent;
                border: none;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 14px;
                font-weight: 600;
            }}
            """
        )
        layout.addWidget(self.edit, 1)

        self.eye_btn = QToolButton()
        self.eye_btn.setCursor(Qt.PointingHandCursor)
        self.eye_btn.setFixedSize(_EYE_BUTTON_WIDTH, _EYE_BUTTON_HEIGHT)
        # Mặc định: Mật khẩu ẩn -> Nút hiển thị MẮT NHẮM
        self.eye_btn.setIcon(qta.icon("mdi6.eye-off-outline", color="white"))
        self.eye_btn.setIconSize(QSize(20, 20))
        self.eye_btn.setToolTip("Hiện/ẩn mật khẩu")
        self.eye_btn.setStyleSheet(
            f"""
            QToolButton {{
                background-color: {COLOR_ACCENT};
                border: none;
                border-radius: 8px;
            }}
            QToolButton:hover {{
                background-color: #E28104;
            }}
            QToolButton:pressed {{
                background-color: #C87203;
            }}
            """
        )
        self.eye_btn.clicked.connect(self._toggle_echo)
        layout.addWidget(self.eye_btn)

    def _toggle_echo(self) -> None:
        # Nếu đang ở chế độ ẨN (Password):
        if self.edit.echoMode() == QLineEdit.Password:
            self.edit.setEchoMode(QLineEdit.Normal)  # 1. Chuyển sang HIỆN mật khẩu
            self.eye_btn.setIcon(qta.icon("mdi6.eye-outline", color="white"))  # 2. Đổi icon sang MẮT MỞ
        # Nếu đang ở chế độ HIỆN (Normal):
        else:
            self.edit.setEchoMode(QLineEdit.Password)  # 1. Chuyển sang ẨN mật khẩu (dấu chấm)
            self.eye_btn.setIcon(qta.icon("mdi6.eye-off-outline", color="white"))  # 2. Đổi icon sang MẮT NHẮM

    def text(self) -> str:
        return self.edit.text()

    def clear(self) -> None:
        self.edit.clear()


# ---------------------------------------------------------------------------
# A4 — Thanh đo độ mạnh mật khẩu (3 đoạn: đỏ / cam / xanh)
# ---------------------------------------------------------------------------
class _StrengthMeter(QWidget):
    _LEVELS = {
        0: ("", COLOR_BORDER),
        1: ("Yếu", COLOR_ERROR),
        2: ("Trung bình", COLOR_ACCENT),
        3: ("Mạnh", COLOR_SUCCESS),
    }

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        segments_row = QHBoxLayout()
        segments_row.setSpacing(6)
        self.segments: List[QFrame] = []
        for _ in range(3):
            seg = QFrame()
            seg.setFixedHeight(6)
            seg.setStyleSheet(
                f"QFrame {{ background-color: {COLOR_BORDER}; border: none; border-radius: 3px; }}"
            )
            segments_row.addWidget(seg, 1)
            self.segments.append(seg)
        layout.addLayout(segments_row)

        self.label = QLabel("Độ mạnh mật khẩu")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.label)

        self.set_score(0)

    def set_score(self, score: int) -> None:
        score = max(0, min(3, score))
        for i, seg in enumerate(self.segments):
            color = self._LEVELS[score][1] if i < score else COLOR_BORDER
            seg.setStyleSheet(
                f"QFrame {{ background-color: {color}; border: none; border-radius: 3px; }}"
            )
        level_text, level_color = self._LEVELS[score]
        if level_text:
            self.label.setText(f"Độ mạnh mật khẩu — {level_text}")
            self.label.setStyleSheet(
                f"color: {level_color}; font-size: 12px; font-weight: 700; "
                "background: transparent; border: none;"
            )
        else:
            self.label.setText("Độ mạnh mật khẩu")
            self.label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
                "background: transparent; border: none;"
            )


# ---------------------------------------------------------------------------
# A5 — Checkbox tùy biến (vẽ bằng QToolButton checkable + icon check qtawesome)
# Tự vẽ thay vì style QCheckBox::indicator vì QSS không tự vẽ dấu check khi
# custom indicator — cách này render chuẩn trên mọi platform.
# ---------------------------------------------------------------------------
class _ToggleCheck(QToolButton):
    def __init__(self, label: str, checked: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.setIconSize(QSize(22, 22))
        self.setText(f" {label}")
        self._label_color = COLOR_TEXT_PRIMARY
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        # SỬA: Sử dụng icon ô checkbox rõ ràng thay vì làm trong suốt icon
        if self.isChecked():
            self.setIcon(qta.icon("mdi6.checkbox-marked", color=COLOR_ACCENT))
        else:
            self.setIcon(qta.icon("mdi6.checkbox-blank-outline", color=COLOR_BORDER_STRONG))

        self.setStyleSheet(
            f"""
            QToolButton {{
                border: none;
                background: transparent;
                color: {self._label_color};
                font-size: 14px;
                font-weight: 600;
            }}
            """
        )

    def nextCheckState(self) -> None:
        super().nextCheckState()
        self._refresh_icon()


# ---------------------------------------------------------------------------
# A6 — Advanced Options: luôn mở, cố định, KHÔNG có nút thu gọn.
# Gồm: tiêu đề + 3 quyền hạn (checkbox) + chip AES 256-bit + banner cảnh báo.
# ---------------------------------------------------------------------------
class _AdvancedOptions(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: 14px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # Tiêu đề (bỏ icon mũi tên collapse theo yêu cầu).
        title_row = QHBoxLayout()
        title_icon = QLabel()
        title_icon.setPixmap(qta.icon("mdi6.cog-outline", color=COLOR_TEXT_SECONDARY).pixmap(QSize(18, 18)))
        title_icon.setStyleSheet("background: transparent; border: none;")
        title_row.addWidget(title_icon)
        title_label = QLabel("Quyền truy cập và Chỉnh sửa")
        title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        title_row.addWidget(title_label)
        title_row.addStretch()
        layout.addLayout(title_row)

        # 3 quyền hạn — "Cấm In" mặc định được tick (theo ảnh thiết kế).
        # Thứ tự PHẢI khớp đúng build_protection_permissions(cam_in, cam_chinh_sua, cam_sao_chep).
        self.checks: List[_ToggleCheck] = []
        for label, checked in (
            ("Cấm In", True),
            ("Cấm Chỉnh sửa", False),
            ("Cấm Sao chép nội dung", False),
        ):
            check = _ToggleCheck(label, checked)
            layout.addWidget(check)
            self.checks.append(check)

        # Chip "Mã hóa AES 256-bit".
        chip = QFrame()
        chip.setStyleSheet(
            f"QFrame {{ background-color: {_CHIP_BG}; border-radius: 12px; border: none; }}"
        )
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(12, 6, 12, 6)
        chip_layout.setSpacing(8)
        chip_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        chip_icon = QLabel()
        chip_icon.setPixmap(qta.icon("mdi6.shield-check-outline", color=COLOR_TEXT_PRIMARY).pixmap(QSize(16, 16)))
        chip_icon.setStyleSheet("background: transparent; border: none;")
        chip_layout.addWidget(chip_icon)

        chip_text = QLabel("Mã hóa AES 256-bit")
        chip_text.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        chip_layout.addWidget(chip_text)

        layout.addWidget(chip)

        # Banner cảnh báo (nền cam nhạt, viền cam).
        banner = QFrame()
        banner.setStyleSheet(
            f"QFrame {{ background-color: {COLOR_ACCENT_LIGHT}; border: 1px solid {COLOR_ACCENT}; "
            "border-radius: 10px; }"
        )
        banner_layout = QHBoxLayout(banner)
        banner_layout.setContentsMargins(12, 10, 12, 10)
        banner_layout.setSpacing(10)
        warn_icon = QLabel()
        warn_icon.setPixmap(qta.icon("mdi6.alert-outline", color=COLOR_ACCENT).pixmap(QSize(20, 20)))
        warn_icon.setFixedSize(20, 20)
        warn_icon.setStyleSheet("background: transparent; border: none;")
        banner_layout.addWidget(warn_icon)
        warn_text = QLabel(
            "Lưu ý: Quyền hạn (Cấm In/Sửa/Copy) chỉ có tác dụng trên các phần mềm "
            "tuân thủ chuẩn PDF. Mật khẩu mở file mới là lớp bảo vệ thực sự."
        )
        warn_text.setWordWrap(True)
        warn_text.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;"
        )
        banner_layout.addWidget(warn_text, 1)
        layout.addWidget(banner)

    def selected_permissions(self) -> List[str]:
        return [c.text().strip() for c in self.checks if c.isChecked()]

    def permission_flags(self) -> Tuple[bool, bool, bool]:
        """(cam_in, cam_chinh_sua, cam_sao_chep) — đúng thứ tự tham số
        pdf_core.build_protection_permissions()/protect_pdf()."""
        cam_in, cam_chinh_sua, cam_sao_chep = (c.isChecked() for c in self.checks)
        return cam_in, cam_chinh_sua, cam_sao_chep


# ---------------------------------------------------------------------------
# Cột B — Thumbnail nhỏ (dải trái) — có ảnh render thật (thay placeholder cũ)
# ---------------------------------------------------------------------------
class _PreviewThumb(QFrame):
    clicked = Signal(int)

    def __init__(self, page_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.is_current = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(_THUMB_W, _THUMB_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        badge_row = QHBoxLayout()
        self.badge = QLabel(str(page_number))
        self.badge.setFixedSize(_BADGE_SIZE, _BADGE_SIZE)
        self.badge.setAlignment(Qt.AlignCenter)
        badge_row.addWidget(self.badge)
        badge_row.addStretch()
        layout.addLayout(badge_row)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.image_label, 1)

        self._apply_style()

    def set_image(self, image_bytes: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes, "PNG")
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            _THUMB_W - 12, _THUMB_H - 26, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def _apply_style(self) -> None:
        if self.is_current:
            self.setStyleSheet(
                f"QFrame {{ background-color: {COLOR_ACCENT_LIGHT}; border: 2px solid {COLOR_ACCENT}; border-radius: 6px; }}"
            )
            self.badge.setStyleSheet(
                f"background-color: {COLOR_ACCENT}; color: white; font-size: 10px; font-weight: 700; "
                f"border-radius: {_BADGE_SIZE // 2}px; border: none;"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
            )
            self.badge.setStyleSheet(
                f"background-color: {COLOR_TEXT_SECONDARY}; color: white; font-size: 10px; font-weight: 700; "
                f"border-radius: {_BADGE_SIZE // 2}px; border: none;"
            )

    def set_current(self, current: bool) -> None:
        self.is_current = current
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self.page_number)


# ---------------------------------------------------------------------------
# Cột B — ScrollArea hỗ trợ pan bằng chuột trái — copy nguyên từ merge_widget.py
# ---------------------------------------------------------------------------
class _PannablePreviewScrollArea(QScrollArea):
    viewport_resized = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._panning = False
        self._pan_start_pos = None
        self._pan_start_h = 0
        self._pan_start_v = 0
        self.viewport().setCursor(Qt.OpenHandCursor)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.viewport_resized.emit()

    def _event_pos(self, event):
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._panning = True
            self._pan_start_pos = self._event_pos(event)
            self._pan_start_h = self.horizontalScrollBar().value()
            self._pan_start_v = self.verticalScrollBar().value()
            self.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._panning and self._pan_start_pos is not None:
            delta = self._event_pos(event) - self._pan_start_pos
            self.horizontalScrollBar().setValue(self._pan_start_h - delta.x())
            self.verticalScrollBar().setValue(self._pan_start_v - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._panning:
            self._panning = False
            self._pan_start_pos = None
            self.viewport().setCursor(Qt.OpenHandCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# Cột B — 1 trang preview, có ảnh render thật (thay placeholder số to cũ)
# ---------------------------------------------------------------------------
class _ProtectPreviewPage(QFrame):
    def __init__(self, page_number: int, aspect_ratio: float = _DEFAULT_ASPECT_RATIO,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.aspect_ratio = aspect_ratio
        self._raw_pixmap: Optional[QPixmap] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.image_label)

        self.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
        )

    def set_image(self, image_bytes: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(image_bytes, "PNG")
        if pixmap.isNull():
            return
        self._raw_pixmap = pixmap
        self._rescale()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._raw_pixmap is None or self._raw_pixmap.isNull():
            return
        target_w = max(1, self.width() - 8)
        target_h = max(1, self.height() - 8)
        scaled = self._raw_pixmap.scaled(
            target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)


# ---------------------------------------------------------------------------
# Cột B — Trạng thái "khóa" / trống (thay cho nội dung khi chưa mở khóa)
# ---------------------------------------------------------------------------
class _LockedPlaceholder(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.icon_label)

        self.title_label = QLabel()
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; background: transparent; border: none;"
        )
        layout.addWidget(self.subtitle_label)

    def set_message(self, icon_name: str, title: str, subtitle: str) -> None:
        self.icon_label.setPixmap(
            qta.icon(icon_name, color=COLOR_TEXT_SECONDARY).pixmap(QSize(56, 56))
        )
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)


# ---------------------------------------------------------------------------
# Dialog tự vẽ — Trùng tên khi lưu: Ghi đè / Đổi tên khác / Hủy
# (01_dac_ta_giao_dien.md mục 3: nền trắng/chữ tối/nút Accent, đồng bộ style
# đã dùng ở Gộp file/Edit/Chèn file)
# ---------------------------------------------------------------------------
class _OverwriteConfirmDialog(QDialog):
    OVERWRITE = "overwrite"
    RENAME = "rename"
    CANCEL = "cancel"

    def __init__(self, file_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trùng tên file")
        self.setModal(True)
        self.setStyleSheet("QDialog { background-color: white; }")
        self._result = self.CANCEL

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.alert-circle-outline", color=COLOR_ACCENT).pixmap(QSize(36, 36)))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon_label)

        message = QLabel(f'File "{file_name}" đã tồn tại. Bạn muốn làm gì?')
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignCenter)
        message.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        layout.addWidget(message)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(CONTROL_HEIGHT)
        cancel_btn.setStyleSheet(_secondary_button_style())
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn)

        rename_btn = QPushButton("Đổi tên khác")
        rename_btn.setCursor(Qt.PointingHandCursor)
        rename_btn.setFixedHeight(CONTROL_HEIGHT)
        rename_btn.setStyleSheet(_secondary_button_style())
        rename_btn.clicked.connect(self._on_rename)
        btn_row.addWidget(rename_btn)

        overwrite_btn = QPushButton("Ghi đè")
        overwrite_btn.setCursor(Qt.PointingHandCursor)
        overwrite_btn.setFixedHeight(CONTROL_HEIGHT)
        overwrite_btn.setStyleSheet(_primary_button_style())
        overwrite_btn.clicked.connect(self._on_overwrite)
        btn_row.addWidget(overwrite_btn)

        layout.addLayout(btn_row)

    def _on_overwrite(self) -> None:
        self._result = self.OVERWRITE
        self.accept()

    def _on_rename(self) -> None:
        self._result = self.RENAME
        self.accept()

    def _on_cancel(self) -> None:
        self._result = self.CANCEL
        self.reject()

    @classmethod
    def ask(cls, parent: QWidget, file_name: str) -> str:
        dialog = cls(file_name, parent)
        dialog.exec()
        return dialog._result


# ---------------------------------------------------------------------------
# Dialog tự vẽ — Xác nhận Đồng ý/Hủy dùng chung (case owner-only ở Gỡ mật khẩu:
# "File này không có mật khẩu mở, chỉ có giới hạn quyền — Bạn có chắc muốn gỡ
# giới hạn?", đúng 02_dac_ta_tinh_nang.md mục 6.5 case 3)
# ---------------------------------------------------------------------------
class _ConfirmDialog(QDialog):
    def __init__(self, message: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Xác nhận")
        self.setModal(True)
        self.setStyleSheet("QDialog { background-color: white; }")
        self._confirmed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.help-circle-outline", color=COLOR_ACCENT).pixmap(QSize(36, 36)))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon_label)

        text_label = QLabel(message)
        text_label.setWordWrap(True)
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        layout.addWidget(text_label)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(CONTROL_HEIGHT)
        cancel_btn.setStyleSheet(_secondary_button_style())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        ok_btn = QPushButton("Đồng ý")
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setFixedHeight(CONTROL_HEIGHT)
        ok_btn.setStyleSheet(_primary_button_style())
        ok_btn.clicked.connect(self._on_ok)
        btn_row.addWidget(ok_btn)

        layout.addLayout(btn_row)

    def _on_ok(self) -> None:
        self._confirmed = True
        self.accept()

    @classmethod
    def ask(cls, parent: QWidget, message: str) -> bool:
        dialog = cls(message, parent)
        dialog.exec()
        return dialog._confirmed


# ---------------------------------------------------------------------------
# Widget chính
# ---------------------------------------------------------------------------
class ProtectFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # State nghiệp vụ
        self._current_path: Optional[str] = None      # đường dẫn đầy đủ, dùng để xử lý
        self._current_file: Optional[str] = None       # tên hiển thị (basename)
        self._protection_status: Optional[pdf_core.ProtectionStatus] = None
        self._unlock_session: Optional[pdf_core.UnlockPreviewSession] = None
        self._mode = _ModeTabs.MODE_SET
        self._current_page = 0
        self._page_count = 0

        # Renderer dùng chung cho tab Đặt mật khẩu (file không mật khẩu, render qua path)
        self._page_renderer = pdf_core.PageRenderer()

        # State preview Cột B (giống merge_widget.py)
        self._preview_thumbs: List[_PreviewThumb] = []
        self._preview_pages: Dict[int, _ProtectPreviewPage] = {}
        self._zoom_level: float = _ZOOM_DEFAULT
        self._current_preview_width: Optional[int] = None
        self._initial_width_applied = False

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # ================= CỘT A (40%) =================
        column_a = QVBoxLayout()
        column_a.setSpacing(14)

        # --- A1: Drop zone ---
        self.drop_zone = _DropZone()
        self.drop_zone.files_selected.connect(self._on_files_selected)
        column_a.addWidget(self.drop_zone)

        # --- A2: Segmented tab ---
        self.mode_tabs = _ModeTabs()
        self.mode_tabs.mode_changed.connect(self._on_mode_changed)
        column_a.addWidget(self.mode_tabs)

        # --- A3: Nội dung thay đổi theo tab ---
        self.mode_stack = QStackedWidget()
        self.mode_stack.addWidget(self._build_set_password_page())   # index 0
        self.mode_stack.addWidget(self._build_unlock_page())          # index 1
        column_a.addWidget(self.mode_stack, 1)

        # Label kết quả / lỗi (giống merge_widget.py)
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        column_a.addWidget(self.result_label)

        # ================= CỘT B (60%) — Xem trước =================
        column_b = QVBoxLayout()

        preview_card = QFrame()
        preview_card.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: 14px; }}"
        )
        preview_card_layout = QVBoxLayout(preview_card)
        preview_card_layout.setContentsMargins(18, 14, 18, 16)
        preview_card_layout.setSpacing(12)

        header_row = QHBoxLayout()
        file_icon = QLabel()
        file_icon.setPixmap(qta.icon("mdi6.file-outline", color=COLOR_TEXT_SECONDARY).pixmap(QSize(18, 18)))
        file_icon.setStyleSheet("background: transparent; border: none;")
        header_row.addWidget(file_icon)

        self.preview_title = QLabel("Xem trước: —")
        self.preview_title.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.preview_title)
        header_row.addStretch()

        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_out_btn.setIcon(qta.icon("mdi6.magnify-minus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_out_btn.setIconSize(QSize(16, 16))
        self.zoom_out_btn.setFixedSize(26, 26)
        self.zoom_out_btn.setStyleSheet(_zoom_button_style())
        self.zoom_out_btn.setToolTip("Thu nhỏ (-15%)")
        self.zoom_out_btn.clicked.connect(self._on_zoom_out_clicked)
        header_row.addWidget(self.zoom_out_btn)

        self.zoom_percent_label = QLabel(f"{round(_ZOOM_DEFAULT * 100)}%")
        self.zoom_percent_label.setAlignment(Qt.AlignCenter)
        self.zoom_percent_label.setFixedWidth(42)
        self.zoom_percent_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.zoom_percent_label)

        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_in_btn.setIcon(qta.icon("mdi6.magnify-plus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_in_btn.setIconSize(QSize(16, 16))
        self.zoom_in_btn.setFixedSize(26, 26)
        self.zoom_in_btn.setStyleSheet(_zoom_button_style())
        self.zoom_in_btn.setToolTip("Phóng to (+15%)")
        self.zoom_in_btn.clicked.connect(self._on_zoom_in_clicked)
        header_row.addWidget(self.zoom_in_btn)

        preview_card_layout.addLayout(header_row)

        body_row = QHBoxLayout()
        body_row.setSpacing(10)

        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setFixedWidth(_THUMB_STRIP_WIDTH)
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }} {_SCROLLBAR_QSS}"
        )
        self.thumb_container = QWidget()
        self.thumb_container.setStyleSheet("background: transparent;")
        self.thumb_layout = QVBoxLayout(self.thumb_container)
        self.thumb_layout.setContentsMargins(2, 2, 6, 2)
        self.thumb_layout.setSpacing(10)
        self.thumb_layout.setAlignment(Qt.AlignTop)
        self.thumb_scroll.setWidget(self.thumb_container)
        body_row.addWidget(self.thumb_scroll)

        self.preview_scroll_b = _PannablePreviewScrollArea()
        self.preview_scroll_b.setWidgetResizable(True)
        self.preview_scroll_b.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {COLOR_CONTENT_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 10px;
            }}
            {_SCROLLBAR_QSS}
            """
        )
        self.preview_scroll_b.viewport_resized.connect(self._on_preview_viewport_resized)

        preview_pages_container = QWidget()
        preview_pages_container.setStyleSheet("background: transparent;")
        self.preview_layout = QVBoxLayout(preview_pages_container)
        self.preview_layout.setContentsMargins(
            _PREVIEW_SIDE_MARGIN, 12, _PREVIEW_SIDE_MARGIN, 12
        )
        self.preview_layout.setSpacing(16)
        self.preview_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.preview_scroll_b.setWidget(preview_pages_container)

        # Stack chuyển đổi giữa trạng thái "khóa/trống" và nội dung xem trước.
        self.content_stack = QStackedWidget()
        self.locked_placeholder = _LockedPlaceholder()
        self.content_stack.addWidget(self.locked_placeholder)  # index 0
        self.content_stack.addWidget(self.preview_scroll_b)     # index 1
        body_row.addWidget(self.content_stack, 1)

        preview_card_layout.addLayout(body_row, 1)
        column_b.addWidget(preview_card, 1)

        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, 40)
        root_layout.addWidget(column_b_widget, 60)

        # Trạng thái ban đầu
        self._show_empty_preview()
        self._update_zoom_buttons_state()
        self._update_zoom_percent_label()

    # ------------------------------------------------------------------
    # Dựng 2 trang nội dung theo tab
    # ------------------------------------------------------------------
    def _build_set_password_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.set_password_input = _PasswordInput("Nhập mật khẩu")
        layout.addWidget(self.set_password_input)

        self.confirm_password_input = _PasswordInput("Xác nhận mật khẩu")
        layout.addWidget(self.confirm_password_input)

        self.strength_meter = _StrengthMeter()
        layout.addWidget(self.strength_meter)
        self.set_password_input.edit.textChanged.connect(self._on_password_text_changed)

        self.advanced_options = _AdvancedOptions()
        layout.addWidget(self.advanced_options)

        layout.addStretch()

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        clear_btn = QPushButton(" Clear")
        clear_btn.setIcon(qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY))
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setFixedHeight(CONTROL_HEIGHT)
        clear_btn.setMinimumWidth(90)
        clear_btn.setStyleSheet(_secondary_button_style())
        clear_btn.clicked.connect(self._on_clear_clicked)
        bottom_row.addWidget(clear_btn)

        self.set_password_btn = QPushButton(" Đặt mật khẩu")
        self.set_password_btn.setIcon(qta.icon("mdi6.lock-outline", color="white"))
        self.set_password_btn.setCursor(Qt.PointingHandCursor)
        self.set_password_btn.setFixedHeight(CONTROL_HEIGHT)
        self.set_password_btn.setMinimumWidth(140)
        self.set_password_btn.setStyleSheet(_primary_button_style())
        self.set_password_btn.clicked.connect(self._on_set_password_clicked)
        bottom_row.addWidget(self.set_password_btn)

        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        return page

    def _build_unlock_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        self.unlock_password_input = _PasswordInput("Nhập mật khẩu để mở khóa")
        layout.addWidget(self.unlock_password_input)

        self.unlock_cta_btn = QPushButton("  Bắt đầu Mở khóa")
        self.unlock_cta_btn.setIcon(qta.icon("mdi6.shield-check-outline", color="white"))
        self.unlock_cta_btn.setIconSize(QSize(22, 22))
        self.unlock_cta_btn.setCursor(Qt.PointingHandCursor)
        self.unlock_cta_btn.setFixedHeight(_UNLOCK_CTA_HEIGHT)
        self.unlock_cta_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: white;
                border: none;
                border-radius: 10px;
                font-size: 15px;
                font-weight: 700;
            }}
            QPushButton:hover:enabled {{ background-color: #E28104; }}
            QPushButton:pressed:enabled {{ background-color: #C87203; }}
            QPushButton:disabled {{ background-color: #FDBA74; }}
            """
        )
        self.unlock_cta_btn.clicked.connect(self._on_unlock_clicked)
        layout.addWidget(self.unlock_cta_btn)

        layout.addStretch()

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        clear_btn = QPushButton(" Clear")
        clear_btn.setIcon(qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY))
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setFixedHeight(CONTROL_HEIGHT)
        clear_btn.setMinimumWidth(90)
        clear_btn.setStyleSheet(_secondary_button_style())
        clear_btn.clicked.connect(self._on_clear_clicked)
        bottom_row.addWidget(clear_btn)

        # "Lưu File" — chỉ bật sau khi mở khóa thành công (hoặc case owner-only sẵn sàng ngay).
        self.save_file_btn = QPushButton(" Lưu File")
        self.save_file_btn.setIcon(qta.icon("mdi6.content-save-outline", color="white"))
        self.save_file_btn.setCursor(Qt.PointingHandCursor)
        self.save_file_btn.setFixedHeight(CONTROL_HEIGHT)
        self.save_file_btn.setMinimumWidth(130)
        self.save_file_btn.setStyleSheet(_primary_button_style())
        self.save_file_btn.clicked.connect(self._on_save_file_clicked)
        self.save_file_btn.setEnabled(False)
        bottom_row.addWidget(self.save_file_btn)

        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        return page

    # ------------------------------------------------------------------
    # Sự kiện chung
    # ------------------------------------------------------------------
    def _on_files_selected(self, paths: List[str]) -> None:
        if not paths:
            return
        path = paths[0]
        self._close_unlock_session()

        try:
            status = pdf_core.get_protection_status(path)
        except pdf_core.CorruptedFileError as exc:
            self._show_error(f"Không thể đọc file: {exc}")
            logger.log_error(f"Chọn file lỗi ở tính năng Bảo vệ: {path}", exc)
            return

        if self._mode == _ModeTabs.MODE_SET and status.is_protected:
            self._show_error(
                'File này đã được bảo vệ — vui lòng dùng tab "Mở khóa" trước khi đặt mật khẩu mới.'
            )
            return
        if self._mode == _ModeTabs.MODE_UNLOCK and not status.is_protected:
            self._show_error(
                'File này không được bảo vệ — không cần mở khóa. Vui lòng dùng tab "Đặt mật khẩu".'
            )
            return

        self._current_path = path
        self._current_file = path.replace("\\", "/").split("/")[-1]
        self._protection_status = status
        self._current_page = 0
        self.preview_title.setText(f"Xem trước: {self._current_file}")
        self._hide_result()

        if self._mode == _ModeTabs.MODE_UNLOCK:
            try:
                self._unlock_session = pdf_core.UnlockPreviewSession(path)
            except pdf_core.CorruptedFileError as exc:
                self._show_error(f"Không thể mở file: {exc}")
                logger.log_error(f"Lỗi mở file để mở khóa: {path}", exc)
                self._reset_file_selection()
                return

            if self._unlock_session.is_ready:
                # Trường hợp owner-only: không cần mật khẩu, render ngay + báo rõ cho người dùng.
                self.unlock_password_input.edit.setEnabled(False)
                self.unlock_password_input.eye_btn.setEnabled(False)
                self.unlock_cta_btn.setEnabled(False)
                self._show_success(
                    "File này không có mật khẩu mở, chỉ có giới hạn quyền — nội dung đã "
                    'hiển thị. Bấm "Lưu File" để gỡ giới hạn quyền.'
                )
            else:
                self.unlock_password_input.edit.setEnabled(True)
                self.unlock_password_input.eye_btn.setEnabled(True)
                self.unlock_cta_btn.setEnabled(True)

        self._refresh_preview_state()

    def _on_mode_changed(self, mode: str) -> None:
        self._mode = mode
        self.mode_stack.setCurrentIndex(0 if mode == _ModeTabs.MODE_SET else 1)
        self._hide_result()
        if self._current_path and self._protection_status is not None:
            self._revalidate_current_file_for_mode()
        self._refresh_preview_state()

    def _revalidate_current_file_for_mode(self) -> None:
        """Gọi khi đổi tab trong lúc đang có file được chọn — 1 file chỉ hợp lệ cho
        đúng 1 trong 2 tab (đã bảo vệ → Mở khóa; chưa bảo vệ → Đặt mật khẩu)."""
        status = self._protection_status
        if self._mode == _ModeTabs.MODE_SET and status.is_protected:
            self._show_error(
                'File này đã được bảo vệ — vui lòng dùng tab "Mở khóa" trước khi đặt mật khẩu mới.'
            )
            self._reset_file_selection()
        elif self._mode == _ModeTabs.MODE_UNLOCK and not status.is_protected:
            self._show_error(
                'File này không được bảo vệ — không cần mở khóa. Vui lòng dùng tab "Đặt mật khẩu".'
            )
            self._reset_file_selection()

    def _on_clear_clicked(self) -> None:
        self.set_password_input.clear()
        self.confirm_password_input.clear()
        self.strength_meter.set_score(0)
        self._zoom_level = _ZOOM_DEFAULT
        self._reset_file_selection()
        self._update_zoom_percent_label()
        self._hide_result()

    def _on_password_text_changed(self, text: str) -> None:
        score_100 = pdf_core.calculate_password_strength(text)
        if score_100 == 0:
            level = 0
        elif score_100 <= _STRENGTH_WEAK_MAX:
            level = 1
        elif score_100 <= _STRENGTH_MEDIUM_MAX:
            level = 2
        else:
            level = 3
        self.strength_meter.set_score(level)

    def _reset_file_selection(self) -> None:
        self._close_unlock_session()
        self._current_path = None
        self._current_file = None
        self._protection_status = None
        self._current_page = 0
        self._page_count = 0
        self.preview_title.setText("Xem trước: —")
        self.unlock_password_input.clear()
        self.unlock_password_input.edit.setEnabled(True)
        self.unlock_password_input.eye_btn.setEnabled(True)
        self.unlock_cta_btn.setEnabled(True)
        self.save_file_btn.setEnabled(False)
        self._show_empty_preview()

    def _close_unlock_session(self) -> None:
        if self._unlock_session is not None:
            self._unlock_session.close()
            self._unlock_session = None

    # ------------------------------------------------------------------
    # Tab Đặt mật khẩu
    # ------------------------------------------------------------------
    def _on_set_password_clicked(self) -> None:
        if not self._current_path:
            self._show_error("Vui lòng chọn 1 file PDF trước.")
            return
        password = self.set_password_input.text()
        confirm = self.confirm_password_input.text()
        if not password:
            self._show_error("Vui lòng nhập mật khẩu.")
            return
        if password != confirm:
            self._show_error("Mật khẩu xác nhận không khớp — vui lòng kiểm tra lại.")
            return

        cam_in, cam_chinh_sua, cam_sao_chep = self.advanced_options.permission_flags()

        default_name = self._default_output_name(self._current_file, _DEFAULT_SUFFIX_PROTECT)
        save_path = self._ask_save_path(default_name)
        if not save_path:
            return

        try:
            pdf_core.protect_pdf(
                self._current_path, save_path, password,
                cam_in=cam_in, cam_chinh_sua=cam_chinh_sua, cam_sao_chep=cam_sao_chep,
            )
        except pdf_core.CorruptedFileError as exc:
            self._show_error(f"Không thể đọc file: {exc}")
            logger.log_error("Lỗi đặt mật khẩu (đọc file)", exc)
            return
        except pdf_core.FileLockedError as exc:
            self._show_error("File đang được sử dụng bởi chương trình khác, vui lòng đóng và thử lại.")
            logger.log_error("Lỗi đặt mật khẩu (ghi file)", exc)
            return
        except Exception as exc:  # không để crash app — hiện thông báo dễ hiểu, log chi tiết
            self._show_error(f"Lỗi không xác định khi đặt mật khẩu: {exc}")
            logger.log_error("Lỗi đặt mật khẩu (không xác định)", exc)
            return

        perm_text = ", ".join(self.advanced_options.selected_permissions()) or "không giới hạn quyền hạn"
        logger.log_info(f"Đặt mật khẩu thành công: {save_path}")
        self._show_success(
            f"Đã đặt mật khẩu thành công (Quyền hạn: {perm_text}) — file kết quả: {save_path}"
        )
        self._open_result_folder(save_path)

    # ------------------------------------------------------------------
    # Tab Mở khóa
    # ------------------------------------------------------------------
    def _on_unlock_clicked(self) -> None:
        if not self._current_path or self._unlock_session is None:
            self._show_error("Vui lòng chọn 1 file PDF cần mở khóa.")
            return
        password = self.unlock_password_input.text()
        if not password:
            # Chưa nhập mật khẩu → giữ trạng thái khóa, KHÔNG render nội dung Cột B.
            self._show_error("Vui lòng nhập mật khẩu trước khi mở khóa.")
            self._show_locked_placeholder()
            return

        ok = self._unlock_session.authenticate(password)
        if not ok:
            self._show_error("Mật khẩu không đúng — vui lòng kiểm tra lại.")
            self._show_locked_placeholder()
            self.save_file_btn.setEnabled(False)
            return

        self._current_page = 1
        self._render_unlock_preview()
        self.save_file_btn.setEnabled(True)
        self._show_success(
            f"Đã mở khóa thành công '{self._current_file}' — nội dung đã được hiển thị bên phải."
        )

    def _on_save_file_clicked(self) -> None:
        if not self._current_path or self._unlock_session is None or not self._unlock_session.is_ready:
            self._show_error("Bạn cần mở khóa file thành công trước khi lưu.")
            return

        # Trường hợp owner-only (không cần mật khẩu mở) — hỏi xác nhận riêng trước khi gỡ
        # giới hạn (02_dac_ta_tinh_nang.md mục 6.5 case 3).
        if not self._unlock_session.needs_password:
            confirmed = _ConfirmDialog.ask(
                self,
                "File này không có mật khẩu mở, chỉ có giới hạn quyền — "
                "Bạn có chắc muốn gỡ giới hạn?",
            )
            if not confirmed:
                return

        default_name = self._default_output_name(self._current_file, _DEFAULT_SUFFIX_UNLOCK)
        save_path = self._ask_save_path(default_name)
        if not save_path:
            return

        try:
            self._unlock_session.save_unlocked(save_path)
        except pdf_core.FileLockedError as exc:
            self._show_error("File đang được sử dụng bởi chương trình khác, vui lòng đóng và thử lại.")
            logger.log_error("Lỗi lưu file đã mở khóa (ghi file)", exc)
            return
        except Exception as exc:
            self._show_error(f"Lỗi không xác định khi lưu file: {exc}")
            logger.log_error("Lỗi lưu file đã mở khóa (không xác định)", exc)
            return

        logger.log_info(f"Gỡ mật khẩu/giới hạn thành công: {save_path}")
        self._show_success(
            f"Đã lưu file mới không còn mật khẩu/giới hạn — file kết quả: {save_path}"
        )
        self._open_result_folder(save_path)

    # ------------------------------------------------------------------
    # Lưu file — dialog chọn nơi lưu + tự kiểm tra trùng tên + tự mở thư mục kết quả
    # ------------------------------------------------------------------
    def _default_output_name(self, basename: Optional[str], suffix: str) -> str:
        name = basename or "output.pdf"
        stem = name[:-4] if name.lower().endswith(".pdf") else name
        return f"{stem}{suffix}.pdf"

    def _ask_save_path(self, default_name: str) -> Optional[str]:
        """Mở dialog chọn nơi lưu (kiểu Save As). Đã tắt cảnh báo ghi đè mặc định của hệ
        điều hành (DontConfirmOverwrite) để tự kiểm tra trùng tên bằng dialog tự vẽ riêng
        (Ghi đè / Đổi tên khác / Hủy) — không hỏi 2 lần cho cùng 1 việc."""
        dialog = QFileDialog(self, "Chọn nơi lưu file kết quả")
        dialog.setAcceptMode(QFileDialog.AcceptSave)
        dialog.setFileMode(QFileDialog.AnyFile)
        dialog.setNameFilter("PDF Files (*.pdf)")
        dialog.setDefaultSuffix("pdf")
        dialog.setOption(QFileDialog.Option.DontConfirmOverwrite, True)
        dialog.selectFile(default_name)

        while True:
            if dialog.exec() != QFileDialog.Accepted:
                return None
            selected = dialog.selectedFiles()
            if not selected:
                return None
            save_path = selected[0]
            if not save_path.lower().endswith(".pdf"):
                save_path += ".pdf"

            if not os.path.exists(save_path):
                return save_path

            choice = _OverwriteConfirmDialog.ask(self, os.path.basename(save_path))
            if choice == _OverwriteConfirmDialog.OVERWRITE:
                return save_path
            if choice == _OverwriteConfirmDialog.RENAME:
                dialog.selectFile(os.path.basename(save_path))
                continue
            return None  # Hủy

    def _open_result_folder(self, save_path: str) -> None:
        folder = os.path.dirname(save_path) or "."
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    # ------------------------------------------------------------------
    # Quản lý trạng thái Cột B
    # ------------------------------------------------------------------
    def _refresh_preview_state(self) -> None:
        """Theo mode + trạng thái file, quyết định Cột B render nội dung hay khóa."""
        if not self._current_path:
            self._show_empty_preview()
            return
        if self._mode == _ModeTabs.MODE_SET:
            self._current_page = 1
            ok = self._load_set_password_preview()
            if ok:
                self._refresh_page_view()
                self.content_stack.setCurrentIndex(1)
            return

        # Tab Mở khóa: chỉ render khi session đã sẵn sàng (đã authenticate, hoặc owner-only).
        session = self._unlock_session
        if session is not None and session.is_ready:
            self._current_page = 1
            self._render_unlock_preview()
            self.save_file_btn.setEnabled(True)
        else:
            self._show_locked_placeholder()
            self.save_file_btn.setEnabled(False)

    def _load_set_password_preview(self) -> bool:
        """Render preview thật cho tab Đặt mật khẩu — file lúc này KHÔNG có mật khẩu,
        dùng list_page_infos()/PageRenderer (chỉ tái sử dụng, không sửa pdf_core)."""
        try:
            page_infos = pdf_core.list_page_infos(self._current_path)
        except Exception as exc:
            self._show_error(f"Không thể đọc file: {exc}")
            logger.log_error(f"Lỗi đọc file ở tab Đặt mật khẩu: {self._current_path}", exc)
            self._reset_file_selection()
            return False

        sizes = [(info.width, info.height) for info in page_infos]
        self._page_count = len(page_infos)
        self._build_preview_thumbs(self._page_count)
        self._build_preview_pages(self._page_count, sizes)

        path = self._current_path
        for i in range(self._page_count):
            page_number = i + 1
            try:
                thumb_bytes = self._page_renderer.render_thumbnail(path, i, max_width=160)
                self._preview_thumbs[i].set_image(thumb_bytes)
            except Exception as exc:
                logger.log_error(f"Lỗi render thumbnail trang {page_number} (Đặt mật khẩu)", exc)
            frame = self._preview_pages.get(page_number)
            if frame is not None:
                try:
                    width = frame.width() or self._compute_preview_width()
                    detail_bytes = self._page_renderer.render_page_detail(
                        path, i, target_width=max(width, 200)
                    )
                    frame.set_image(detail_bytes)
                except Exception as exc:
                    logger.log_error(f"Lỗi render preview trang {page_number} (Đặt mật khẩu)", exc)
        return True

    def _render_unlock_preview(self) -> None:
        """Render preview thật cho tab Mở khóa, TRỰC TIẾP từ fitz.Document đang mở trong
        bộ nhớ của UnlockPreviewSession (mục 6b pdf_core.py) — dùng render_document_page()
        (mục 8) đã có sẵn, không qua path/PDFDocument (file trên đĩa vẫn còn mật khẩu)."""
        session = self._unlock_session
        doc = session.document
        total_pages = pdf_core.get_document_page_count(doc)
        self._page_count = total_pages
        sizes = [pdf_core.get_document_page_size(doc, i) for i in range(total_pages)]

        self._build_preview_thumbs(total_pages)
        self._build_preview_pages(total_pages, sizes)

        for i in range(total_pages):
            page_number = i + 1
            try:
                thumb_bytes = pdf_core.render_document_page(doc, i, target_width=160)
                self._preview_thumbs[i].set_image(thumb_bytes)
            except Exception as exc:
                logger.log_error(f"Lỗi render thumbnail trang {page_number} (Mở khóa)", exc)
            frame = self._preview_pages.get(page_number)
            if frame is not None:
                try:
                    width = frame.width() or self._compute_preview_width()
                    detail_bytes = pdf_core.render_document_page(doc, i, target_width=max(width, 200))
                    frame.set_image(detail_bytes)
                except Exception as exc:
                    logger.log_error(f"Lỗi render preview trang {page_number} (Mở khóa)", exc)

        self._refresh_page_view()
        self.content_stack.setCurrentIndex(1)

    def _show_empty_preview(self) -> None:
        self.preview_title.setText("Xem trước: —")
        self._build_preview_thumbs(0)
        self._build_preview_pages(0)
        self.locked_placeholder.set_message(
            "mdi6.file-outline",
            "Chưa có file nào được chọn",
            "Hãy chọn hoặc kéo-thả 1 file PDF phía trên để bắt đầu.",
        )
        self.content_stack.setCurrentIndex(0)
        self._update_zoom_buttons_state()

    def _show_locked_placeholder(self) -> None:
        self._build_preview_thumbs(0)
        self._build_preview_pages(0)
        self.locked_placeholder.set_message(
            "mdi6.lock",
            "Nội dung file đang được bảo vệ",
            "Nhập mật khẩu và bấm \"Bắt đầu Mở khóa\" để xem trước nội dung.",
        )
        self.content_stack.setCurrentIndex(0)
        self._update_zoom_buttons_state()

    # ------------------------------------------------------------------
    # Xem trước (Cột B) — copy logic từ merge_widget.py
    # ------------------------------------------------------------------
    def _build_preview_thumbs(self, total_pages: int) -> None:
        while self.thumb_layout.count():
            child = self.thumb_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        self._preview_thumbs = []

        for i in range(total_pages):
            page_number = i + 1
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setSpacing(2)

            thumb = _PreviewThumb(page_number)
            thumb.clicked.connect(self._on_thumb_clicked)
            wrapper_layout.addWidget(thumb, alignment=Qt.AlignHCenter)

            self.thumb_layout.addWidget(wrapper)
            self._preview_thumbs.append(thumb)

    def _build_preview_pages(self, total_pages: int,
                              page_sizes: Optional[List[Tuple[float, float]]] = None) -> None:
        for frame in self._preview_pages.values():
            self.preview_layout.removeWidget(frame)
            frame.deleteLater()
        self._preview_pages.clear()
        self._current_preview_width = None

        if total_pages == 0:
            self._update_zoom_buttons_state()
            return

        width = self._compute_preview_width()
        self._current_preview_width = width
        for i in range(total_pages):
            page_number = i + 1
            aspect_ratio = _DEFAULT_ASPECT_RATIO
            if page_sizes and i < len(page_sizes):
                w, h = page_sizes[i]
                if w:
                    aspect_ratio = h / w
            frame = _ProtectPreviewPage(page_number, aspect_ratio)
            height = round(width * frame.aspect_ratio)
            frame.setFixedSize(width, height)
            self.preview_layout.addWidget(frame, alignment=Qt.AlignHCenter)
            self._preview_pages[page_number] = frame

        self._update_zoom_buttons_state()

    def _on_thumb_clicked(self, page_number: int) -> None:
        self._current_page = page_number
        self._refresh_page_view()

    def _refresh_page_view(self) -> None:
        for thumb in self._preview_thumbs:
            thumb.set_current(thumb.page_number == self._current_page)
        if 0 <= self._current_page - 1 < len(self._preview_thumbs):
            current_thumb = self._preview_thumbs[self._current_page - 1]
            self.thumb_scroll.ensureWidgetVisible(current_thumb, 0, 20)

        current_frame = self._preview_pages.get(self._current_page)
        if current_frame is not None:
            self.preview_scroll_b.ensureWidgetVisible(current_frame, 0, 0)

    # ------------------------------------------------------------------
    # Zoom Cột B — đồng bộ với merge_widget.py
    # ------------------------------------------------------------------
    def _fit_base_width(self) -> int:
        viewport_width = self.preview_scroll_b.viewport().width()
        usable = viewport_width - (_PREVIEW_SIDE_MARGIN * 2)
        return max(_PREVIEW_MIN_PAGE_WIDTH, usable)

    def _compute_preview_width(self) -> int:
        base_width = self._fit_base_width()
        return max(_PREVIEW_MIN_PAGE_WIDTH, round(base_width * self._zoom_level))

    def _apply_preview_zoom(self) -> None:
        if not self._preview_pages:
            self._update_zoom_buttons_state()
            self._update_zoom_percent_label()
            return

        new_width = self._compute_preview_width()
        if new_width == self._current_preview_width:
            self._update_zoom_buttons_state()
            self._update_zoom_percent_label()
            return
        self._current_preview_width = new_width

        for frame in self._preview_pages.values():
            new_height = round(new_width * frame.aspect_ratio)
            frame.setFixedSize(new_width, new_height)

        self._update_zoom_buttons_state()
        self._update_zoom_percent_label()

    def _on_zoom_in_clicked(self) -> None:
        self._set_zoom_level(self._zoom_level + _ZOOM_STEP)

    def _on_zoom_out_clicked(self) -> None:
        self._set_zoom_level(self._zoom_level - _ZOOM_STEP)

    def _set_zoom_level(self, new_level: float) -> None:
        clamped = max(_ZOOM_MIN, min(_ZOOM_MAX, round(new_level, 2)))
        if abs(clamped - self._zoom_level) < 1e-6:
            return
        self._zoom_level = clamped
        self._apply_preview_zoom()

    def _update_zoom_buttons_state(self) -> None:
        has_pages = bool(self._preview_pages)
        self.zoom_in_btn.setEnabled(has_pages and self._zoom_level < _ZOOM_MAX - 1e-6)
        self.zoom_out_btn.setEnabled(has_pages and self._zoom_level > _ZOOM_MIN + 1e-6)

    def _update_zoom_percent_label(self) -> None:
        self.zoom_percent_label.setText(f"{round(self._zoom_level * 100)}%")

    def _on_preview_viewport_resized(self) -> None:
        if self._preview_pages:
            self._apply_preview_zoom()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Lần hiển thị đầu tiên: cửa sổ đã có kích thước thật, tính lại chiều rộng
        # trang cho khớp khung Cột B thật sự (giữ nguyên fix từ merge_widget.py).
        if not self._initial_width_applied and self._preview_pages:
            self._initial_width_applied = True
            self._current_preview_width = None
            self._apply_preview_zoom()

    # ------------------------------------------------------------------
    def _show_success(self, message: str) -> None:
        self.result_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"✓ {message}")
        self.result_label.show()

    def _show_error(self, message: str) -> None:
        self.result_label.setStyleSheet(f"color: {COLOR_ERROR}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"✕ {message}")
        self.result_label.show()

    def _hide_result(self) -> None:
        self.result_label.hide()