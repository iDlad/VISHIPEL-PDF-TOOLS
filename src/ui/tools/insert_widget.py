"""
Giao diện tính năng Chèn File (Insert PDF) — Vishipel PDF Tools.

Đã nối logic thật với `pdf_core.InsertSession` (04_kien_truc_module_va_flow.md,
02_dac_ta_tinh_nang.md mục 4):
1. Chọn File A / File B qua `pdf_core.get_page_count` để validate (hỏng/mật khẩu)
   ngay khi chọn file — không cho file lỗi vào danh sách xử lý.
2. Khi đã có đủ 2 file, khởi tạo `InsertSession(path_a, path_b)` — giữ bản làm việc
   của File B trong bộ nhớ, chưa ghi ra đĩa.
3. Cột A: chuột phải → Đánh dấu 1 trang (đúng đặc tả, tách biệt với việc click trái
   chỉ để xem trước — trước đây UI demo nhầm dùng chung 1 biến).
4. Cột B: chuột phải vào 1 thumbnail (hoặc vùng đầu trang) → chọn vị trí chèn → menu
   "Chèn" gọi `session.mark_page_a` + `session.select_insert_position_b` +
   `session.perform_insert()` — Cột B tự render lại từ bản làm việc mới nhất.
5. Nút "Lưu File": chặn nếu còn trang A đang đánh dấu mà chưa Chèn (đúng thông báo
   lỗi đã chốt ở 02_dac_ta_tinh_nang.md mục 4), hỏi Ghi đè/Đổi tên khác/Hủy khi trùng
   tên (mục 6), tên gợi ý mặc định `<tenfileB>_Insert.pdf`.
6. Đã bỏ tính năng "Undo" của bản demo cũ: không có trong đặc tả đã chốt (mục 4 chỉ
   liệt kê 3 nút Chèn/Lưu file/Clear) và `InsertSession` không có cơ chế hoàn tác một
   lượt chèn trên bản làm việc trong bộ nhớ — giữ lại sẽ là 1 nút không hoạt động thật.

Việc render ảnh trang dùng `pdf_core.PageRenderer` (từ path, cho File A và cho File B
TRƯỚC khi có session) và `pdf_core.render_document_page` (từ đối tượng fitz.Document
đang mở trong bộ nhớ, dùng riêng cho Cột B SAU khi session đã tạo — xem mục 8 mới
thêm vào pdf_core.py, không đụng gì đến PageRenderer đang dùng cho Tách file/Edit).
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QAction, QPixmap, QDesktopServices
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
    QMessageBox,
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
from src.pdf_core import (
    get_page_count,
    PageRenderer,
    InsertSession,
    render_document_page,
    CorruptedFileError,
    PasswordProtectedError,
    FileLockedError,
)
from src.logger import log_info, log_error
from src.undo_logic import InsertUndoManager

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

# Độ phân giải render — thumbnail nhỏ cho dải bên trái, ảnh lớn cho khung Preview
_THUMB_RENDER_WIDTH = 160
_DETAIL_RENDER_WIDTH = 760

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


def _context_menu_qss() -> str:
    """QSS dùng chung cho context menu của cả Cột A (Đánh dấu) và Cột B (Chèn) —
    gộp lại 1 chỗ để không lặp lại y hệt 2 lần như bản demo cũ."""
    return f"""
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


