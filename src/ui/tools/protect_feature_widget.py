"""
Giao diện tính năng Bảo vệ (Protect) — Đặt mật khẩu / Mở khóa file PDF.

Đồng bộ hoàn toàn với thiết kế của merge_widget.py:
- Cột A (40%): Drop zone (CHỈ CHỌN 1 FILE) → segmented tab Đặt mật khẩu / Mở khóa
  → nội dung thay đổi theo tab → hàng nút hành động cuối cùng.
- Cột B (60%): Card xem trước giống Merge — header có cụm Zoom In/Out ±15%
  (50%-200%), dải thumbnail trái (đồng bộ 1 chiều: click → cuộn khung lớn),
  khung lớn dùng _PannablePreviewScrollArea (cuộn chuột + pan chuột trái).

Luồng nghiệp vụ (mock — chưa nối pdf_core):
- Tab Đặt mật khẩu: chọn 1 file → xem trước render ngay (file chưa khóa).
  Validate: đã chọn file, mật khẩu không trống, 2 ô khớp nhau.
- Tab Mở khóa: chọn file → Cột B ở trạng thái "khóa" (không render nội dung).
  Bấm "Bắt đầu Mở khóa" khi chưa nhập mật khẩu → báo lỗi, vẫn không render.
  Nhập mật khẩu + bấm → mở khóa thành công → Cột B mới render nội dung.
  Nút "Lưu File" chỉ bật sau khi mở khóa thành công (demo: lưu file mới
  hoàn toàn không mật khẩu).

Advanced Options luôn mở, cố định — không có trạng thái thu gọn.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtGui import QDragEnterEvent, QDropEvent
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
)

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
# Dữ liệu giả để dựng giao diện
# ---------------------------------------------------------------------------
_MOCK_FILE_NAME = "Tai lieu bao mat.pdf"
_MOCK_PAGE_COUNT = 6

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

# Chiều cao ô nhập mật khẩu + nút con mắt (nút mắt nền cam, theo ảnh thiết kế).
_PASSWORD_INPUT_HEIGHT = 52
_EYE_BUTTON_WIDTH = 52
_EYE_BUTTON_HEIGHT = 40
# Nút "Bắt đầu Mở khóa" full-width, cao hơn nút thường (theo ảnh Mở khóa).
_UNLOCK_CTA_HEIGHT = 52

# Advanced Options — màu chip + banner cảnh báo.
_CHIP_BG = "#F3F4F6"

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


def _password_strength_score(password: str) -> int:
    """Chấm điểm độ mạnh mật khẩu (0-3):
    - +1: độ dài >= 8 ký tự
    - +1: có cả chữ hoa và chữ thường
    - +1: có chữ số hoặc ký tự đặc biệt
    """
    if not password:
        return 0
    score = 0
    if len(password) >= 8:
        score += 1
    if any(c.islower() for c in password) and any(c.isupper() for c in password):
        score += 1
    if any(c.isdigit() for c in password) or any(not c.isalnum() for c in password):
        score += 1
    return score


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
        self.edit.setEchoMode(QLineEdit.Password)
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
        self.eye_btn.setIcon(qta.icon("mdi6.eye-outline", color="white"))
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
        if self.edit.echoMode() == QLineEdit.Password:
            self.edit.setEchoMode(QLineEdit.Normal)
            self.eye_btn.setIcon(qta.icon("mdi6.eye-off-outline", color="white"))
        else:
            self.edit.setEchoMode(QLineEdit.Password)
            self.eye_btn.setIcon(qta.icon("mdi6.eye-outline", color="white"))

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
        self.setIconSize(QSize(20, 20))
        self.setText(f"  {label}")
        self.setStyleSheet("QToolButton { border: none; background: transparent; }")
        self._label_color = COLOR_TEXT_PRIMARY
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        if self.isChecked():
            self.setIcon(qta.icon("mdi6.check", color="white"))
        else:
            self.setIcon(qta.icon("mdi6.check", color="transparent"))
        # Màu chữ label đi kèm.
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

    def nextCheckState(self) -> None:  # noqa: N802 - Qt API
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
        chip = QLabel("  Mã hóa AES 256-bit")
        chip.setPixmap(qta.icon("mdi6.shield-check-outline", color=COLOR_TEXT_PRIMARY).pixmap(QSize(16, 16)))
        chip.setStyleSheet(
            f"background-color: {_CHIP_BG}; color: {COLOR_TEXT_PRIMARY}; font-size: 13px; "
            "font-weight: 600; border-radius: 12px; padding: 6px 12px; border: none;"
        )
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


# ---------------------------------------------------------------------------
# Cột B — Thumbnail nhỏ (dải trái) — copy nguyên từ merge_widget.py
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
        layout.setSpacing(0)

        badge_row = QHBoxLayout()
        self.badge = QLabel(str(page_number))
        self.badge.setFixedSize(_BADGE_SIZE, _BADGE_SIZE)
        self.badge.setAlignment(Qt.AlignCenter)
        badge_row.addWidget(self.badge)
        badge_row.addStretch()
        layout.addLayout(badge_row)
        layout.addStretch()

        self._apply_style()

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
            self.badge.setStyleSheet("background-color: transparent; color: transparent; border: none;")

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
# Cột B — 1 trang placeholder (mock, chưa nối pdf_core) — giống merge_widget.py
# ---------------------------------------------------------------------------
class _ProtectPreviewPage(QFrame):
    def __init__(self, page_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.aspect_ratio = _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.number_label = QLabel(str(page_number))
        self.number_label.setAlignment(Qt.AlignCenter)
        self.number_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 48px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.number_label)

        self.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
        )


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
# Widget chính
# ---------------------------------------------------------------------------
class ProtectFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # State nghiệp vụ
        self._current_file: Optional[str] = None
        self._unlocked = False
        self._mode = _ModeTabs.MODE_SET
        self._current_page = 0

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
        clear_btn.setStyleSheet(self._secondary_button_style())
        clear_btn.clicked.connect(self._on_clear_clicked)
        bottom_row.addWidget(clear_btn)

        self.set_password_btn = QPushButton(" Đặt mật khẩu")
        self.set_password_btn.setIcon(qta.icon("mdi6.lock-outline", color="white"))
        self.set_password_btn.setCursor(Qt.PointingHandCursor)
        self.set_password_btn.setFixedHeight(CONTROL_HEIGHT)
        self.set_password_btn.setMinimumWidth(140)
        self.set_password_btn.setStyleSheet(self._primary_button_style())
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
            QPushButton:hover {{ background-color: #E28104; }}
            QPushButton:pressed {{ background-color: #C87203; }}
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
        clear_btn.setStyleSheet(self._secondary_button_style())
        clear_btn.clicked.connect(self._on_clear_clicked)
        bottom_row.addWidget(clear_btn)

        # "Lưu File" — chỉ bật sau khi mở khóa thành công.
        self.save_file_btn = QPushButton(" Lưu File")
        self.save_file_btn.setIcon(qta.icon("mdi6.content-save-outline", color="white"))
        self.save_file_btn.setCursor(Qt.PointingHandCursor)
        self.save_file_btn.setFixedHeight(CONTROL_HEIGHT)
        self.save_file_btn.setMinimumWidth(130)
        self.save_file_btn.setStyleSheet(self._primary_button_style())
        self.save_file_btn.clicked.connect(self._on_save_file_clicked)
        self.save_file_btn.setEnabled(False)
        bottom_row.addWidget(self.save_file_btn)

        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        return page

    @staticmethod
    def _primary_button_style() -> str:
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

    @staticmethod
    def _secondary_button_style() -> str:
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

    # ------------------------------------------------------------------
    # Sự kiện chung
    # ------------------------------------------------------------------
    def _on_files_selected(self, paths: List[str]) -> None:
        if not paths:
            return
        self._current_file = paths[0].replace("\\", "/").split("/")[-1]
        self._unlocked = False
        self._current_page = 0
        self.preview_title.setText(f"Xem trước: {self._current_file}")
        self._hide_result()
        self._refresh_preview_state()

    def _on_mode_changed(self, mode: str) -> None:
        self._mode = mode
        self.mode_stack.setCurrentIndex(0 if mode == _ModeTabs.MODE_SET else 1)
        self._hide_result()
        self._refresh_preview_state()

    def _on_clear_clicked(self) -> None:
        self._current_file = None
        self._unlocked = False
        self._current_page = 0
        self.set_password_input.clear()
        self.confirm_password_input.clear()
        self.unlock_password_input.clear()
        self.strength_meter.set_score(0)
        self.save_file_btn.setEnabled(False)
        self._zoom_level = _ZOOM_DEFAULT
        self._show_empty_preview()
        self._update_zoom_percent_label()
        self._hide_result()

    def _on_password_text_changed(self, text: str) -> None:
        self.strength_meter.set_score(_password_strength_score(text))

    # ------------------------------------------------------------------
    # Tab Đặt mật khẩu
    # ------------------------------------------------------------------
    def _on_set_password_clicked(self) -> None:
        if not self._current_file:
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
        permissions = self.advanced_options.selected_permissions()
        perm_text = ", ".join(permissions) if permissions else "không giới hạn quyền hạn"
        self._show_success(
            f"[Demo giao diện] Sẽ đặt mật khẩu cho '{self._current_file}' "
            f"(Độ mạnh: {self.strength_meter.label.text().split('—')[-1].strip()}; "
            f"Quyền hạn: {perm_text}) — chưa xử lý PDF thật."
        )

    # ------------------------------------------------------------------
    # Tab Mở khóa
    # ------------------------------------------------------------------
    def _on_unlock_clicked(self) -> None:
        if not self._current_file:
            self._show_error("Vui lòng chọn 1 file PDF cần mở khóa.")
            return
        password = self.unlock_password_input.text()
        if not password:
            # Chưa nhập mật khẩu → giữ trạng thái khóa, KHÔNG render nội dung Cột B.
            self._show_error("Vui lòng nhập mật khẩu trước khi mở khóa.")
            self._show_locked_placeholder()
            return

        # Demo: coi như mật khẩu đúng → mở khóa thành công, render nội dung.
        self._unlocked = True
        self._current_page = 1
        self._build_preview_thumbs(_MOCK_PAGE_COUNT)
        self._build_preview_pages(_MOCK_PAGE_COUNT)
        self._refresh_page_view()
        self.content_stack.setCurrentIndex(1)
        self.save_file_btn.setEnabled(True)
        self._show_success(f"Đã mở khóa thành công '{self._current_file}' — nội dung đã được hiển thị bên phải.")

    def _on_save_file_clicked(self) -> None:
        if not self._unlocked or not self._current_file:
            self._show_error("Bạn cần mở khóa file thành công trước khi lưu.")
            return
        base = self._current_file.rsplit(".pdf", 1)[0]
        self._show_success(
            f"[Demo giao diện] Sẽ lưu file mới không mật khẩu: '{base}_unlocked.pdf' — chưa xử lý PDF thật."
        )

    # ------------------------------------------------------------------
    # Quản lý trạng thái Cột B
    # ------------------------------------------------------------------
    def _refresh_preview_state(self) -> None:
        """Theo mode + trạng thái file, quyết định Cột B render nội dung hay khóa."""
        if not self._current_file:
            self._show_empty_preview()
            return
        if self._mode == _ModeTabs.MODE_SET:
            # Tab Đặt mật khẩu: file chưa khóa → xem trước ngay.
            self._current_page = 1
            self._build_preview_thumbs(_MOCK_PAGE_COUNT)
            self._build_preview_pages(_MOCK_PAGE_COUNT)
            self._refresh_page_view()
            self.content_stack.setCurrentIndex(1)
            return
        # Tab Mở khóa: chỉ render khi đã mở khóa thành công.
        if self._unlocked:
            self._build_preview_thumbs(_MOCK_PAGE_COUNT)
            self._build_preview_pages(_MOCK_PAGE_COUNT)
            self._refresh_page_view()
            self.content_stack.setCurrentIndex(1)
            self.save_file_btn.setEnabled(True)
        else:
            self._show_locked_placeholder()
            self.save_file_btn.setEnabled(False)

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

            num_label = QLabel(str(page_number))
            num_label.setAlignment(Qt.AlignCenter)
            num_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            wrapper_layout.addWidget(num_label)

            self.thumb_layout.addWidget(wrapper)
            self._preview_thumbs.append(thumb)

    def _build_preview_pages(self, total_pages: int) -> None:
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
            frame = _ProtectPreviewPage(page_number)
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