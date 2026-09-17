"""
Giao diện tính năng Chèn File (Insert PDF) — Vishipel PDF Tools.

Đã khắc phục triệt để các lỗi UI/UX:
1. Đồng bộ khoảng cách lề và căn chỉnh Zoom ở cả Cột A và Cột B.
2. Vạch chỉ thị màu đỏ dùng 1 Widget duy nhất (Overlay Indicator), chỉ hiển thị KHI Menu chuột phải bật.
3. Hỗ trợ click chuột phải tại khu vực đầu trang 1 để chèn vào vị trí đầu tiên (Vạch xám nhạy chuột).
4. Khắc phục hoàn toàn lỗi đè/đội thumbnail khi bật Context Menu.
5. Cột B kéo dài bằng phẳng với cạnh dưới các nút bấm ở Cột A.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QEvent
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QAction
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QScrollArea,
    QFrame,
    QFileDialog,
    QMenu,
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

# ----------------------------------------------------------------------
# Dữ liệu giả lập (Mock Data)
# ----------------------------------------------------------------------
_MOCK_FILE_A = {"name": "Tai lieu 01.pdf", "pages": 12}
_MOCK_FILE_B = {"name": "Tai lieu 02.pdf", "pages": 12}

_DROPZONE_ICON_BOX = 56
_THUMB_STRIP_WIDTH = 115
_THUMB_W, _THUMB_H = 72, 94
_BADGE_SIZE = 18

# Cấu hình Zoom
_ZOOM_MIN = 0.5
_ZOOM_MAX = 2.0
_ZOOM_STEP = 0.15
_ZOOM_DEFAULT = 1.0

# Kích thước khung preview
_PREVIEW_SIDE_MARGIN = 12
_PREVIEW_MIN_PAGE_WIDTH = 220
_PREVIEW_PAGE_WIDTH_FALLBACK = 340
_PREVIEW_PAGE_HEIGHT_DEFAULT = 460

_INDICATOR_RED = COLOR_ERROR
_INDICATOR_GRAY = "#9CA3AF"
_INDICATOR_HEIGHT = 4

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


# ----------------------------------------------------------------------
# DropZone
# ----------------------------------------------------------------------
class _SingleDropZone(QFrame):
    file_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(84)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 1.5px dashed {COLOR_BORDER_STRONG};
                border-radius: 12px;
            }}
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignCenter)

        icon_box = QFrame()
        icon_box.setFixedSize(_DROPZONE_ICON_BOX - 8, _DROPZONE_ICON_BOX - 8)
        icon_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 2px solid {COLOR_ACCENT};
                border-radius: 10px;
            }}
            """
        )
        icon_box_layout = QVBoxLayout(icon_box)
        icon_box_layout.setContentsMargins(0, 0, 0, 0)
        icon_box_layout.setAlignment(Qt.AlignCenter)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.tray-arrow-up", color=COLOR_ACCENT).pixmap(QSize(24, 24)))
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_box_layout.addWidget(icon_label)
        layout.addWidget(icon_box)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        main_label = QLabel("Chọn file hoặc kéo-thả file vào đây")
        main_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(main_label)

        note_label = QLabel("Lưu ý: CHỈ CHỌN 1 FILE")
        note_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(note_label)

        layout.addLayout(text_col)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            path, _ = QFileDialog.getOpenFileName(self, "Chọn file PDF", "", "PDF Files (*.pdf)")
            if path:
                self.file_selected.emit(path)
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(".pdf"):
                self.file_selected.emit(file_path)
                break


# ----------------------------------------------------------------------
# Vùng nhạy chuột Chèn Đầu Trang (Top Zone)
# ----------------------------------------------------------------------
class _TopInsertZone(QFrame):
    right_clicked = Signal(QPoint)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(12)
        self.setCursor(Qt.PointingHandCursor)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setAlignment(Qt.AlignCenter)

        self.line = QFrame()
        self.line.setFixedHeight(2)
        self.line.setStyleSheet(f"background-color: {_INDICATOR_GRAY}; border-radius: 1px;")
        layout.addWidget(self.line)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.RightButton:
            pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self.right_clicked.emit(pos)
        super().mousePressEvent(event)


