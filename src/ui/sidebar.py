""" /src/ui/sidebar.py """
from __future__ import annotations

import os
from typing import Dict, List, Tuple

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
    QSizePolicy,
    QToolButton,
)

from src.ui.vishipel_theme import (
    COLOR_SIDEBAR_BG,
    COLOR_SIDEBAR_TEXT,
    COLOR_ACCENT,
    SIDEBAR_WIDTH,
)

# Nhóm 1 — "Menu Tools"
MENU_FEATURES: List[Tuple[str, str, str]] = [
    ("split", "Tách File", "mdi6.call-split"),
    ("merge", "Gộp File", "mdi6.file-multiple-outline"),
    ("edit", "Edit File", "mdi6.file-document-edit-outline"),
    ("insert", "Chèn File", "mdi6.file-plus-outline"),
]

# Nhóm 2 — "Quản lý"
MANAGE_FEATURES: List[Tuple[str, str, str]] = [
    ("rename", "Đổi Tên", "mdi6.form-textbox"),
    ("protect", "Bảo vệ", "mdi6.lock-outline"),
    ("watermark", "Watermark", "mdi6.water-outline"),
]

FEATURES: List[Tuple[str, str, str]] = MENU_FEATURES + MANAGE_FEATURES

_ITEM_HEIGHT = 44
_ICON_SIZE = 18
_GROUP_ICON_SIZE = 20

_FOOTER_ICON_SIZE = 20
_ROW_LEFT_PADDING = 20
_GROUP_HEADER_LEFT_PADDING = 20
_LOGO_SIZE = 160

_CLEAR_LOG_ICON = "mdi6.delete-outline"


_LOGO_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "icon", "logo.png")
)


