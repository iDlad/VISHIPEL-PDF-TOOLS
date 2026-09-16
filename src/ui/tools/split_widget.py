"""
Giao diện tính năng Tách File (Split) — ĐÃ NỐI LOGIC THẬT với pdf_core.py.

Bố cục 2 cột (A ~55% - B ~45%):
- Cột A: A1 khối chọn file, A3 khung chứa tiêu đề + lưới thumbnail (render thật).
- Cột B: Khung chứa tiêu đề + preview cuộn liên tục nhiều trang (render thật).

Render thumbnail/preview chạy nền qua QThread (_PageRenderWorker) để không đơ UI
khi file nhiều trang — cập nhật ảnh từng trang một ngay khi render xong (progressive).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QThread, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QSpinBox,
    QScrollArea,
    QFrame,
    QFileDialog,
    QMessageBox,
    QStackedWidget,
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
    CorruptedFileError,
    PasswordProtectedError,
    FileLockedError,
    PageInfo,
    PageRenderer,
    list_page_infos,
    split_by_fixed_count,
    split_by_flags,
)
from src.logger import log_info, log_error

_GRID_COLUMNS = 3
_THUMB_SIZE = 128
_FLAG_BAR_WIDTH = 6

# Kích thước render thực tế lớn hơn kích thước hiển thị để ảnh nét, đặc biệt trên
# màn hình có DPI cao — sau đó co lại vừa khung hiển thị (KeepAspectRatio).
_THUMB_RENDER_WIDTH = 220
_PREVIEW_RENDER_WIDTH = 700

_PREVIEW_PAGE_WIDTH = 340
_PREVIEW_PAGE_HEIGHT_DEFAULT = 460

_CHECKBOX_SIZE = 22
_CHECKBOX_RADIUS = round(CORNER_RADIUS * _CHECKBOX_SIZE / CONTROL_HEIGHT)

_DROPZONE_ICON_BOX = 56

_SPIN_BOX_WIDTH = 84
_SPIN_ARROW_WIDTH = 22


def _spin_arrow_style(is_top: bool) -> str:
    radius = (
        f"border-top-right-radius: {CORNER_RADIUS - 2}px;"
        if is_top
        else f"border-bottom-right-radius: {CORNER_RADIUS - 2}px;"
    )
    return f"""
        QToolButton {{
            background-color: transparent;
            border: none;
            border-left: 1px solid {COLOR_BORDER};
            {radius}
        }}
        QToolButton:hover {{ background-color: {COLOR_ACCENT_LIGHT}; }}
        QToolButton:pressed {{ background-color: {COLOR_ACCENT}; }}
        """


_SCROLLBAR_QSS = f"""
    QScrollBar:vertical {{
        background: transparent;
        width: 9px;
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


# ----------------------------------------------------------------------
# Worker nền: render thumbnail + preview cho từng trang, không đụng UI thread
# ----------------------------------------------------------------------
class _PageRenderWorker(QThread):
    """Render tuần tự từng trang (thumbnail nhỏ cho Cột A + ảnh lớn cho Cột B),
    phát tín hiệu ngay khi xong 1 trang để UI cập nhật dần (progressive), không
    chờ render hết toàn bộ file mới hiển thị gì đó."""

    page_rendered = Signal(int, bytes, bytes)  # page_index (0-based), thumb_png, preview_png
    render_error = Signal(str)

    def __init__(self, path: str, page_count: int, renderer: PageRenderer,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._path = path
        self._page_count = page_count
        self._renderer = renderer
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        try:
            for i in range(self._page_count):
                if self._cancelled:
                    return
                thumb_bytes = self._renderer.render_thumbnail(
                    self._path, i, max_width=_THUMB_RENDER_WIDTH
                )
                if self._cancelled:
                    return
                preview_bytes = self._renderer.render_page_detail(
                    self._path, i, target_width=_PREVIEW_RENDER_WIDTH
                )
                if self._cancelled:
                    return
                self.page_rendered.emit(i, thumb_bytes, preview_bytes)
        except Exception as exc:  # không để lỗi render làm crash thread ngầm
            self.render_error.emit(str(exc))


# ----------------------------------------------------------------------
# A3 — 1 ô trong lưới thumbnail: số trang (lúc đang tải) → ảnh thật (khi render xong)
#      + vạch cờ đỏ bên phải
# ----------------------------------------------------------------------
class _PageThumbnail(QWidget):
    clicked = Signal(int)

    def __init__(self, page_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.is_selected = False
        self.is_flagged = False
        self.setCursor(Qt.PointingHandCursor)

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        self.card = QFrame()
        self.card.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._apply_card_style()

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)

        # Số trang — hiển thị khi chưa render xong (trạng thái "đang tải")
        self.number_label = QLabel(str(page_number))
        self.number_label.setAlignment(Qt.AlignCenter)
        self.number_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 26px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(self.number_label)

        # Ảnh thumbnail thật — ẩn cho tới khi render xong
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        self.image_label.hide()
        card_layout.addWidget(self.image_label)

        row_layout.addWidget(self.card)

        self.flag_bar = QFrame()
        self.flag_bar.setFixedWidth(_FLAG_BAR_WIDTH)
        self.flag_bar.setFixedHeight(_THUMB_SIZE)
        self._apply_flag_style()
        row_layout.addWidget(self.flag_bar)

    def _apply_card_style(self) -> None:
        if self.is_selected:
            border = f"2px solid {COLOR_ACCENT}"
            background = COLOR_ACCENT_LIGHT
        else:
            border = f"1px solid {COLOR_BORDER}"
            background = "white"
        self.card.setStyleSheet(
            f"QFrame {{ background-color: {background}; border: {border}; "
            f"border-radius: {CORNER_RADIUS}px; }}"
        )

    def _apply_flag_style(self) -> None:
        color = COLOR_ERROR if self.is_flagged else "transparent"
        self.flag_bar.setStyleSheet(f"background-color: {color}; border-radius: 2px;")

    def set_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self._apply_card_style()

    def set_flagged(self, flagged: bool) -> None:
        self.is_flagged = flagged
        self._apply_flag_style()

    def reset_flag(self) -> None:
        self.set_flagged(False)

    def set_thumbnail_image(self, png_bytes: bytes) -> None:
        """Gắn ảnh thumbnail thật đã render — thay thế số trang đang hiển thị tạm."""
        pixmap = QPixmap()
        if not pixmap.loadFromData(png_bytes):
            return
        scaled = pixmap.scaled(
            _THUMB_SIZE - 12, _THUMB_SIZE - 12, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)
        self.image_label.show()
        self.number_label.hide()

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self.page_number)


# ----------------------------------------------------------------------
# Checkbox tùy chỉnh
# ----------------------------------------------------------------------
class _CheckToggle(QToolButton):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(_CHECKBOX_SIZE, _CHECKBOX_SIZE)
        self.toggled.connect(self._on_toggled)
        self._on_toggled(False)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.setIcon(qta.icon("mdi6.check-bold", color="white"))
            self.setStyleSheet(
                f"""
                QToolButton {{
                    background-color: {COLOR_ACCENT};
                    border: 1px solid {COLOR_ACCENT};
                    border-radius: {_CHECKBOX_RADIUS}px;
                }}
                """
            )
        else:
            self.setIcon(qta.icon("mdi6.check-bold", color="transparent"))
            self.setStyleSheet(
                f"""
                QToolButton {{
                    background-color: white;
                    border: 1.5px solid {COLOR_BORDER_STRONG};
                    border-radius: {_CHECKBOX_RADIUS}px;
                }}
                """
            )


# ----------------------------------------------------------------------
# A1 — Khối chọn file
# ----------------------------------------------------------------------
class _DropZone(QFrame):
    file_selected = Signal(str)

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
            self.file_selected.emit(path)

    def mousePressEvent(self, event) -> None:
        self._open_file_dialog()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].toLocalFile().lower().endswith(".pdf"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if path.lower().endswith(".pdf"):
                self.file_selected.emit(path)


# ----------------------------------------------------------------------
# Widget chính
# ----------------------------------------------------------------------
class SplitFeatureWidget(QWidget):
    """Giao diện tính năng Tách File — ĐÃ NỐI LOGIC THẬT (pdf_core.py)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._selected_file_path: Optional[str] = None
        self._page_infos: List[PageInfo] = []
        self._thumbnails: List[_PageThumbnail] = []
        self._preview_pages: Dict[int, QFrame] = {}
        self._renderer = PageRenderer()
        self._render_worker: Optional[_PageRenderWorker] = None

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # ================= CỘT A (~55%) =================
        column_a = QVBoxLayout()
        column_a.setSpacing(14)

        # --- A1 ---
        self.drop_zone = _DropZone()
        self.drop_zone.file_selected.connect(self._on_file_selected)
        column_a.addWidget(self.drop_zone)

        # --- Khung bao toàn bộ khu vực A3 (Header tiêu đề + Lưới Thumbnail) ---
        a3_container = QFrame()
        a3_container.setStyleSheet(
            f"""
            QFrame#a3_container {{
                background-color: transparent;
                border: 1.5px solid {COLOR_BORDER};
                border-radius: 14px;
            }}
            """
        )
        a3_container.setObjectName("a3_container")
        a3_box_layout = QVBoxLayout(a3_container)
        a3_box_layout.setContentsMargins(0, 0, 0, 0)
        a3_box_layout.setSpacing(0)

        # Header Tiêu đề A3 trong khung bao (Icon đen + Text)
        a3_header = QWidget()
        a3_header_layout = QHBoxLayout(a3_header)
        a3_header_layout.setContentsMargins(16, 12, 16, 12)
        a3_header_layout.setSpacing(8)

        a3_icon = QLabel()
        a3_icon.setPixmap(qta.icon("mdi6.file-document-outline", color="black").pixmap(QSize(18, 18)))
        a3_icon.setStyleSheet("background: transparent; border: none;")
        a3_header_layout.addWidget(a3_icon)

        self.a3_title_label = QLabel('File được chọn: ""')
        self.a3_title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        a3_header_layout.addWidget(self.a3_title_label, stretch=1)
        a3_box_layout.addWidget(a3_header)

        # A3: khung lưới thumbnail
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet(
            f"""
            QScrollArea {{ background: transparent; border: none; }}
            {_SCROLLBAR_QSS}
            """
        )
        self.preview_scroll.setMinimumHeight(320)

        grid_container = QWidget()
        grid_container.setStyleSheet("background: transparent;")
        self.thumb_grid = QGridLayout(grid_container)
        self.thumb_grid.setContentsMargins(28, 28, 28, 28)
        self.thumb_grid.setHorizontalSpacing(22)
        self.thumb_grid.setVerticalSpacing(22)
        self.preview_scroll.setWidget(grid_container)

        # Nhãn trạng thái rỗng — hiển thị khi chưa chọn file nào
        self.empty_state_label = QLabel("Chưa có file nào được chọn.\nVui lòng chọn file PDF để bắt đầu.")
        self.empty_state_label.setAlignment(Qt.AlignCenter)
        self.empty_state_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; background: transparent; border: none;"
        )

        # QStackedWidget thay vì setVisible() qua lại: 2 trang (rỗng / lưới thumbnail)
        # luôn chiếm đúng 1 vùng kích thước cố định ngay dưới header — nhờ đó header
        # "File được chọn" không bao giờ bị đẩy lệch vị trí khi chuyển trạng thái.
        self.a3_content_stack = QStackedWidget()
        self.a3_content_stack.addWidget(self.empty_state_label)
        self.a3_content_stack.addWidget(self.preview_scroll)
        a3_box_layout.addWidget(self.a3_content_stack, stretch=1)

        column_a.addWidget(a3_container, stretch=1)

        # --- Hàng dưới cùng: Nhập số trang + Tùy chỉnh + Clear + Tách File ---
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.setContentsMargins(0, 0, 0, 0)

        pages_label = QLabel("Nhập số trang:")
        pages_label.setFixedHeight(CONTROL_HEIGHT)
        pages_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        pages_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        bottom_row.addWidget(pages_label)

        spin_container = QFrame()
        spin_container.setFixedHeight(CONTROL_HEIGHT)
        spin_container.setFixedWidth(_SPIN_BOX_WIDTH)
        spin_container.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
            }}
            """
        )
        spin_row = QHBoxLayout(spin_container)
        spin_row.setContentsMargins(10, 0, 0, 0)
        spin_row.setSpacing(0)

        self.pages_per_file_spin = QSpinBox()
        self.pages_per_file_spin.setButtonSymbols(QSpinBox.NoButtons)
        self.pages_per_file_spin.setFrame(False)
        self.pages_per_file_spin.setRange(1, 9999)
        self.pages_per_file_spin.setValue(1)
        self.pages_per_file_spin.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.pages_per_file_spin.setStyleSheet(
            f"""
            QSpinBox {{
                background: transparent;
                border: none;
                color: {COLOR_TEXT_PRIMARY};
                font-size: 13px;
                font-weight: 600;
            }}
            """
        )
        spin_row.addWidget(self.pages_per_file_spin, stretch=1)

        arrows_col = QVBoxLayout()
        arrows_col.setContentsMargins(0, 0, 0, 0)
        arrows_col.setSpacing(0)

        self.spin_up_btn = QToolButton()
        self.spin_up_btn.setCursor(Qt.PointingHandCursor)
        self.spin_up_btn.setIcon(qta.icon("mdi6.chevron-up", color=COLOR_TEXT_SECONDARY))
        self.spin_up_btn.setIconSize(QSize(13, 13))
        self.spin_up_btn.setFixedSize(_SPIN_ARROW_WIDTH, CONTROL_HEIGHT // 2)
        self.spin_up_btn.setStyleSheet(_spin_arrow_style(is_top=True))
        self.spin_up_btn.clicked.connect(self.pages_per_file_spin.stepUp)
        arrows_col.addWidget(self.spin_up_btn)

        self.spin_down_btn = QToolButton()
        self.spin_down_btn.setCursor(Qt.PointingHandCursor)
        self.spin_down_btn.setIcon(qta.icon("mdi6.chevron-down", color=COLOR_TEXT_SECONDARY))
        self.spin_down_btn.setIconSize(QSize(13, 13))
        self.spin_down_btn.setFixedSize(_SPIN_ARROW_WIDTH, CONTROL_HEIGHT - CONTROL_HEIGHT // 2)
        self.spin_down_btn.setStyleSheet(_spin_arrow_style(is_top=False))
        self.spin_down_btn.clicked.connect(self.pages_per_file_spin.stepDown)
        arrows_col.addWidget(self.spin_down_btn)

        spin_row.addLayout(arrows_col)
        bottom_row.addWidget(spin_container)

        # Nhãn "Tùy chỉnh" + Checkbox
        custom_group = QHBoxLayout()
        custom_group.setContentsMargins(0, 0, 0, 0)
        custom_group.setSpacing(8)

        custom_label = QLabel("Tùy chỉnh")
        custom_label.setFixedHeight(CONTROL_HEIGHT)
        custom_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        custom_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        custom_group.addWidget(custom_label)

        self.custom_checkbox = _CheckToggle()
        checkbox_container = QWidget()
        checkbox_container.setFixedHeight(CONTROL_HEIGHT)
        checkbox_layout = QHBoxLayout(checkbox_container)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setAlignment(Qt.AlignCenter)
        checkbox_layout.addWidget(self.custom_checkbox)
        self.custom_checkbox.toggled.connect(self._on_custom_toggled)
        custom_group.addWidget(checkbox_container)

        custom_group_widget = QWidget()
        custom_group_widget.setLayout(custom_group)
        bottom_row.addWidget(custom_group_widget)

        bottom_row.addStretch()

        self.clear_button = QPushButton("Clear")
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setFixedHeight(CONTROL_HEIGHT)
        self.clear_button.setMinimumWidth(85)
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

        self.split_button = QPushButton(" Tách File")
        self.split_button.setIcon(qta.icon("mdi6.content-cut", color="white"))
        self.split_button.setCursor(Qt.PointingHandCursor)
        self.split_button.setFixedHeight(CONTROL_HEIGHT)
        self.split_button.setMinimumWidth(120)
        self.split_button.setStyleSheet(
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
        self.split_button.clicked.connect(self._on_split_clicked)
        bottom_row.addWidget(self.split_button)

        column_a.addLayout(bottom_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        column_a.addWidget(self.result_label)

        # ================= CỘT B (~40%) — Preview cuộn liên tục =================
        column_b = QVBoxLayout()
        column_b.setSpacing(0)

        # Khung bao toàn bộ Cột B (Header tiêu đề + Preview cuộn)
        preview_box_container = QFrame()
        preview_box_container.setStyleSheet(
            f"""
            QFrame#preview_box_container {{
                background-color: white;
                border: 1.5px solid {COLOR_BORDER};
                border-radius: 14px;
            }}
            """
        )
        preview_box_container.setObjectName("preview_box_container")
        preview_box_layout = QVBoxLayout(preview_box_container)
        preview_box_layout.setContentsMargins(0, 0, 0, 0)
        preview_box_layout.setSpacing(0)

        # Header Tiêu đề Cột B trong khung bao (Icon đen + Text)
        b_header = QWidget()
        b_header_layout = QHBoxLayout(b_header)
        b_header_layout.setContentsMargins(16, 12, 16, 12)
        b_header_layout.setSpacing(8)

        b_icon = QLabel()
        b_icon.setPixmap(qta.icon("mdi6.eye-outline", color="black").pixmap(QSize(18, 18)))
        b_icon.setStyleSheet("background: transparent; border: none;")
        b_header_layout.addWidget(b_icon)

        self.preview_title_label = QLabel('Xem trước: ""')
        self.preview_title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        b_header_layout.addWidget(self.preview_title_label, stretch=1)
        preview_box_layout.addWidget(b_header)

        # Khung Preview cuộn dọc
        self.preview_scroll_b = QScrollArea()
        self.preview_scroll_b.setWidgetResizable(True)
        self.preview_scroll_b.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: transparent;
                border: none;
            }}
            {_SCROLLBAR_QSS}
            """
        )

        preview_container = QWidget()
        preview_container.setStyleSheet("background: transparent;")
        self.preview_layout = QVBoxLayout(preview_container)
        self.preview_layout.setContentsMargins(16, 16, 16, 16)
        self.preview_layout.setSpacing(16)
        self.preview_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.preview_scroll_b.setWidget(preview_container)

        preview_box_layout.addWidget(self.preview_scroll_b, stretch=1)
        column_b.addWidget(preview_box_container, stretch=1)

        # Ghép 2 cột theo tỉ lệ 55/45
        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, stretch=55)
        root_layout.addWidget(column_b_widget, stretch=45)

        self._update_empty_state()

    # ------------------------------------------------------------------
    # Trạng thái rỗng (chưa chọn file)
    # ------------------------------------------------------------------
    def _update_empty_state(self) -> None:
        has_file = self._selected_file_path is not None
        target = self.preview_scroll if has_file else self.empty_state_label
        self.a3_content_stack.setCurrentWidget(target)

    # ------------------------------------------------------------------
    # Dựng / dọn lưới thumbnail (Cột A) + dải preview (Cột B) theo file thật
    # ------------------------------------------------------------------
    def _clear_grid_and_preview(self) -> None:
        for thumb in self._thumbnails:
            self.thumb_grid.removeWidget(thumb)
            thumb.deleteLater()
        self._thumbnails.clear()

        for frame in self._preview_pages.values():
            self.preview_layout.removeWidget(frame)
            frame.deleteLater()
        self._preview_pages.clear()

    def _build_real_grid(self, page_infos: List[PageInfo]) -> None:
        for i in range(len(page_infos)):
            page_number = i + 1
            row, col = divmod(i, _GRID_COLUMNS)
            thumb = _PageThumbnail(page_number)
            thumb.clicked.connect(self._on_thumbnail_clicked)
            self.thumb_grid.addWidget(thumb, row, col)
            self._thumbnails.append(thumb)

    def _create_preview_frame(self, page_number: int, info: PageInfo) -> QFrame:
        height = _PREVIEW_PAGE_HEIGHT_DEFAULT
        if info.width and info.height:
            height = round(_PREVIEW_PAGE_WIDTH * (info.height / info.width))

        frame = QFrame()
        frame.setFixedSize(_PREVIEW_PAGE_WIDTH, height)
        frame.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setAlignment(Qt.AlignCenter)

        number_label = QLabel(str(page_number))
        number_label.setAlignment(Qt.AlignCenter)
        number_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 48px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        frame_layout.addWidget(number_label)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setStyleSheet("background: transparent; border: none;")
        image_label.hide()
        frame_layout.addWidget(image_label)

        # Gắn tham chiếu để cập nhật ảnh sau khi render xong (xem _set_preview_frame_image)
        frame.number_label = number_label
        frame.image_label = image_label
        return frame

    def _build_real_preview(self, page_infos: List[PageInfo]) -> None:
        for i, info in enumerate(page_infos):
            page_number = i + 1
            frame = self._create_preview_frame(page_number, info)
            self.preview_layout.addWidget(frame, alignment=Qt.AlignHCenter)
            self._preview_pages[page_number] = frame

    def _set_preview_frame_image(self, frame: QFrame, png_bytes: bytes) -> None:
        pixmap = QPixmap()
        if not pixmap.loadFromData(png_bytes):
            return
        scaled = pixmap.scaled(
            frame.width() - 4, frame.height() - 4, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        frame.image_label.setPixmap(scaled)
        frame.image_label.show()
        frame.number_label.hide()

    # ------------------------------------------------------------------
    # Render nền (QThread)
    # ------------------------------------------------------------------
    def _cancel_render_worker(self) -> None:
        if self._render_worker is not None:
            self._render_worker.page_rendered.disconnect(self._on_page_rendered)
            self._render_worker.render_error.disconnect(self._on_render_error)
            self._render_worker.cancel()
            self._render_worker.wait()
            self._render_worker = None

    def _start_render_worker(self, path: str, page_count: int) -> None:
        worker = _PageRenderWorker(path, page_count, self._renderer, parent=self)
        worker.page_rendered.connect(self._on_page_rendered)
        worker.render_error.connect(self._on_render_error)
        self._render_worker = worker
        worker.start()

    def _on_page_rendered(self, page_index: int, thumb_bytes: bytes, preview_bytes: bytes) -> None:
        if page_index < len(self._thumbnails):
            self._thumbnails[page_index].set_thumbnail_image(thumb_bytes)

        page_number = page_index + 1
        frame = self._preview_pages.get(page_number)
        if frame is not None:
            self._set_preview_frame_image(frame, preview_bytes)

    def _on_render_error(self, message: str) -> None:
        log_error(f"Lỗi khi render trang xem trước: {message}")
        self._show_error("Có lỗi khi hiển thị một số trang xem trước (xem app.log để biết chi tiết).")

    # ------------------------------------------------------------------
    # Sự kiện
    # ------------------------------------------------------------------
    def _on_file_selected(self, path: str) -> None:
        self._cancel_render_worker()
        self._hide_result()

        try:
            page_infos = list_page_infos(path)
        except PasswordProtectedError:
            self._show_error("File có mật khẩu, chưa hỗ trợ mở file loại này.")
            return
        except CorruptedFileError:
            self._show_error("Không thể đọc file, file có thể bị hỏng.")
            return
        except Exception as exc:  # phòng lỗi phát sinh ngoài dự kiến
            log_error("Lỗi không xác định khi mở file trong tính năng Tách file", exc)
            self._show_error("Đã xảy ra lỗi không xác định khi mở file.")
            return

        self._selected_file_path = path
        self._page_infos = page_infos

        self._clear_grid_and_preview()
        self._build_real_grid(page_infos)
        self._build_real_preview(page_infos)
        self._update_empty_state()

        filename = os.path.basename(path)
        self.a3_title_label.setText(f'File được chọn: "{filename}"')
        self.preview_title_label.setText(f'Xem trước: "{filename}"')

        self._select_page(1)
        self._start_render_worker(path, len(page_infos))

    def _on_custom_toggled(self, checked: bool) -> None:
        self.pages_per_file_spin.setDisabled(checked)
        self.spin_up_btn.setDisabled(checked)
        self.spin_down_btn.setDisabled(checked)
        if not checked:
            for thumb in self._thumbnails:
                thumb.reset_flag()

    def _on_thumbnail_clicked(self, page_number: int) -> None:
        self._select_page(page_number)
        if self.custom_checkbox.isChecked():
            # Trang cuối cùng không có "ranh giới sau nó" trong file nên bỏ qua,
            # tránh tạo cờ không hợp lệ khi gọi pdf_core.split_by_flags.
            if page_number < len(self._thumbnails):
                thumb = self._thumbnails[page_number - 1]
                thumb.set_flagged(not thumb.is_flagged)

    def _on_clear_clicked(self) -> None:
        self._cancel_render_worker()
        self._selected_file_path = None
        self._page_infos = []
        self.custom_checkbox.setChecked(False)
        self.pages_per_file_spin.setValue(1)
        self._clear_grid_and_preview()
        self._update_empty_state()
        self.a3_title_label.setText('File được chọn: ""')
        self.preview_title_label.setText('Xem trước: ""')
        self._hide_result()

    def _select_page(self, page_number: int) -> None:
        for thumb in self._thumbnails:
            thumb.set_selected(thumb.page_number == page_number)
        target = self._preview_pages.get(page_number)
        if target is not None:
            self.preview_scroll_b.ensureWidgetVisible(target, 0, 0)

    # ------------------------------------------------------------------
    # Tách file thật
    # ------------------------------------------------------------------
    @staticmethod
    def _compute_fixed_segments(total: int, pages_per_file: int) -> List[tuple]:
        """Dự đoán các đoạn (start, end) — PHẢI khớp logic split_by_fixed_count trong
        pdf_core.py. Dùng để: (1) biết trước sẽ có bao nhiêu file kết quả (từ đó suy ra
        danh sách tên PDF_Split_01, 02... để kiểm tra trùng tên trước khi ghi), và
        (2) validate dữ liệu phía UI. Việc tách file thật luôn do pdf_core thực hiện."""
        segments = []
        start = 0
        while start < total:
            end = min(start + pages_per_file, total) - 1
            segments.append((start, end))
            start = end + 1
        return segments

    @staticmethod
    def _compute_flag_segments(total: int, flag_positions: List[int]) -> List[tuple]:
        """Dự đoán các đoạn (start, end) — PHẢI khớp logic split_by_flags trong pdf_core.py."""
        boundaries = sorted(set(flag_positions))
        segments = []
        start = 0
        for b in boundaries:
            segments.append((start, b))
            start = b + 1
        segments.append((start, total - 1))
        return segments

    def _confirm_overwrite(self, duplicate_count: int) -> bool:
        """Hộp thoại xác nhận ghi đè khi phát hiện trùng tên file — style tường minh,
        không phụ thuộc theme toàn app (tránh bị chữ trắng-trên-trắng do QSS toàn cục)."""
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle("Trùng tên file")
        msg_box.setText(
            f"Đã có {duplicate_count} file trùng tên trong thư mục đã chọn.\n"
            "Bạn có muốn ghi đè tất cả không?"
        )
        msg_box.setStyleSheet(
            f"""
            QMessageBox {{
                background-color: white;
            }}
            QMessageBox QLabel {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 13px;
                background: transparent;
            }}
            QPushButton {{
                background-color: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 16px;
                min-width: 90px;
            }}
            QPushButton:hover {{
                background-color: #F3F4F6;
            }}
            """
        )
        btn_overwrite = msg_box.addButton("Ghi đè tất cả", QMessageBox.AcceptRole)
        btn_overwrite.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: white;
                border: none;
                border-radius: {CORNER_RADIUS}px;
                font-size: 13px;
                font-weight: 700;
                padding: 6px 16px;
                min-width: 90px;
            }}
            QPushButton:hover {{ background-color: #E28104; }}
            """
        )
        msg_box.addButton("Hủy", QMessageBox.RejectRole)
        msg_box.exec()
        return msg_box.clickedButton() == btn_overwrite

    def _on_split_clicked(self) -> None:
        if not self._selected_file_path:
            self._show_error("Vui lòng chọn file PDF trước khi tách.")
            return

        total = len(self._page_infos)
        base_name = os.path.splitext(os.path.basename(self._selected_file_path))[0]

        use_flags = self.custom_checkbox.isChecked()
        if not use_flags:
            n = self.pages_per_file_spin.value()
            if n < 1:
                self._show_error("Số trang mỗi file phải lớn hơn hoặc bằng 1.")
                return
            segments = self._compute_fixed_segments(total, n)
        else:
            flag_positions = sorted(
                t.page_number - 1 for t in self._thumbnails if t.is_flagged
            )
            if not flag_positions:
                self._show_error("Vui lòng đặt ít nhất 1 cờ trước khi tách.")
                return
            segments = self._compute_flag_segments(total, flag_positions)

        # Chọn thư mục lưu kết quả (Save As style) — tên file dùng mặc định pdf_core tự sinh
        output_dir = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu kết quả")
        if not output_dir:
            return  # người dùng hủy chọn thư mục

        # Tên file kết quả theo quy ước đã chốt: PDF_Split_01.pdf, PDF_Split_02.pdf...
        # (đánh số theo đúng thứ tự file sẽ được tạo ra — xem pdf_core._extract_pages_and_save)
        predicted_names = [f"PDF_Split_{i:02d}.pdf" for i in range(1, len(segments) + 1)]
        duplicates = [n for n in predicted_names if os.path.exists(os.path.join(output_dir, n))]
        if duplicates:
            if not self._confirm_overwrite(len(duplicates)):
                return

        try:
            if not use_flags:
                output_paths = split_by_fixed_count(
                    self._selected_file_path, n, output_dir, base_name
                )
            else:
                output_paths = split_by_flags(
                    self._selected_file_path, flag_positions, output_dir, base_name
                )
        except PasswordProtectedError:
            log_error(f"Tách file thất bại (file có mật khẩu): {self._selected_file_path}")
            self._show_error("File có mật khẩu, không thể xử lý.")
            return
        except CorruptedFileError:
            log_error(f"Tách file thất bại (file hỏng): {self._selected_file_path}")
            self._show_error("Không thể đọc file, file có thể bị hỏng.")
            return
        except FileLockedError:
            log_error(f"Tách file thất bại (file bị khóa khi ghi): {output_dir}")
            self._show_error(
                "File đang được sử dụng bởi chương trình khác, vui lòng đóng và thử lại."
            )
            return
        except ValueError as exc:
            log_error(f"Tách file thất bại (dữ liệu không hợp lệ): {exc}", exc)
            self._show_error(str(exc))
            return
        except Exception as exc:  # phòng lỗi phát sinh ngoài dự kiến
            log_error("Lỗi không xác định khi tách file", exc)
            self._show_error("Đã xảy ra lỗi không xác định khi tách file.")
            return

        log_info(
            f"Tách file thành công: '{self._selected_file_path}' -> {len(output_paths)} file "
            f"tại '{output_dir}'"
        )
        self._show_success(f"Đã tách thành công {len(output_paths)} file, lưu tại: {output_dir}")

        # Tự động mở thư mục lưu kết quả cho người dùng xem ngay
        QDesktopServices.openUrl(QUrl.fromLocalFile(output_dir))

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

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._cancel_render_worker()
        super().closeEvent(event)