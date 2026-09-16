"""
Giao diện tính năng Edit File — GIAI ĐOẠN THIẾT KẾ UI THUẦN (bố cục), theo khuôn mẫu split_widget.py.

Bố cục 2 cột (A ~55% - B ~45%), giữ nguyên tỉ lệ và cấu trúc khung của Split:
- Cột A: A1 khối chọn file (chỉ 1 file, giữ nguyên thiết kế Split) + A3 khung chứa tiêu đề
  + lưới thumbnail (giữ nguyên thiết kế lưới, KHÁC ở chỗ: chuột phải vào 1 trang mở menu
  "Xoay trái 90° / Xoay phải 90°").
- Hàng thao tác dưới cùng (KHÁC Split — bỏ "Nhập số trang" + spin box + "Tùy chỉnh"):
  Nhãn "Xóa" + checkbox → Undo → Clear → Lưu File (thay cho nút "Tách File").
- Cột B: khung preview cuộn liên tục nhiều trang — giữ nguyên thiết kế Split, không đổi.

LƯU Ý: đây là bước dựng BỐ CỤC theo yêu cầu của đại ca — hành vi chi tiết của checkbox "Xóa",
Undo, và 2 mục trong menu chuột phải hiện đang là MOCK (chưa nối pdf_core.py / undo_manager.py),
chờ đại ca mô tả thêm về thao tác rồi mới hoàn thiện logic thật.
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
    QMenu,
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

_CONTEXT_MENU_QSS = f"""
    QMenu {{
        background-color: white;
        border: 1.5px solid {COLOR_BORDER};
        border-radius: {CORNER_RADIUS}px;
        padding: 4px;
    }}
    QMenu::item {{
        padding: 6px 22px 6px 10px;
        border-radius: 6px;
        color: {COLOR_TEXT_PRIMARY};
        font-size: 13px;
        font-weight: 600;
    }}
    QMenu::item:selected {{
        background-color: {COLOR_ACCENT_LIGHT};
        color: {COLOR_TEXT_PRIMARY};
    }}