def _message_box_style() -> str:
    """QSS bắt buộc cho QMessageBox theo 01_dac_ta_giao_dien.md mục 3 — không dùng
    style mặc định vì theme nền tối của app có thể làm chữ trắng-trên-trắng."""
    return f"""
        QMessageBox {{ background-color: white; }}
        QLabel {{ color: {COLOR_TEXT_PRIMARY}; font-size: 13px; background: transparent; }}
        QPushButton {{
            background-color: white;
            color: {COLOR_TEXT_PRIMARY};
            border: 1.5px solid {COLOR_BORDER_STRONG};
            border-radius: {CORNER_RADIUS}px;
            padding: 6px 16px;
            font-size: 13px;
            font-weight: 700;
            min-width: 88px;
        }}
        QPushButton:hover {{ background-color: #F3F4F6; }}
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

    def __init__(self, page_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.is_current = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(_THUMB_W, _THUMB_H)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setScaledContents(True)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.image_label, 1)

        self._apply_style()

    def set_thumbnail(self, png_bytes: Optional[bytes]) -> None:
        """Gán ảnh thật render từ pdf_core. Không có ảnh (lỗi render) → hiện dấu '?'."""
        if not png_bytes:
            self.image_label.setScaledContents(False)
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("?")
            self.image_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 20px; font-weight: 700; "
                "background: transparent; border: none;"
            )
            return
        pixmap = QPixmap()
        pixmap.loadFromData(png_bytes)
        self.image_label.setScaledContents(True)
        self.image_label.setText("")
        self.image_label.setStyleSheet("background: transparent; border: none;")
        self.image_label.setPixmap(pixmap)

    def _apply_style(self) -> None:
        if self.is_current:
            self.setStyleSheet(
                f"QFrame {{ background-color: {COLOR_ACCENT_LIGHT}; border: 2px solid {COLOR_ACCENT}; border-radius: 6px; }}"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
            )

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
# Page Display — hiển thị ảnh thật (thay vì số to giả lập)
# ----------------------------------------------------------------------
class _InsertPreviewPage(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.aspect_ratio = _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setScaledContents(True)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.image_label)

        self.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
        )

    def set_image(self, png_bytes: Optional[bytes]) -> None:
        if not png_bytes:
            self.image_label.setScaledContents(False)
            self.image_label.setPixmap(QPixmap())
            self.image_label.setText("Không thể xem trước trang này")
            self.image_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            return
        pixmap = QPixmap()
        pixmap.loadFromData(png_bytes)
        if pixmap.width() and pixmap.height():
            self.aspect_ratio = pixmap.height() / pixmap.width()
        self.image_label.setScaledContents(True)
        self.image_label.setText("")
        self.image_label.setStyleSheet("background: transparent; border: none;")
        self.image_label.setPixmap(pixmap)


# ----------------------------------------------------------------------
# InsertFeatureWidget
# ----------------------------------------------------------------------
class InsertFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # --- Trạng thái dữ liệu thật (thay cho _pages_a/_pages_b kiểu chuỗi giả) ---
        self._path_a: Optional[str] = None
        self._path_b: Optional[str] = None
        self._page_count_a: int = 0
        self._session: Optional[InsertSession] = None

        # Renderer cho Cột A (luôn đọc từ path_a, không đổi trong suốt phiên làm việc)
        # và Renderer tạm cho Cột B TRƯỚC khi có session (đọc từ path_b trên đĩa).
        # Sau khi có session, Cột B render qua render_document_page(working_document)
        # (xem pdf_core.py mục 8) — không dùng renderer có cache vì nội dung B đổi
        # liên tục sau mỗi lượt chèn.
        self._renderer_a = PageRenderer()
        self._renderer_b_static = PageRenderer()

        # Undo riêng cho Chèn file — xem src/undo_logic.py (không dùng chung với
        # undo_manager.py của Edit, xem lý do ở phần đề xuất đã được đại ca xác nhận).
        self._undo_manager = InsertUndoManager()

        # Trang A đang được click chọn (Cột A không còn thao tác "Đánh dấu" riêng —
        # click trái vừa mở preview vừa là nguồn để chèn, theo yêu cầu đại ca).
        self._selected_page_a: int = 0
        self._selected_page_b: int = 0

        self._target_insert_index_b: int = 0

        self._zoom_a: float = _ZOOM_DEFAULT
        self._zoom_b: float = _ZOOM_DEFAULT

        self._thumbs_a: List[_InsertPreviewThumb] = []
        self._thumbs_b: List[_InsertPreviewThumb] = []

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

        self._load_file_a("—", 0)
        self._refresh_column_b_display()

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
    # Render ảnh thật — Cột A luôn từ path_a; Cột B từ path_b (trước khi có
    # session) hoặc từ working_document của session (sau khi có session).
    # ------------------------------------------------------------------
    def _render_a_thumb_bytes(self, index0: int) -> Optional[bytes]:
        if not self._path_a:
            return None
        try:
            return self._renderer_a.render_thumbnail(self._path_a, index0, max_width=_THUMB_RENDER_WIDTH)
        except (CorruptedFileError, PasswordProtectedError, FileLockedError, Exception):
            return None

    def _render_a_detail_bytes(self, index0: int) -> Optional[bytes]:
        if not self._path_a:
            return None
        try:
            return self._renderer_a.render_page_detail(self._path_a, index0, target_width=_DETAIL_RENDER_WIDTH)
        except (CorruptedFileError, PasswordProtectedError, FileLockedError, Exception):
            return None

    def _render_b_thumb_bytes(self, index0: int) -> Optional[bytes]:
        try:
            if self._session is not None:
                return render_document_page(self._session.working_document, index0, target_width=_THUMB_RENDER_WIDTH)
            if self._path_b:
                return self._renderer_b_static.render_thumbnail(self._path_b, index0, max_width=_THUMB_RENDER_WIDTH)
        except Exception:
            return None
        return None

    def _render_b_detail_bytes(self, index0: int) -> Optional[bytes]:
        try:
            if self._session is not None:
                return render_document_page(self._session.working_document, index0, target_width=_DETAIL_RENDER_WIDTH)
            if self._path_b:
                return self._renderer_b_static.render_page_detail(self._path_b, index0, target_width=_DETAIL_RENDER_WIDTH)
        except Exception:
            return None
        return None

    def _current_page_count_b(self) -> int:
        if self._session is not None:
            return self._session.working_page_count
        if self._path_b:
            try:
                return get_page_count(self._path_b)
            except (CorruptedFileError, PasswordProtectedError):
                return 0
        return 0

    # ------------------------------------------------------------------
    # Quản lý InsertSession — chỉ tạo được khi đã có đủ File A + File B
    # ------------------------------------------------------------------
    def _rebuild_session(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        # Lịch sử Undo chỉ có ý nghĩa với đúng working_document đang hoạt động —
        # đổi File A/B (tạo session mới) coi như khởi động lại, xoá sạch lịch sử cũ.
        self._undo_manager.clear()

        if not (self._path_a and self._path_b):
            return

        try:
            self._session = InsertSession(self._path_a, self._path_b)
        except PasswordProtectedError:
            self._show_error(f"File có mật khẩu, không thể mở: {os.path.basename(self._path_b)}")
            self._path_b = None
        except CorruptedFileError:
            self._show_error(f"Không thể đọc file, có thể bị hỏng: {os.path.basename(self._path_b)}")
            self._path_b = None

    # ------------------------------------------------------------------
    # Render File A & File B
    # ------------------------------------------------------------------
    def _load_file_a(self, file_name: str, count: int) -> None:
        self.title_a.setText(f"Xem trước: {file_name}")
        self._page_count_a = count
        self._selected_page_a = 1 if count else 0

        while self.thumb_layout_a.count():
            child = self.thumb_layout_a.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._thumbs_a.clear()

        for idx in range(count):
            page_num = idx + 1
            wrapper = QWidget()
            w_layout = QVBoxLayout(wrapper)
            w_layout.setContentsMargins(0, 0, 0, 0)
            w_layout.setSpacing(2)

            thumb = _InsertPreviewThumb(page_num)
            thumb.set_thumbnail(self._render_a_thumb_bytes(idx))
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

        # Dồn khoảng trống dư (khi ít trang, chưa lấp đầy khung nhìn) xuống cuối cùng
        # thay vì để Qt tự giãn đều spacing giữa các thumbnail — đây là nguyên nhân
        # gây hiện tượng "kéo giãn" khoảng cách khi số trang ít.
        self.thumb_layout_a.addStretch(1)

        while self.preview_layout_a.count():
            item = self.preview_layout_a.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pages_widget_a.clear()

        for idx in range(count):
            page_num = idx + 1
            frame = _InsertPreviewPage()
            frame.set_image(self._render_a_detail_bytes(idx))
            self.preview_layout_a.addWidget(frame, alignment=Qt.AlignHCenter)
            self._pages_widget_a[page_num] = frame

        self.preview_layout_a.addStretch(1)

        self._refresh_view_a()
        self._apply_zoom_a()

    def _refresh_column_b_display(self) -> None:
        """Dựng lại toàn bộ Cột B — dùng chung cho: chọn File B lần đầu, đổi File A/B,
        sau mỗi lượt Chèn thành công, và khi bấm Clear."""
        name = os.path.basename(self._path_b) if self._path_b else "—"
        count = self._current_page_count_b()
        self._load_file_b(name, count)

    def _load_file_b(self, file_name: str, count: int) -> None:
        self.title_b.setText(f"Xem trước: {file_name}")
        if self._selected_page_b > count:
            self._selected_page_b = count
        elif self._selected_page_b == 0 and count:
            self._selected_page_b = 1

        self._hide_red_indicator()

        while self.thumb_layout_b.count():
            child = self.thumb_layout_b.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._thumbs_b.clear()

        # Vùng tương tác Chèn Đầu Trang (Top Zone)
        top_zone = _TopInsertZone()
        top_zone.right_clicked.connect(lambda pos: self._open_context_menu(0, pos, top_zone))
        self.thumb_layout_b.addWidget(top_zone)

        for idx in range(count):
            page_num = idx + 1
            wrapper = QWidget()
            w_layout = QVBoxLayout(wrapper)
            w_layout.setContentsMargins(0, 0, 0, 0)
            w_layout.setSpacing(2)

            thumb = _InsertPreviewThumb(page_num)
            thumb.set_thumbnail(self._render_b_thumb_bytes(idx))
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

        self.thumb_layout_b.addStretch(1)

        while self.preview_layout_b.count():
            item = self.preview_layout_b.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._pages_widget_b.clear()

        for idx in range(count):
            page_num = idx + 1
            frame = _InsertPreviewPage()
            frame.set_image(self._render_b_detail_bytes(idx))
            self.preview_layout_b.addWidget(frame, alignment=Qt.AlignHCenter)
            self._pages_widget_b[page_num] = frame

        self.preview_layout_b.addStretch(1)

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
        """Menu chuột phải ở Cột B — chọn vị trí chèn rồi bấm "Chèn".
        insert_index = 0 nghĩa là chèn vào đầu file (Top Zone); insert_index = N (>0)
        nghĩa là chèn ngay sau trang thứ N (1-based)."""
        if self._session is None:
            self._show_error("Vui lòng chọn đủ File A và File B trước khi thao tác!")
            return

        self._target_insert_index_b = insert_index

        if insert_index > 0:
            self._selected_page_b = insert_index
            self._refresh_view_b()

        self._position_red_indicator(target_widget)

        context_menu = QMenu(self)
        context_menu.setStyleSheet(_context_menu_qss())

        insert_action = QAction(qta.icon("mdi6.file-plus-outline", color=COLOR_ACCENT), "Chèn", self)
        insert_action.setEnabled(self._selected_page_a >= 1)
        insert_action.triggered.connect(self._execute_insert)
        context_menu.addAction(insert_action)

        can_undo = self._undo_manager.can_undo()
        undo_action = QAction(
            qta.icon("mdi6.undo-variant", color=COLOR_ACCENT if can_undo else COLOR_TEXT_SECONDARY),
            "Undo",
            self,
        )
        undo_action.setEnabled(can_undo)
        undo_action.triggered.connect(self._execute_undo)
        context_menu.addAction(undo_action)

        context_menu.aboutToHide.connect(self._hide_red_indicator)
        context_menu.exec(global_pos)

    # ------------------------------------------------------------------
    # Thao tác Chèn & Undo (gọi InsertSession + InsertUndoManager thật)
    # ------------------------------------------------------------------
    def _execute_insert(self) -> None:
        if self._session is None:
            self._show_error("Vui lòng chọn đủ File A và File B trước khi chèn!")
            return
        if self._selected_page_a < 1:
            self._show_error("Vui lòng chọn trang từ Cột A để chèn!")
            return

        source_page = self._selected_page_a
        insert_index = self._target_insert_index_b

        self._session.mark_page_a(source_page - 1)
        self._session.select_insert_position_b(insert_index - 1)
        try:
            self._session.perform_insert()
        except (ValueError, FileLockedError, CorruptedFileError) as exc:
            self._show_error(str(exc))
            log_error(f"Lỗi khi chèn trang {source_page} của File A vào vị trí {insert_index}: {exc}", exc)
            return

        # Trang vừa chèn nằm ở đúng index = insert_index trong working_document
        # (vì start_at = selected_position_b + 1 = insert_index, xem pdf_core.py
        # InsertSession.perform_insert) — dùng đúng giá trị này để Undo sau này biết
        # xoá đúng trang.
        self._undo_manager.register(start_index=insert_index, page_count=1)

        log_info(f"Đã chèn trang {source_page} của File A vào File B tại vị trí {insert_index}")
        self._selected_page_b = insert_index + 1
        self._refresh_column_b_display()
        self._show_success(f"Đã chèn thành công trang {source_page} của File A vào vị trí {insert_index}!")

    def _execute_undo(self) -> None:
        if self._session is None or not self._undo_manager.can_undo():
            return
        if not self._undo_manager.undo(self._session.working_document):
            return

        log_info("Đã hoàn tác (Undo) 1 lượt chèn trang ở tính năng Chèn file")
        self._refresh_column_b_display()
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
    # Zoom Management (giữ nguyên logic — không liên quan pdf_core)
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

        v_bar = self.preview_scroll_a.verticalScrollBar()
        v_bar_width = v_bar.width() if v_bar.isVisible() else 0

        viewport_w = self.preview_scroll_a.viewport().width()
        usable_w = viewport_w - (_PREVIEW_SIDE_MARGIN * 2) - v_bar_width

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
    # Actions — chọn file (validate thật qua pdf_core)
    # ------------------------------------------------------------------
    def _on_file_a_selected(self, path: str) -> None:
        try:
            count = get_page_count(path)
        except PasswordProtectedError:
            self._show_error(f"File có mật khẩu, không thể mở: {os.path.basename(path)}")
            return
        except CorruptedFileError:
            self._show_error(f"Không thể đọc file, có thể bị hỏng: {os.path.basename(path)}")
            return

        self._path_a = path
        self._load_file_a(os.path.basename(path), count)
        self._rebuild_session()
        self._refresh_column_b_display()
        self._hide_result()
        log_info(f"Đã chọn File A (Insert): {path}")

    def _on_file_b_selected(self, path: str) -> None:
        try:
            get_page_count(path)
        except PasswordProtectedError:
            self._show_error(f"File có mật khẩu, không thể mở: {os.path.basename(path)}")
            return
        except CorruptedFileError:
            self._show_error(f"Không thể đọc file, có thể bị hỏng: {os.path.basename(path)}")
            return

        self._path_b = path
        self._selected_page_b = 0
        self._target_insert_index_b = 0
        self._rebuild_session()
        self._refresh_column_b_display()
        self._hide_result()
        log_info(f"Đã chọn File B (Insert): {path}")

    def _on_clear_clicked(self) -> None:
        if self._session is not None:
            self._session.close()
            self._session = None
        self._path_a = None
        self._path_b = None
        self._renderer_a.clear_cache()
        self._renderer_b_static.clear_cache()
        self._undo_manager.clear()
        self._selected_page_a = 0
        self._selected_page_b = 0
        self._target_insert_index_b = 0
        self._load_file_a("—", 0)
        self._refresh_column_b_display()
        self._hide_result()

    def _confirm_overwrite(self, path: str) -> str:
        """Hỏi Ghi đè / Đổi tên khác / Hủy khi trùng tên file lưu kết quả
        (02_dac_ta_tinh_nang.md mục 6). Style tường minh theo 01_dac_ta_giao_dien.md
        mục 3 — không dùng QMessageBox mặc định."""
        box = QMessageBox(self)
        box.setWindowTitle("File đã tồn tại")
        box.setIcon(QMessageBox.Warning)
        box.setText(f"File '{os.path.basename(path)}' đã tồn tại. Bạn muốn:")
        box.setStyleSheet(_message_box_style())

        overwrite_btn = box.addButton("Ghi đè", QMessageBox.AcceptRole)
        overwrite_btn.setStyleSheet(
            overwrite_btn.styleSheet() + f"background-color: {COLOR_ACCENT}; color: white; border: none;"
        )
        rename_btn = box.addButton("Đổi tên khác", QMessageBox.ActionRole)
        box.addButton("Hủy", QMessageBox.RejectRole)

        box.exec()
        clicked = box.clickedButton()
        if clicked is overwrite_btn:
            return "overwrite"
        if clicked is rename_btn:
            return "rename"
        return "cancel"

    def _on_save_clicked(self) -> None:
        if self._session is None:
            self._show_error("Vui lòng chọn đủ File A và File B trước khi lưu!")
            return
        if self._session.has_pending_mark():
            self._show_error("Chưa thực hiện chèn, vui lòng bỏ đánh dấu hoặc thực hiện xong thao tác chèn")
            return

        base_name = os.path.splitext(os.path.basename(self._path_b))[0]
        default_name = f"{base_name}_Insert.pdf"
        start_dir = os.path.dirname(self._path_b) or ""

        while True:
            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu file kết quả",
                os.path.join(start_dir, default_name),
                "PDF Files (*.pdf)",
                options=QFileDialog.Option.DontConfirmOverwrite,
                # Tắt hộp thoại "Confirm Save As" mặc định của hệ điều hành — app đã
                # tự hỏi Ghi đè/Đổi tên khác/Hủy bằng QMessageBox style riêng ngay bên
                # dưới, giữ cả 2 sẽ hiện 2 lần hỏi liên tiếp cho cùng 1 việc.
            )
            if not save_path:
                return
            if not save_path.lower().endswith(".pdf"):
                save_path += ".pdf"

            if os.path.exists(save_path):
                choice = self._confirm_overwrite(save_path)
                if choice == "cancel":
                    return
                if choice == "rename":
                    start_dir = os.path.dirname(save_path)
                    default_name = os.path.basename(save_path)
                    continue
            break

        try:
            self._session.save(save_path)
        except FileLockedError as exc:
            self._show_error(str(exc))
            log_error(f"Lỗi khi lưu file Chèn: {exc}", exc)
            return
        except ValueError as exc:
            self._show_error(str(exc))
            return

        log_info(f"Đã lưu file Chèn: {save_path}")
        self._show_success(f"Đã lưu file thành công: {os.path.basename(save_path)}")

        # Tự động mở thư mục chứa file kết quả (giống hành vi đã có ở Tách file).
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(save_path)))

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