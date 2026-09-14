"""
Giao diện tính năng Tách File (Split) — GIAI ĐOẠN THIẾT KẾ UI THUẦN.

Bố cục 2 cột (A ~55% - B ~45%):
- Cột A: A1 khối chọn file, A3 khung chứa tiêu đề + đường ngăn cách + lưới thumbnail.
- Cột B: Khung chứa tiêu đề + đường ngăn cách + preview cuộn liên tục nhiều trang.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent
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

# Số trang giả dùng để dựng lưới xem trước khi chưa có pdf_core.py thật.
_MOCK_PAGE_COUNT = 9
_GRID_COLUMNS = 3
_THUMB_SIZE = 128
_FLAG_BAR_WIDTH = 6

_PREVIEW_PAGE_WIDTH = 340
_PREVIEW_PAGE_HEIGHT = 460

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
# A3 — 1 ô trong lưới thumbnail: thumbnail giả + vạch cờ đỏ bên phải
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
        number_label = QLabel(str(page_number))
        number_label.setAlignment(Qt.AlignCenter)
        number_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 26px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(number_label)
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
    """Giao diện tính năng Tách File — GIAI ĐOẠN UI THUẦN."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._selected_file_path: Optional[str] = None
        self._thumbnails: List[_PageThumbnail] = []
        self._preview_pages: Dict[int, QFrame] = {}

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

        # --- Khung bao toàn bộ khu vực A3 (Header tiêu đề + Đường ngăn cách + Lưới Thumbnail) ---
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

        # Header Tiêu đề A3 trong khung bao (Icon + Text)
        a3_header = QWidget()
        a3_header_layout = QHBoxLayout(a3_header)
        a3_header_layout.setContentsMargins(16, 12, 16, 12)
        a3_header_layout.setSpacing(8)

        a3_icon = QLabel()
        a3_icon.setPixmap(qta.icon("mdi6.file-document-outline", color=COLOR_ACCENT).pixmap(QSize(18, 18)))
        a3_icon.setStyleSheet("background: transparent; border: none;")
        a3_header_layout.addWidget(a3_icon)

        # TODO Giai đoạn 2: Cập nhật tên file thực tế vào self.a3_title_label khi mở file thành công
        self.a3_title_label = QLabel('File được chọn: ""')
        self.a3_title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        a3_header_layout.addWidget(self.a3_title_label, stretch=1)
        a3_box_layout.addWidget(a3_header)

        # Đường ngăn cách giữa tiêu đề và nội dung lưới
        a3_divider = QFrame()
        a3_divider.setFrameShape(QFrame.HLine)
        a3_divider.setFrameShadow(QFrame.Sunken)
        a3_divider.setStyleSheet(f"background-color: {COLOR_BORDER}; border: none; max-height: 1px;")
        a3_box_layout.addWidget(a3_divider)

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
        self._build_mock_grid()
        self.preview_scroll.setWidget(grid_container)
        a3_box_layout.addWidget(self.preview_scroll, stretch=1)

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

        # Nhãn "Tùy chỉnh" + Checkbox — thứ tự: Tùy chỉnh - Checkbox
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

        # Khung bao toàn bộ Cột B (Header tiêu đề + Đường ngăn cách + Preview cuộn)
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

        # Header Tiêu đề Cột B trong khung bao (Icon + Text)
        b_header = QWidget()
        b_header_layout = QHBoxLayout(b_header)
        b_header_layout.setContentsMargins(16, 12, 16, 12)
        b_header_layout.setSpacing(8)

        b_icon = QLabel()
        b_icon.setPixmap(qta.icon("mdi6.eye-outline", color=COLOR_ACCENT).pixmap(QSize(18, 18)))
        b_icon.setStyleSheet("background: transparent; border: none;")
        b_header_layout.addWidget(b_icon)

        # TODO Giai đoạn 2: Cập nhật tên file thực tế vào self.preview_title_label khi mở file thành công
        self.preview_title_label = QLabel('Xem trước: ""')
        self.preview_title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        b_header_layout.addWidget(self.preview_title_label, stretch=1)
        preview_box_layout.addWidget(b_header)

        # Đường ngăn cách giữa tiêu đề và vùng Preview bên dưới
        b_divider = QFrame()
        b_divider.setFrameShape(QFrame.HLine)
        b_divider.setFrameShadow(QFrame.Sunken)
        b_divider.setStyleSheet(f"background-color: {COLOR_BORDER}; border: none; max-height: 1px;")
        preview_box_layout.addWidget(b_divider)

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
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(16, 16, 16, 16)
        preview_layout.setSpacing(16)
        preview_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self._build_mock_preview_pages(preview_layout)
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

        # Mặc định chọn trang 1
        self._select_page(1)

    # ------------------------------------------------------------------
    # Xây lưới thumbnail giả (A3)
    # ------------------------------------------------------------------
    def _build_mock_grid(self) -> None:
        for i in range(_MOCK_PAGE_COUNT):
            page_number = i + 1
            row, col = divmod(i, _GRID_COLUMNS)

            thumb = _PageThumbnail(page_number)
            thumb.clicked.connect(self._on_thumbnail_clicked)
            self.thumb_grid.addWidget(thumb, row, col)
            self._thumbnails.append(thumb)

    # ------------------------------------------------------------------
    # Xây các trang Preview giả — xếp dọc liên tục để cuộn (Cột B)
    # ------------------------------------------------------------------
    def _build_mock_preview_pages(self, layout: QVBoxLayout) -> None:
        for i in range(_MOCK_PAGE_COUNT):
            page_number = i + 1
            page_frame = QFrame()
            page_frame.setFixedSize(_PREVIEW_PAGE_WIDTH, _PREVIEW_PAGE_HEIGHT)
            page_frame.setStyleSheet(
                f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
            )
            page_layout = QVBoxLayout(page_frame)
            page_layout.setAlignment(Qt.AlignCenter)
            number_label = QLabel(str(page_number))
            number_label.setAlignment(Qt.AlignCenter)
            number_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 48px; font-weight: 700; "
                "background: transparent; border: none;"
            )
            page_layout.addWidget(number_label)

            layout.addWidget(page_frame, alignment=Qt.AlignHCenter)
            self._preview_pages[page_number] = page_frame

    # ------------------------------------------------------------------
    # Sự kiện
    # ------------------------------------------------------------------
    def _on_file_selected(self, path: str) -> None:
        self._selected_file_path = path
        self._select_page(1)
        self._hide_result()

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
            thumb = self._thumbnails[page_number - 1]
            thumb.set_flagged(not thumb.is_flagged)

    def _on_clear_clicked(self) -> None:
        self._selected_file_path = None
        self.custom_checkbox.setChecked(False)
        self.pages_per_file_spin.setValue(1)
        for thumb in self._thumbnails:
            thumb.reset_flag()
        self._select_page(1)
        self._hide_result()

    def _select_page(self, page_number: int) -> None:
        for thumb in self._thumbnails:
            thumb.set_selected(thumb.page_number == page_number)
        target = self._preview_pages.get(page_number)
        if target is not None:
            self.preview_scroll_b.ensureWidgetVisible(target, 0, 0)

    def _on_split_clicked(self) -> None:
        if not self._selected_file_path:
            self._show_error("Vui lòng chọn file PDF trước khi tách.")
            return

        if not self.custom_checkbox.isChecked():
            n = self.pages_per_file_spin.value()
            if n < 1:
                self._show_error("Số trang mỗi file phải lớn hơn hoặc bằng 1.")
                return
            self._show_success(f"[Demo giao diện] Sẽ tách theo {n} trang/file — chưa xử lý PDF thật.")
        else:
            flagged = [t.page_number for t in self._thumbnails if t.is_flagged]
            if not flagged:
                self._show_error("Vui lòng đặt ít nhất 1 cờ trước khi tách.")
                return
            self._show_success(f"[Demo giao diện] Sẽ tách tại các cờ sau trang: {flagged} — chưa xử lý PDF thật.")

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