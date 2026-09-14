"""
Sidebar điều hướng bên trái. Thứ tự từ trên xuống: logo phần mềm, tên phần
mềm, nhãn "Menu:", danh sách 5 tính năng, rồi đến hàng nút Home + Logout ở
cuối. Mục đang chọn có highlight màu accent. Phát tín hiệu feature_selected(key)
khi người dùng bấm chọn 1 tính năng, home_requested khi bấm nút Home (quay về
màn hình chào), và logout_requested khi bấm nút đóng phần mềm.
"""
from __future__ import annotations

import os
from typing import List, Tuple

import qtawesome as qta
from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QToolButton,
)

from src.ui.vishipel_theme import (
    COLOR_SIDEBAR_BG,
    COLOR_SIDEBAR_TEXT,
    COLOR_ACCENT,
    SIDEBAR_WIDTH,
)

# Danh sách tính năng theo đúng thứ tự sidebar đã chốt: (khóa nội bộ, tên hiển thị, icon mdi6)
FEATURES: List[Tuple[str, str, str]] = [
    ("split", "Tách File", "mdi6.call-split"),
    ("merge", "Gộp File", "mdi6.file-multiple-outline"),
    ("edit", "Edit File", "mdi6.file-document-edit-outline"),
    ("insert", "Chèn File", "mdi6.file-plus-outline"),
    ("rename", "Đổi Tên", "mdi6.form-textbox"),
]

_ITEM_HEIGHT = 44
_ICON_SIZE = 18
_LOGOUT_ICON_SIZE = 20
_ROW_LEFT_PADDING = 20  
_LOGO_SIZE = 160


_LOGO_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "icon", "logo.png")
)


