"""
Sidebar điều hướng bên trái. Thứ tự từ trên xuống: logo phần mềm, tên phần
mềm, nhóm "Menu Tools" (4 tính năng xử lý PDF: Tách/Gộp/Edit/Chèn), nhóm
"Quản lý" (Đổi Tên/Bảo vệ/Watermark), rồi đến hàng nút Home + Logout ở cuối.
2 nhóm dùng 2 QListWidget riêng để có thể chèn nhãn tiêu đề nhóm ở giữa —
khi chọn 1 mục ở nhóm này thì tự động bỏ chọn mục đang chọn ở nhóm kia,
đảm bảo toàn sidebar luôn chỉ có đúng 1 mục active tại một thời điểm.

Lưu ý: "Bảo vệ" và "Watermark" hiện chỉ là mục UI trong sidebar (đại ca sẽ
bổ sung đặc tả nghiệp vụ sau) — chưa có widget/logic xử lý tương ứng, bấm
vào vẫn phát feature_selected("protect") / feature_selected("watermark")
như các mục khác.

Mục đang chọn có highlight màu accent. Phát tín hiệu feature_selected(key)
khi người dùng bấm chọn 1 tính năng, home_requested khi bấm nút Home (quay về
màn hình chào), và logout_requested khi bấm nút đóng phần mềm.
"""
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

# Nhóm 1 — "Menu Tools": các tính năng xử lý PDF gốc đã chốt trong 02_dac_ta_tinh_nang.md
# (khóa nội bộ, tên hiển thị, icon mdi6)
MENU_FEATURES: List[Tuple[str, str, str]] = [
    ("split", "Tách File", "mdi6.call-split"),
    ("merge", "Gộp File", "mdi6.file-multiple-outline"),
    ("edit", "Edit File", "mdi6.file-document-edit-outline"),
    ("insert", "Chèn File", "mdi6.file-plus-outline"),
]

# Nhóm 2 — "Quản lý": Đổi Tên (đã có đặc tả, chờ chốt quy ước TX/RX/OPC) + Bảo vệ/Watermark
# (2 mục mới, hiện chỉ thêm UI, đại ca sẽ bổ sung đặc tả nghiệp vụ sau).
MANAGE_FEATURES: List[Tuple[str, str, str]] = [
    ("rename", "Đổi Tên", "mdi6.form-textbox"),
    ("protect", "Bảo vệ", "mdi6.lock-outline"),
    ("watermark", "Watermark", "mdi6.water-outline"),
]

# Giữ biến FEATURES (gộp cả 2 nhóm) để tương thích ngược nếu module khác có import
# danh sách đầy đủ tính năng từ sidebar.py.
FEATURES: List[Tuple[str, str, str]] = MENU_FEATURES + MANAGE_FEATURES

_ITEM_HEIGHT = 44
_ICON_SIZE = 18
_GROUP_ICON_SIZE = 20
_LOGOUT_ICON_SIZE = 20
_ROW_LEFT_PADDING = 20
_GROUP_HEADER_LEFT_PADDING = 20
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
        layout.setContentsMargins(0, 48, 0, 16)
        layout.setSpacing(0)

        # --- 1. Logo phần mềm (giữ nguyên như thiết kế cũ) ---
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

        # --- 2. Tên phần mềm (giữ nguyên như thiết kế cũ) ---
        title_label = QLabel("Vishipel PDF Tools")
        title_label.setWordWrap(True)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(
            "color: white; font-size: 16px; font-weight: 600; padding: 8px 12px 16px 12px;"
        )
        layout.addWidget(title_label)
        layout.addSpacing(24)

        # Nơi lưu ánh xạ id(QListWidget) -> (danh sách feature, icon_labels, text_labels)
        # để _on_list_selected có thể tự reset màu của nhóm còn lại khi chuyển chọn.
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

        # --- 5. Hàng nút Home + Logout ở cuối sidebar (giữ nguyên như thiết kế cũ) ---
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
        self.list_menu.setCurrentRow(-1)
        self.list_manage.setCurrentRow(-1)

    def _build_group_header(self, icon_name: str, text: str) -> QWidget:
        """Tạo nhãn tiêu đề nhóm (icon + chữ, bold, không dùng màu Accent — chỉ là
        nhãn phân loại nhóm chức năng, không phải mục có thể bấm chọn)."""
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
        """Tạo 1 QListWidget chứa các mục tính năng của 1 nhóm (icon + tên).
        Chiều cao cố định theo đúng số mục để không chiếm chỗ thừa/có scrollbar."""
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

    def _reset_group_colors(self, list_widget: QListWidget) -> None:
        """Đưa toàn bộ icon/text của 1 nhóm về màu mặc định (không chọn) —
        dùng khi bỏ chọn 1 nhóm do người dùng vừa chọn mục ở nhóm kia."""
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
        """Xử lý khi 1 mục trong 1 nhóm được chọn: cập nhật màu highlight cho nhóm
        hiện tại, bỏ chọn mục đang chọn (nếu có) ở nhóm còn lại, rồi phát feature_selected."""
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

        # Bỏ chọn nhóm còn lại mà không phát sinh vòng lặp tín hiệu, rồi tự reset màu
        # của nhóm đó (vì blockSignals nên _on_list_selected không tự chạy cho nó).
        other_list.blockSignals(True)
        other_list.setCurrentRow(-1)
        other_list.blockSignals(False)
        self._reset_group_colors(other_list)

        key = features[row][0]
        self.feature_selected.emit(key)

    def _on_home_clicked(self) -> None:
        """Bấm nút Home: bỏ chọn mục tính năng đang chọn (nếu có) rồi báo main_window
        chuyển khung nội dung về màn hình chào."""
        self.clear_selection()
        self.home_requested.emit()

    def clear_selection(self) -> None:
        """Bỏ chọn mục sidebar (ở cả 2 nhóm) — dùng khi cần quay lại màn hình chào."""
        self.list_menu.setCurrentRow(-1)
        self.list_manage.setCurrentRow(-1)