# ----------------------------------------------------------------------
# Thumbnail Item
# ----------------------------------------------------------------------
class _InsertPreviewThumb(QFrame):
    clicked = Signal(int)
    right_clicked = Signal(int, QPoint)

    def __init__(self, page_number: int, label_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.label_text = label_text if label_text else str(page_number)
        self.is_current = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(_THUMB_W, _THUMB_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        badge_row = QHBoxLayout()
        self.badge = QLabel(self.label_text)
        self.badge.setMinimumWidth(_BADGE_SIZE)
        self.badge.setFixedHeight(_BADGE_SIZE)
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
                f"border-radius: {_BADGE_SIZE // 2}px; border: none; padding: 0 4px;"
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
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.page_number)
        elif event.button() == Qt.RightButton:
            pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self.right_clicked.emit(self.page_number, pos)
        super().mousePressEvent(event)


# ----------------------------------------------------------------------
# Scroll Area Pannable
# ----------------------------------------------------------------------
class _PannableScrollArea(QScrollArea):
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
        return event.position().toPoint() if hasattr(event, "position") else event.pos()

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


# ----------------------------------------------------------------------
# Page Display
# ----------------------------------------------------------------------
class _InsertPreviewPage(QFrame):
    def __init__(self, display_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.display_text = display_text
        self.aspect_ratio = _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.number_label = QLabel(display_text)
        self.number_label.setAlignment(Qt.AlignCenter)
        self.number_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 48px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.number_label)

        self.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
        )