class Sidebar(QWidget):

    feature_selected = Signal(str)
    home_requested = Signal()
    logout_requested = Signal()
    clear_log_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(SIDEBAR_WIDTH)

        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {COLOR_SIDEBAR_BG};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 48, 0, 16)
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

        # --- 2. Tên phần mềm  ---
        title_label = QLabel("Vishipel PDF Tools")
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            "color: white; font-size: 16px; font-weight: 600; padding: 8px 12px 16px 12px;"
        )
        layout.addWidget(title_label)
        layout.addSpacing(24)


        self._group_map: Dict[int, Tuple[List[Tuple[str, str, str]], List[QLabel], List[QLabel]]] = {}

        # --- 3. Nhóm "Menu Tools" ---
        layout.addWidget(self._build_group_header("mdi6.cog-outline", "Menu Tools"))
        self.list_menu, self._icon_labels_menu, self._text_labels_menu = self._build_feature_list(
            MENU_FEATURES
        )
        layout.addWidget(self.list_menu)

        layout.addSpacing(36)

        # --- 4. Nhóm "Quản lý" ---
        layout.addWidget(self._build_group_header("mdi6.shield-outline", "Quản lý"))
        self.list_manage, self._icon_labels_manage, self._text_labels_manage = self._build_feature_list(
            MANAGE_FEATURES
        )
        layout.addWidget(self.list_manage)

        self._group_map[id(self.list_menu)] = (MENU_FEATURES, self._icon_labels_menu, self._text_labels_menu)
        self._group_map[id(self.list_manage)] = (
            MANAGE_FEATURES,
            self._icon_labels_manage,
            self._text_labels_manage,
        )

        self.list_menu.currentRowChanged.connect(
            lambda row: self._on_list_selected(self.list_menu, self.list_manage, MENU_FEATURES, row)
        )
        self.list_manage.currentRowChanged.connect(
            lambda row: self._on_list_selected(self.list_manage, self.list_menu, MANAGE_FEATURES, row)
        )

        layout.addStretch()

        # --- 5. Hàng nút Home - Logout - Clear log ở cuối sidebar ---

        self.home_button = QToolButton()
        self.home_button.setIcon(qta.icon("mdi6.home-outline", color=COLOR_SIDEBAR_TEXT))
        self.home_button.setIconSize(QSize(_FOOTER_ICON_SIZE, _FOOTER_ICON_SIZE))
        self.home_button.setToolTip("Về màn hình chính")
        self.home_button.setCursor(Qt.PointingHandCursor)
        self.home_button.setAutoRaise(True)
        self.home_button.setStyleSheet(self._round_button_stylesheet())
        self.home_button.clicked.connect(self._on_home_clicked)

        self.logout_button = QToolButton()
        self.logout_button.setIcon(qta.icon("mdi6.logout", color=COLOR_SIDEBAR_TEXT))
        self.logout_button.setIconSize(QSize(_FOOTER_ICON_SIZE, _FOOTER_ICON_SIZE))
        self.logout_button.setToolTip("Đóng phần mềm")
        self.logout_button.setCursor(Qt.PointingHandCursor)
        self.logout_button.setAutoRaise(True)
        self.logout_button.setStyleSheet(self._round_button_stylesheet())
        self.logout_button.clicked.connect(self.logout_requested.emit)


        self.clear_log_button = QToolButton()
        self.clear_log_button.setIcon(qta.icon(_CLEAR_LOG_ICON, color=COLOR_SIDEBAR_TEXT))
        self.clear_log_button.setIconSize(QSize(_FOOTER_ICON_SIZE, _FOOTER_ICON_SIZE))
        self.clear_log_button.setToolTip("Xóa log ứng dụng")
        self.clear_log_button.setCursor(Qt.PointingHandCursor)
        self.clear_log_button.setAutoRaise(True)
        self.clear_log_button.setStyleSheet(self._round_button_stylesheet())
        self.clear_log_button.clicked.connect(self.clear_log_requested.emit)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 8, 0, 0)
        bottom_row.setSpacing(16)
        bottom_row.addStretch()
        bottom_row.addWidget(self.home_button)
        bottom_row.addWidget(self.logout_button)
        bottom_row.addWidget(self.clear_log_button)
        bottom_row.addStretch()
        layout.addLayout(bottom_row)


        self.list_menu.setCurrentRow(-1)
        self.list_manage.setCurrentRow(-1)

    def _build_group_header(self, icon_name: str, text: str) -> QWidget:

        header_widget = QWidget()
        header_widget.setAttribute(Qt.WA_StyledBackground, True)
        header_widget.setStyleSheet("background: transparent;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(_GROUP_HEADER_LEFT_PADDING, 4, 12, 8)
        header_layout.setSpacing(10)

        icon_label = QLabel()
        icon_label.setStyleSheet("background: transparent;")
        icon_label.setPixmap(
            qta.icon(icon_name, color=COLOR_SIDEBAR_TEXT).pixmap(_GROUP_ICON_SIZE, _GROUP_ICON_SIZE)
        )
        header_layout.addWidget(icon_label)

        text_label = QLabel(text)
        text_label.setStyleSheet(
            f"color: {COLOR_SIDEBAR_TEXT}; background: transparent; font-weight: 700; font-size: 17px;"
        )
        header_layout.addWidget(text_label)

        header_layout.addStretch()
        return header_widget

    def _build_feature_list(
        self, features: List[Tuple[str, str, str]]
    ) -> Tuple[QListWidget, List[QLabel], List[QLabel]]:

        list_widget = QListWidget()
        list_widget.setFrameShape(QListWidget.NoFrame)
        list_widget.setFocusPolicy(Qt.NoFocus)
        list_widget.setSelectionMode(QListWidget.SingleSelection)
        list_widget.setStyleSheet(self._list_stylesheet())
        list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_widget.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        list_widget.setFixedHeight(len(features) * _ITEM_HEIGHT)

        icon_labels: List[QLabel] = []
        text_labels: List[QLabel] = []

        for _key, label, icon_name in features:
            item = QListWidgetItem()
            item.setSizeHint(QSize(SIDEBAR_WIDTH, _ITEM_HEIGHT))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            list_widget.addItem(item)

            row_widget, icon_label, text_label = self._build_row_widget(icon_name, label)
            list_widget.setItemWidget(item, row_widget)
            icon_labels.append(icon_label)
            text_labels.append(text_label)

        return list_widget, icon_labels, text_labels

    def _build_row_widget(self, icon_name: str, label: str):

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

    def _reset_group_colors(self, list_widget: QListWidget) -> None:

        features, icon_labels, text_labels = self._group_map[id(list_widget)]
        for i, (_key, _label, icon_name) in enumerate(features):
            icon_labels[i].setPixmap(
                qta.icon(icon_name, color=COLOR_SIDEBAR_TEXT).pixmap(_ICON_SIZE, _ICON_SIZE)
            )
            text_labels[i].setStyleSheet(
                f"color: {COLOR_SIDEBAR_TEXT}; background: transparent; font-weight: 600;"
            )

    def _on_list_selected(
        self,
        source_list: QListWidget,
        other_list: QListWidget,
        features: List[Tuple[str, str, str]],
        row: int,
    ) -> None:

        _features, icon_labels, text_labels = self._group_map[id(source_list)]
        for i, (_key, _label, icon_name) in enumerate(features):
            is_selected = i == row
            icon_color = COLOR_ACCENT if is_selected else COLOR_SIDEBAR_TEXT
            text_color = "white" if is_selected else COLOR_SIDEBAR_TEXT
            icon_labels[i].setPixmap(
                qta.icon(icon_name, color=icon_color).pixmap(_ICON_SIZE, _ICON_SIZE)
            )
            text_labels[i].setStyleSheet(
                f"color: {text_color}; background: transparent; font-weight: 600;"
            )

        if row < 0:
            return


        other_list.blockSignals(True)
        other_list.setCurrentRow(-1)
        other_list.blockSignals(False)
        self._reset_group_colors(other_list)

        key = features[row][0]
        self.feature_selected.emit(key)

    def _on_home_clicked(self) -> None:

        self.clear_selection()
        self.home_requested.emit()

    def clear_selection(self) -> None:

        self.list_menu.setCurrentRow(-1)
        self.list_manage.setCurrentRow(-1)