"""


# ----------------------------------------------------------------------
# A3 — 1 ô trong lưới thumbnail: thumbnail giấy + vạch cờ đỏ bên phải
# + menu chuột phải Xoay trái/phải (KHÁC Split: Split không có context menu).
# ----------------------------------------------------------------------
class _EditPageThumbnail(QWidget):
    clicked = Signal(int)
    rotate_requested = Signal(int, str)  # (page_number, "left" | "right")

    def __init__(self, page_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.is_selected = False
        self.is_flagged = False  # đang được đánh dấu để xóa (khi bật chế độ "Xóa")
        # TODO Giai đoạn 2/3: rotation hiện chỉ là badge hiển thị tạm; khi có
        # render_page_thumbnail() thật từ pdf_core.py, thay bằng xoay ảnh PNG thật.
        self.rotation = 0
        self.setCursor(Qt.PointingHandCursor)

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        self.card = QFrame()
        self.card.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._apply_card_style()

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 4)
        card_layout.setSpacing(0)

        self.number_label = QLabel(str(page_number))
        self.number_label.setAlignment(Qt.AlignCenter)
        self.number_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 26px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(self.number_label, stretch=1)

        # Badge góc xoay — chỉ hiện chữ khi trang đã bị xoay (VD "90°", "270°").
        self.rotation_badge = QLabel("")
        self.rotation_badge.setAlignment(Qt.AlignCenter)
        self.rotation_badge.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-size: 11px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(self.rotation_badge)

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

    def apply_rotation(self, direction: str) -> None:
        delta = 90 if direction == "right" else -90
        self.rotation = (self.rotation + delta) % 360
        self.rotation_badge.setText(f"{self.rotation}°" if self.rotation else "")

    def reset_rotation(self) -> None:
        self.rotation = 0
        self.rotation_badge.setText("")

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.page_number)

    def contextMenuEvent(self, event) -> None:
        menu = QMenu(self)
        menu.setStyleSheet(_CONTEXT_MENU_QSS)
        rotate_left_action = menu.addAction(
            qta.icon("mdi6.rotate-left", color=COLOR_TEXT_PRIMARY), "Xoay trái 90°"
        )
        rotate_right_action = menu.addAction(
            qta.icon("mdi6.rotate-right", color=COLOR_TEXT_PRIMARY), "Xoay phải 90°"
        )
        chosen = menu.exec(event.globalPos())
        if chosen == rotate_left_action:
            self.rotate_requested.emit(self.page_number, "left")
        elif chosen == rotate_right_action:
            self.rotate_requested.emit(self.page_number, "right")


# ----------------------------------------------------------------------
# Checkbox tùy chỉnh (giữ nguyên style từ Split)
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
# A1 — Khối chọn file (giữ nguyên thiết kế Split — chỉ 1 file)
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
class EditFeatureWidget(QWidget):
    """Giao diện tính năng Edit File — GIAI ĐOẠN BỐ CỤC (UI THUẦN, chưa nối logic thật)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._selected_file_path: Optional[str] = None
        self._thumbnails: List[_EditPageThumbnail] = []
        self._preview_pages: Dict[int, QFrame] = {}

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # ================= CỘT A (~55%) =================
        column_a = QVBoxLayout()
        column_a.setSpacing(14)

        # --- A1: chọn file (giữ nguyên Split) ---
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
        a3_icon.setPixmap(qta.icon("mdi6.file-document-edit-outline", color="black").pixmap(QSize(18, 18)))
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

        # --- Hàng dưới cùng: Nhãn "Xóa" + checkbox → Undo → Clear → Lưu File ---
        # (KHÁC Split: bỏ hẳn "Nhập số trang" + spin box + "Tùy chỉnh")
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.setContentsMargins(0, 0, 0, 0)

        delete_label = QLabel("Xóa")
        delete_label.setFixedHeight(CONTROL_HEIGHT)
        delete_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        delete_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        bottom_row.addWidget(delete_label)

        self.delete_checkbox = _CheckToggle()
        checkbox_container = QWidget()
        checkbox_container.setFixedHeight(CONTROL_HEIGHT)
        checkbox_layout = QHBoxLayout(checkbox_container)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setAlignment(Qt.AlignCenter)
        checkbox_layout.addWidget(self.delete_checkbox)
        # TODO: hành vi chi tiết của checkbox "Xóa" (bật/tắt chế độ đánh dấu trang trên
        # thumbnail) chờ đại ca mô tả thêm — hiện đang tạm nối giống cơ chế đặt cờ của Split.
        self.delete_checkbox.toggled.connect(self._on_delete_mode_toggled)
        bottom_row.addWidget(checkbox_container)

        bottom_row.addStretch()

        self.undo_button = QPushButton(" Undo")
        self.undo_button.setIcon(qta.icon("mdi6.undo-variant", color=COLOR_TEXT_PRIMARY))
        self.undo_button.setCursor(Qt.PointingHandCursor)
        self.undo_button.setFixedHeight(CONTROL_HEIGHT)
        self.undo_button.setMinimumWidth(100)
        self.undo_button.setStyleSheet(
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
        # TODO Giai đoạn 2/3: nối với undo_manager.py — hiện là mock.
        self.undo_button.clicked.connect(self._on_undo_clicked)
        bottom_row.addWidget(self.undo_button)

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

        self.save_button = QPushButton(" Lưu File")
        self.save_button.setIcon(qta.icon("mdi6.content-save-outline", color="white"))
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.setFixedHeight(CONTROL_HEIGHT)
        self.save_button.setMinimumWidth(120)
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

        column_a.addLayout(bottom_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        column_a.addWidget(self.result_label)

        # ================= CỘT B (~45%) — Preview cuộn liên tục (giữ nguyên Split) =================
        column_b = QVBoxLayout()
        column_b.setSpacing(0)

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

        b_header = QWidget()
        b_header_layout = QHBoxLayout(b_header)
        b_header_layout.setContentsMargins(16, 12, 16, 12)
        b_header_layout.setSpacing(8)

        b_icon = QLabel()
        b_icon.setPixmap(qta.icon("mdi6.eye-outline", color="black").pixmap(QSize(18, 18)))
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

            thumb = _EditPageThumbnail(page_number)
            thumb.clicked.connect(self._on_thumbnail_clicked)
            thumb.rotate_requested.connect(self._on_rotate_requested)
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

    def _on_delete_mode_toggled(self, checked: bool) -> None:
        # TODO: chờ đại ca mô tả thêm hành vi chính xác của chế độ "Xóa".
        # Tạm thời: khi tắt chế độ, bỏ hết đánh dấu đang có (giống cơ chế của Split).
        if not checked:
            for thumb in self._thumbnails:
                thumb.reset_flag()

    def _on_thumbnail_clicked(self, page_number: int) -> None:
        self._select_page(page_number)
        if self.delete_checkbox.isChecked():
            thumb = self._thumbnails[page_number - 1]
            thumb.set_flagged(not thumb.is_flagged)

    def _on_rotate_requested(self, page_number: int, direction: str) -> None:
        # TODO Giai đoạn 2/3: gọi pdf_core.rotate_page() + undo_manager.register() thật.
        thumb = self._thumbnails[page_number - 1]
        thumb.apply_rotation(direction)
        huong = "trái" if direction == "left" else "phải"
        self._show_success(f"[Demo giao diện] Đã xoay {huong} 90° trang {page_number} — chưa xử lý PDF thật.")

    def _on_undo_clicked(self) -> None:
        # TODO Giai đoạn 2/3: nối với undo_manager.py — hiện là mock.
        self._show_success("[Demo giao diện] Nút Undo — chưa nối undo_manager.py thật.")

    def _on_clear_clicked(self) -> None:
        self._selected_file_path = None
        self.delete_checkbox.setChecked(False)
        for thumb in self._thumbnails:
            thumb.reset_flag()
            thumb.reset_rotation()
        self._select_page(1)
        self._hide_result()

    def _select_page(self, page_number: int) -> None:
        for thumb in self._thumbnails:
            thumb.set_selected(thumb.page_number == page_number)
        target = self._preview_pages.get(page_number)
        if target is not None:
            self.preview_scroll_b.ensureWidgetVisible(target, 0, 0)

    def _on_save_clicked(self) -> None:
        if not self._selected_file_path:
            self._show_error("Vui lòng chọn file PDF trước khi lưu.")
            return

        flagged = [t.page_number for t in self._thumbnails if t.is_flagged]
        rotated = {t.page_number: t.rotation for t in self._thumbnails if t.rotation}

        # TODO Giai đoạn 2/3: gọi tuần tự pdf_core (rotate_page/delete_pages/reorder_pages)
        # theo lịch sử undo_manager rồi ghi 1 file <tenfilegoc>_edited.pdf duy nhất.
        self._show_success(
            f"[Demo giao diện] Sẽ lưu file mới — xóa trang: {flagged or 'không có'}, "
            f"xoay trang: {rotated or 'không có'} — chưa xử lý PDF thật."
        )

    # ------------------------------------------------------------------
    def _show_success(self, message: str) -> None:
        self.result_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"✓ {message}")
        self.result_label.show()

    def _show_error(self, message: str) -> None:
        self.result_label.setStyleSheet(f"color: {COLOR_ERROR}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"✗ {message}")
        self.result_label.show()

    def _hide_result(self) -> None:
        self.result_label.hide()