# ----------------------------------------------------------------------
# InsertFeatureWidget
# ----------------------------------------------------------------------
class InsertFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pages_a: List[str] = [str(i + 1) for i in range(_MOCK_FILE_A["pages"])]
        self._pages_b: List[str] = [str(i + 1) for i in range(_MOCK_FILE_B["pages"])]

        self._selected_page_a: int = 1 if self._pages_a else 0
        self._selected_page_b: int = 1 if self._pages_b else 0

        self._history_stack: List[List[str]] = []
        self._target_insert_index_b: int = 0

        self._zoom_a: float = _ZOOM_DEFAULT
        self._zoom_b: float = _ZOOM_DEFAULT

        self._thumbs_a: List[_InsertPreviewThumb] = []
        self._thumbs_b: List[_InsertPreviewThumb] = []

        self._thumb_wrappers_b: List[QWidget] = []

        self._pages_widget_a: Dict[int, _InsertPreviewPage] = {}
        self._pages_widget_b: Dict[int, _InsertPreviewPage] = {}

        self._initial_width_applied = False

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # Cột A
        col_a_widget, _ = self._build_column_a()
        root_layout.addWidget(col_a_widget, 50)

        # Cột B
        col_b_widget, _ = self._build_column_b()
        root_layout.addWidget(col_b_widget, 50)

        # Khởi tạo duy nhất 1 Vạch Chỉ Thị Đỏ (Dùng dạng Overlay Widget)
        self._red_indicator = QFrame(self.thumb_container_b)
        self._red_indicator.setFixedHeight(_INDICATOR_HEIGHT)
        self._red_indicator.setStyleSheet(
            f"background-color: {_INDICATOR_RED}; border-radius: 2px; border: none;"
        )
        self._red_indicator.hide()

        self._load_file_a(_MOCK_FILE_A["name"], self._pages_a)
        self._load_file_b(_MOCK_FILE_B["name"], self._pages_b)

    # ------------------------------------------------------------------
    # Dựng Cột A
    # ------------------------------------------------------------------
    def _build_column_a(self) -> Tuple[QWidget, QVBoxLayout]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.drop_zone_a = _SingleDropZone()
        self.drop_zone_a.file_selected.connect(self._on_file_a_selected)
        layout.addWidget(self.drop_zone_a)

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

        self.title_a = QLabel("Xem trước: —")
        self.title_a.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.title_a)
        header_row.addStretch()

        self.zoom_out_btn_a = QToolButton()
        self.zoom_out_btn_a.setCursor(Qt.PointingHandCursor)
        self.zoom_out_btn_a.setIcon(qta.icon("mdi6.magnify-minus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_out_btn_a.setIconSize(QSize(16, 16))
        self.zoom_out_btn_a.setFixedSize(26, 26)
        self.zoom_out_btn_a.setStyleSheet(_zoom_button_style())
        self.zoom_out_btn_a.clicked.connect(lambda: self._set_zoom_a(self._zoom_a - _ZOOM_STEP))
        header_row.addWidget(self.zoom_out_btn_a)

        self.zoom_label_a = QLabel(f"{round(_ZOOM_DEFAULT * 100)}%")
        self.zoom_label_a.setAlignment(Qt.AlignCenter)
        self.zoom_label_a.setFixedWidth(42)
        self.zoom_label_a.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.zoom_label_a)

        self.zoom_in_btn_a = QToolButton()
        self.zoom_in_btn_a.setCursor(Qt.PointingHandCursor)
        self.zoom_in_btn_a.setIcon(qta.icon("mdi6.magnify-plus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_in_btn_a.setIconSize(QSize(16, 16))
        self.zoom_in_btn_a.setFixedSize(26, 26)
        self.zoom_in_btn_a.setStyleSheet(_zoom_button_style())
        self.zoom_in_btn_a.clicked.connect(lambda: self._set_zoom_a(self._zoom_a + _ZOOM_STEP))
        header_row.addWidget(self.zoom_in_btn_a)

        preview_card_layout.addLayout(header_row)

        body_row = QHBoxLayout()
        body_row.setSpacing(10)

        self.thumb_scroll_a = QScrollArea()
        self.thumb_scroll_a.setFixedWidth(_THUMB_STRIP_WIDTH)
        self.thumb_scroll_a.setWidgetResizable(True)
        self.thumb_scroll_a.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }} {_SCROLLBAR_QSS}"
        )
        self.thumb_container_a = QWidget()
        self.thumb_container_a.setStyleSheet("background: transparent;")
        self.thumb_layout_a = QVBoxLayout(self.thumb_container_a)
        self.thumb_layout_a.setContentsMargins(2, 2, 6, 2)
        self.thumb_layout_a.setSpacing(10)
        self.thumb_layout_a.setAlignment(Qt.AlignTop)
        self.thumb_scroll_a.setWidget(self.thumb_container_a)
        body_row.addWidget(self.thumb_scroll_a)

        self.preview_scroll_a = _PannableScrollArea()
        self.preview_scroll_a.setWidgetResizable(True)
        self.preview_scroll_a.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {COLOR_CONTENT_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 10px;
            }}
            {_SCROLLBAR_QSS}
            """
        )
        self.preview_scroll_a.viewport_resized.connect(self._apply_zoom_a)

        self.preview_container_a = QWidget()
        self.preview_container_a.setStyleSheet("background: transparent;")
        self.preview_layout_a = QVBoxLayout(self.preview_container_a)
        self.preview_layout_a.setContentsMargins(_PREVIEW_SIDE_MARGIN, 12, _PREVIEW_SIDE_MARGIN, 12)
        self.preview_layout_a.setSpacing(16)
        self.preview_layout_a.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.preview_scroll_a.setWidget(self.preview_container_a)

        body_row.addWidget(self.preview_scroll_a, 1)
        preview_card_layout.addLayout(body_row, 1)
        layout.addWidget(preview_card, 1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        self.clear_button = QPushButton(" Clear")
        self.clear_button.setIcon(qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY))
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setFixedHeight(CONTROL_HEIGHT)
        self.clear_button.setMinimumWidth(90)
        self.clear_button.setStyleSheet(
            f"""
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
        )
        self.clear_button.clicked.connect(self._on_clear_clicked)
        bottom_row.addWidget(self.clear_button)

        self.save_button = QPushButton(" Lưu File")
        self.save_button.setIcon(qta.icon("mdi6.content-save-outline", color="white"))
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.setFixedHeight(CONTROL_HEIGHT)
        self.save_button.setMinimumWidth(130)
        self.save_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: white;
                border: none;
                border-radius: {CORNER_RADIUS}px;
                font-size: 13px;
                font-weight: 700;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: #E28104; }}
            QPushButton:pressed {{ background-color: #C87203; }}
            """
        )
        self.save_button.clicked.connect(self._on_save_clicked)
        bottom_row.addWidget(self.save_button)

        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        layout.addWidget(self.result_label)

        return container, layout

    # ------------------------------------------------------------------
    # Dựng Cột B (Kéo dài hết mép dưới bằng Cột A)
    # ------------------------------------------------------------------
    def _build_column_b(self) -> Tuple[QWidget, QVBoxLayout]:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        self.drop_zone_b = _SingleDropZone()
        self.drop_zone_b.file_selected.connect(self._on_file_b_selected)
        layout.addWidget(self.drop_zone_b)

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

        self.title_b = QLabel("Xem trước: —")
        self.title_b.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.title_b)
        header_row.addStretch()

        self.zoom_out_btn_b = QToolButton()
        self.zoom_out_btn_b.setCursor(Qt.PointingHandCursor)
        self.zoom_out_btn_b.setIcon(qta.icon("mdi6.magnify-minus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_out_btn_b.setIconSize(QSize(16, 16))
        self.zoom_out_btn_b.setFixedSize(26, 26)
        self.zoom_out_btn_b.setStyleSheet(_zoom_button_style())
        self.zoom_out_btn_b.clicked.connect(lambda: self._set_zoom_b(self._zoom_b - _ZOOM_STEP))
        header_row.addWidget(self.zoom_out_btn_b)

        self.zoom_label_b = QLabel(f"{round(_ZOOM_DEFAULT * 100)}%")
        self.zoom_label_b.setAlignment(Qt.AlignCenter)
        self.zoom_label_b.setFixedWidth(42)
        self.zoom_label_b.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.zoom_label_b)

        self.zoom_in_btn_b = QToolButton()
        self.zoom_in_btn_b.setCursor(Qt.PointingHandCursor)
        self.zoom_in_btn_b.setIcon(qta.icon("mdi6.magnify-plus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_in_btn_b.setIconSize(QSize(16, 16))
        self.zoom_in_btn_b.setFixedSize(26, 26)
        self.zoom_in_btn_b.setStyleSheet(_zoom_button_style())
        self.zoom_in_btn_b.clicked.connect(lambda: self._set_zoom_b(self._zoom_b + _ZOOM_STEP))
        header_row.addWidget(self.zoom_in_btn_b)

        preview_card_layout.addLayout(header_row)

        body_row = QHBoxLayout()
        body_row.setSpacing(10)

        self.thumb_scroll_b = QScrollArea()
        self.thumb_scroll_b.setFixedWidth(_THUMB_STRIP_WIDTH)
        self.thumb_scroll_b.setWidgetResizable(True)
        self.thumb_scroll_b.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }} {_SCROLLBAR_QSS}"
        )
        self.thumb_container_b = QWidget()
        self.thumb_container_b.setStyleSheet("background: transparent;")
        self.thumb_layout_b = QVBoxLayout(self.thumb_container_b)
        self.thumb_layout_b.setContentsMargins(2, 2, 6, 2)
        self.thumb_layout_b.setSpacing(10)
        self.thumb_layout_b.setAlignment(Qt.AlignTop)
        self.thumb_scroll_b.setWidget(self.thumb_container_b)
        body_row.addWidget(self.thumb_scroll_b)

        self.preview_scroll_b = _PannableScrollArea()
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
        self.preview_scroll_b.viewport_resized.connect(self._apply_zoom_b)

        self.preview_container_b = QWidget()
        self.preview_container_b.setStyleSheet("background: transparent;")
        self.preview_layout_b = QVBoxLayout(self.preview_container_b)
        self.preview_layout_b.setContentsMargins(_PREVIEW_SIDE_MARGIN, 12, _PREVIEW_SIDE_MARGIN, 12)
        self.preview_layout_b.setSpacing(16)
        self.preview_layout_b.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.preview_scroll_b.setWidget(self.preview_container_b)

        body_row.addWidget(self.preview_scroll_b, 1)
        preview_card_layout.addLayout(body_row, 1)

        # Cột B chiếm hết không gian theo phương đứng để gióng bằng cạnh dưới Cột A
        layout.addWidget(preview_card, 1)

        return container, layout

    # ------------------------------------------------------------------
    # Render File A & File B
    # ------------------------------------------------------------------
    def _load_file_a(self, file_name: str, pages: List[str]) -> None:
        self.title_a.setText(f"Xem trước: {file_name}")
        self._pages_a = pages
        self._selected_page_a = 1 if pages else 0

        while self.thumb_layout_a.count():
            child = self.thumb_layout_a.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._thumbs_a.clear()

        for idx, page_str in enumerate(pages):
            page_num = idx + 1
            wrapper = QWidget()
            w_layout = QVBoxLayout(wrapper)
            w_layout.setContentsMargins(0, 0, 0, 0)
            w_layout.setSpacing(2)

            thumb = _InsertPreviewThumb(page_num)
            thumb.clicked.connect(self._on_thumb_a_clicked)
            w_layout.addWidget(thumb, alignment=Qt.AlignHCenter)

            num_label = QLabel(str(page_num))
            num_label.setAlignment(Qt.AlignCenter)
            num_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            w_layout.addWidget(num_label)

            self.thumb_layout_a.addWidget(wrapper)
            self._thumbs_a.append(thumb)

        for frame in self._pages_widget_a.values():
            self.preview_layout_a.removeWidget(frame)
            frame.deleteLater()
        self._pages_widget_a.clear()

        for idx, page_str in enumerate(pages):
            page_num = idx + 1
            frame = _InsertPreviewPage(page_str)
            self.preview_layout_a.addWidget(frame, alignment=Qt.AlignHCenter)
            self._pages_widget_a[page_num] = frame

        self._refresh_view_a()
        self._apply_zoom_a()

    def _load_file_b(self, file_name: str, pages: List[str]) -> None:
        self.title_b.setText(f"Xem trước: {file_name}")
        self._pages_b = pages
        if self._selected_page_b > len(pages):
            self._selected_page_b = len(pages)
        elif self._selected_page_b == 0 and pages:
            self._selected_page_b = 1

        self._hide_red_indicator()

        while self.thumb_layout_b.count():
            child = self.thumb_layout_b.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._thumbs_b.clear()
        self._thumb_wrappers_b.clear()

        # Vùng tương tác Chèn Đầu Trang (Top Zone)
        top_zone = _TopInsertZone()
        top_zone.right_clicked.connect(lambda pos: self._open_context_menu(0, pos, top_zone))
        self.thumb_layout_b.addWidget(top_zone)

        for idx, page_str in enumerate(pages):
            page_num = idx + 1
            wrapper = QWidget()
            w_layout = QVBoxLayout(wrapper)
            w_layout.setContentsMargins(0, 0, 0, 0)
            w_layout.setSpacing(2)

            thumb = _InsertPreviewThumb(page_num, label_text=page_str)
            thumb.clicked.connect(self._on_thumb_b_clicked)
            thumb.right_clicked.connect(lambda p_num, pos, w=wrapper: self._open_context_menu(p_num, pos, w))
            w_layout.addWidget(thumb, alignment=Qt.AlignHCenter)

            num_label = QLabel(str(page_num))
            num_label.setAlignment(Qt.AlignCenter)
            num_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            w_layout.addWidget(num_label)

            self.thumb_layout_b.addWidget(wrapper)
            self._thumbs_b.append(thumb)
            self._thumb_wrappers_b.append(wrapper)

        for frame in self._pages_widget_b.values():
            self.preview_layout_b.removeWidget(frame)
            frame.deleteLater()
        self._pages_widget_b.clear()

        for idx, page_str in enumerate(pages):
            page_num = idx + 1
            frame = _InsertPreviewPage(page_str)
            self.preview_layout_b.addWidget(frame, alignment=Qt.AlignHCenter)
            self._pages_widget_b[page_num] = frame

        self._refresh_view_b()
        self._apply_zoom_b()

    # ------------------------------------------------------------------
    # Xử lý Vạch chỉ thị Đỏ & Context Menu
    # ------------------------------------------------------------------
    def _position_red_indicator(self, target_widget: QWidget) -> None:
        """Định vị vạch đỏ hiển thị chính xác ngay dưới thumbnail được chọn."""
        self._red_indicator.setParent(self.thumb_container_b)
        self._red_indicator.setFixedWidth(target_widget.width() - 8)
        
        # Tính vị trí Y ngay bên dưới target_widget
        pos_y = target_widget.y() + target_widget.height() - 2
        pos_x = target_widget.x() + 4
        
        self._red_indicator.move(pos_x, pos_y)
        self._red_indicator.raise_()
        self._red_indicator.show()

    def _hide_red_indicator(self) -> None:
        if hasattr(self, "_red_indicator"):
            self._red_indicator.hide()

    def _open_context_menu(self, insert_index: int, global_pos: QPoint, target_widget: QWidget) -> None:
        """Kích hoạt Menu chuột phải và hiển thị Vạch Đỏ."""
        self._target_insert_index_b = insert_index
        
        if insert_index > 0:
            self._selected_page_b = insert_index
            self._refresh_view_b()

        # Hiển thị vạch đỏ
        self._position_red_indicator(target_widget)

        context_menu = QMenu(self)
        context_menu.setStyleSheet(
            f"""
            QMenu {{
                background-color: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 18px 6px 12px;
                border-radius: 4px;
                font-size: 13px;
                font-weight: 600;
            }}
            QMenu::item:selected {{
                background-color: {COLOR_ACCENT_LIGHT};
                color: {COLOR_ACCENT};
            }}
            QMenu::item:disabled {{
                color: {COLOR_TEXT_SECONDARY};
                background-color: transparent;
            }}
            """
        )

        insert_action = QAction(qta.icon("mdi6.file-plus-outline", color=COLOR_ACCENT), "Chèn", self)
        insert_action.triggered.connect(self._execute_insert)
        context_menu.addAction(insert_action)

        undo_action = QAction(
            qta.icon("mdi6.undo-variant", color=COLOR_ACCENT if self._history_stack else COLOR_TEXT_SECONDARY),
            "Undo",
            self,
        )
        undo_action.setEnabled(bool(self._history_stack))
        undo_action.triggered.connect(self._execute_undo)
        context_menu.addAction(undo_action)

        # Ẩn vạch đỏ khi Menu đóng
        context_menu.aboutToHide.connect(self._hide_red_indicator)
        context_menu.exec(global_pos)

    # ------------------------------------------------------------------
    # Thao tác Chèn & Undo
    # ------------------------------------------------------------------
    def _execute_insert(self) -> None:
        if not self._pages_a or self._selected_page_a < 1:
            self._show_error("Vui lòng chọn trang từ Cột A để chèn!")
            return

        self._history_stack.append(list(self._pages_b))

        page_content_from_a = self._pages_a[self._selected_page_a - 1]
        insert_pos = self._target_insert_index_b

        self._pages_b.insert(insert_pos, f"A-{page_content_from_a}")
        self._selected_page_b = insert_pos + 1

        self._load_file_b(_MOCK_FILE_B["name"], self._pages_b)
        self._show_success(f"Đã chèn thành công trang {self._selected_page_a} của File A vào vị trí {insert_pos}!")

    def _execute_undo(self) -> None:
        if not self._history_stack:
            return

        previous_state = self._history_stack.pop()
        self._pages_b = previous_state
        self._load_file_b(_MOCK_FILE_B["name"], self._pages_b)
        self._show_success("Đã hoàn tác (Undo) thao tác chèn trước đó.")

    # ------------------------------------------------------------------
    # Event Handlers & Sync
    # ------------------------------------------------------------------
    def _on_thumb_a_clicked(self, page_num: int) -> None:
        self._selected_page_a = page_num
        self._refresh_view_a()

    def _on_thumb_b_clicked(self, page_num: int) -> None:
        self._hide_red_indicator()
        self._selected_page_b = page_num
        self._refresh_view_b()

    def _refresh_view_a(self) -> None:
        for thumb in self._thumbs_a:
            thumb.set_current(thumb.page_number == self._selected_page_a)
        if 0 <= self._selected_page_a - 1 < len(self._thumbs_a):
            self.thumb_scroll_a.ensureWidgetVisible(self._thumbs_a[self._selected_page_a - 1], 0, 20)

        frame = self._pages_widget_a.get(self._selected_page_a)
        if frame:
            self.preview_scroll_a.ensureWidgetVisible(frame, 0, 0)

    def _refresh_view_b(self) -> None:
        for thumb in self._thumbs_b:
            thumb.set_current(thumb.page_number == self._selected_page_b)
        if 0 <= self._selected_page_b - 1 < len(self._thumbs_b):
            self.thumb_scroll_b.ensureWidgetVisible(self._thumbs_b[self._selected_page_b - 1], 0, 20)

        frame = self._pages_widget_b.get(self._selected_page_b)
        if frame:
            self.preview_scroll_b.ensureWidgetVisible(frame, 0, 0)

# ------------------------------------------------------------------
    # Zoom Management (Đã khắc phục lỗi khoảng cách biên lớn)
    # ------------------------------------------------------------------
    def _set_zoom_a(self, level: float) -> None:
        clamped = max(_ZOOM_MIN, min(_ZOOM_MAX, round(level, 2)))
        self._zoom_a = clamped
        self.zoom_label_a.setText(f"{round(self._zoom_a * 100)}%")
        self.zoom_in_btn_a.setEnabled(self._zoom_a < _ZOOM_MAX - 1e-6)
        self.zoom_out_btn_a.setEnabled(self._zoom_a > _ZOOM_MIN + 1e-6)
        self._apply_zoom_a()

    def _set_zoom_b(self, level: float) -> None:
        clamped = max(_ZOOM_MIN, min(_ZOOM_MAX, round(level, 2)))
        self._zoom_b = clamped
        self.zoom_label_b.setText(f"{round(self._zoom_b * 100)}%")
        self.zoom_in_btn_b.setEnabled(self._zoom_b < _ZOOM_MAX - 1e-6)
        self.zoom_out_btn_b.setEnabled(self._zoom_b > _ZOOM_MIN + 1e-6)
        self._apply_zoom_b()

    def _apply_zoom_a(self) -> None:
        if not self._pages_widget_a:
            return
            
        # Kiểm tra sự tồn tại của thanh cuộn dọc để trừ độ rộng chính xác
        v_bar = self.preview_scroll_a.verticalScrollBar()
        v_bar_width = v_bar.width() if v_bar.isVisible() else 0
        
        # Lấy chiều rộng thực tế của viewport và tính toán khoảng rộng khả dụng
        viewport_w = self.preview_scroll_a.viewport().width()
        usable_w = viewport_w - (_PREVIEW_SIDE_MARGIN * 2) - v_bar_width
        
        # Đảm bảo chiều rộng không vượt quá khung nhìn khả dụng ở tỷ lệ 100%
        base_w = max(_PREVIEW_MIN_PAGE_WIDTH, usable_w)
        width = round(base_w * self._zoom_a)

        for frame in self._pages_widget_a.values():
            height = round(width * frame.aspect_ratio)
            frame.setFixedSize(width, height)

    def _apply_zoom_b(self) -> None:
        if not self._pages_widget_b:
            return
            
        v_bar = self.preview_scroll_b.verticalScrollBar()
        v_bar_width = v_bar.width() if v_bar.isVisible() else 0
        
        viewport_w = self.preview_scroll_b.viewport().width()
        usable_w = viewport_w - (_PREVIEW_SIDE_MARGIN * 2) - v_bar_width
        
        base_w = max(_PREVIEW_MIN_PAGE_WIDTH, usable_w)
        width = round(base_w * self._zoom_b)

        for frame in self._pages_widget_b.values():
            height = round(width * frame.aspect_ratio)
            frame.setFixedSize(width, height)

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------
    def _on_file_a_selected(self, path: str) -> None:
        name = path.replace("\\", "/").split("/")[-1]
        self._load_file_a(name, [str(i + 1) for i in range(10)])
        self._hide_result()

    def _on_file_b_selected(self, path: str) -> None:
        name = path.replace("\\", "/").split("/")[-1]
        self._history_stack.clear()
        self._target_insert_index_b = 0
        self._load_file_b(name, [str(i + 1) for i in range(10)])
        self._hide_result()

    def _on_clear_clicked(self) -> None:
        self._history_stack.clear()
        self._target_insert_index_b = 0
        self._load_file_a("—", [])
        self._load_file_b("—", [])
        self._hide_result()

    def _on_save_clicked(self) -> None:
        if not self._pages_b:
            self._show_error("Không có nội dung file B để xuất ra tài liệu mới!")
            return
        self._show_success(f"[Demo Giao diện] Đã xuất file thành công gồm {len(self._pages_b)} trang!")

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_width_applied:
            self._initial_width_applied = True
            self._apply_zoom_a()
            self._apply_zoom_b()

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