class Sidebar(QWidget):
    """Sidebar điều hướng. Phát tín hiệu feature_selected(str) với khóa tính năng đã chọn,
    home_requested() khi bấm nút Home, và logout_requested() khi bấm nút đóng phần mềm."""

    feature_selected = Signal(str)
    home_requested = Signal()
    logout_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {COLOR_SIDEBAR_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 20, 0, 16)
        layout.setSpacing(0)

        # --- 1. Logo phần mềm ---
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet("background: transparent;")
        logo_label.setContentsMargins(0, 0, 0, 8)
        pixmap = QPixmap(_LOGO_PATH)
        if not pixmap.isNull():
            logo_label.setPixmap(
                pixmap.scaled(
                    _LOGO_SIZE,
                    _LOGO_SIZE,
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
        layout.addWidget(logo_label)

        # --- 2. Tên phần mềm ---
        title_label = QLabel("Vishipel PDF Tools")
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            "color: white; font-size: 16px; font-weight: 600; padding: 8px 12px 16px 12px;"
        )
        layout.addWidget(title_label)


        # --- 4. Danh sách 5 tính năng — mỗi dòng dùng widget riêng (icon + tên canh lề trái)
        self.list_widget = QListWidget()
        self.list_widget.setFrameShape(QListWidget.NoFrame)
        self.list_widget.setFocusPolicy(Qt.NoFocus)
        self.list_widget.setSelectionMode(QListWidget.SingleSelection)
        self.list_widget.setStyleSheet(self._list_stylesheet())

        self._icon_labels: List[QLabel] = []
        self._text_labels: List[QLabel] = []

        for _key, label, icon_name in FEATURES:
            item = QListWidgetItem()
            item.setSizeHint(QSize(SIDEBAR_WIDTH, _ITEM_HEIGHT))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.list_widget.addItem(item)

            row_widget, icon_label, text_label = self._build_row_widget(icon_name, label)
            self.list_widget.setItemWidget(item, row_widget)
            self._icon_labels.append(icon_label)
            self._text_labels.append(text_label)

        self.list_widget.currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.list_widget)
        layout.addStretch()

        # --- 5. Hàng nút Home + Logout ở cuối sidebar ---
        self.home_button = QToolButton()
        self.home_button.setIcon(qta.icon("mdi6.home-outline", color=COLOR_SIDEBAR_TEXT))
        self.home_button.setIconSize(QSize(_LOGOUT_ICON_SIZE, _LOGOUT_ICON_SIZE))
        self.home_button.setToolTip("Về màn hình chính")
        self.home_button.setCursor(Qt.PointingHandCursor)
        self.home_button.setAutoRaise(True)
        self.home_button.setStyleSheet(self._round_button_stylesheet())
        self.home_button.clicked.connect(self._on_home_clicked)

        self.logout_button = QToolButton()
        self.logout_button.setIcon(qta.icon("mdi6.logout", color=COLOR_SIDEBAR_TEXT))
        self.logout_button.setIconSize(QSize(_LOGOUT_ICON_SIZE, _LOGOUT_ICON_SIZE))
        self.logout_button.setToolTip("Đóng phần mềm")
        self.logout_button.setCursor(Qt.PointingHandCursor)
        self.logout_button.setAutoRaise(True)
        self.logout_button.setStyleSheet(self._round_button_stylesheet())
        self.logout_button.clicked.connect(self.logout_requested.emit)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 8, 0, 0)
        bottom_row.setSpacing(16)
        bottom_row.addStretch()
        bottom_row.addWidget(self.home_button)
        bottom_row.addWidget(self.logout_button)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        # Không chọn sẵn mục nào khi khởi tạo — khung nội dung mặc định hiển thị
        # màn hình chào (welcome_screen.py), không phải trang của 1 tính năng cụ thể.
        # Người dùng bấm vào sidebar mới bắt đầu chuyển sang trang tính năng tương ứng.
        self.list_widget.setCurrentRow(-1)

    def _build_row_widget(self, icon_name: str, label: str):
        """Tạo 1 hàng trong list gồm icon + tên, canh lề trái trong sidebar."""
        row_widget = QWidget()
        row_widget.setAttribute(Qt.WA_StyledBackground, True)
        row_widget.setStyleSheet("background: transparent;")
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(_ROW_LEFT_PADDING, 0, 12, 0)
        row_layout.setSpacing(12)

        icon_label = QLabel()
        icon_label.setStyleSheet("background: transparent;")
        icon_label.setPixmap(
            qta.icon(icon_name, color=COLOR_SIDEBAR_TEXT).pixmap(_ICON_SIZE, _ICON_SIZE)
        )
        row_layout.addWidget(icon_label)

        text_label = QLabel(label)
        text_label.setStyleSheet(
            f"color: {COLOR_SIDEBAR_TEXT}; background: transparent; font-weight: 600;"
        )
        row_layout.addWidget(text_label)

        row_layout.addStretch()
        return row_widget, icon_label, text_label

    def _list_stylesheet(self) -> str:
        return f"""
            QListWidget {{
                background-color: transparent;
                border: none;
                outline: none;
            }}
            QListWidget::item {{
                border-left: 1px solid transparent;
                border-right: 1px solid transparent;
            }}
            QListWidget::item:selected {{
                background-color: rgba(47, 111, 237, 0.3);
                border-left: 1px solid {COLOR_ACCENT};
            }}
            QListWidget::item:hover:!selected {{
                background-color: rgba(255, 255, 255, 0.08);
            }}
            QListWidget::item:selected:hover {{
                background-color: rgba(47, 111, 237, 0.28);
                border-left: 1px solid {COLOR_ACCENT};
            }}
        """

    def _round_button_stylesheet(self) -> str:
        """Style dùng chung cho nút Home và Logout — hình vuông bo góc, có hover."""
        return """
            QToolButton {
                background-color: transparent;
                border: none;
                padding: 8px;
                border-radius: 8px;
            }
            QToolButton:hover {
                background-color: rgba(255, 255, 255, 0.08);
            }
            """

    def _on_row_changed(self, row: int) -> None:

        for i, (_key, _label, icon_name) in enumerate(FEATURES):
            is_selected = i == row
            icon_color = COLOR_ACCENT if is_selected else COLOR_SIDEBAR_TEXT
            text_color = "white" if is_selected else COLOR_SIDEBAR_TEXT
            self._icon_labels[i].setPixmap(
                qta.icon(icon_name, color=icon_color).pixmap(_ICON_SIZE, _ICON_SIZE)
            )
            self._text_labels[i].setStyleSheet(
                f"color: {text_color}; background: transparent; font-weight: 600;"
            )

        if row < 0:
            return

        key = FEATURES[row][0]
        self.feature_selected.emit(key)

    def _on_home_clicked(self) -> None:
        """Bấm nút Home: bỏ chọn mục tính năng đang chọn (nếu có) rồi báo main_window
        chuyển khung nội dung về màn hình chào."""
        self.list_widget.setCurrentRow(-1)
        self.home_requested.emit()

    def clear_selection(self) -> None:
        """Bỏ chọn mục sidebar — dùng khi cần quay lại màn hình chào."""
        self.list_widget.setCurrentRow(-1)