"""
Giao diện tính năng Tách File (Split) — GIAI ĐOẠN THIẾT KẾ UI THUẦN.

Bố cục 2 cột (A ~55% - B ~45%):
- Cột A: A1 khối chọn file (nền trắng, viền nét đứt, icon khung bên trái),
  A3 lưới thumbnail 3 cột x N hàng (cờ đỏ = vạch dọc bên phải ô, đặt bằng
  cách click thumbnail khi đang ở chế độ "Tùy chỉnh"), hàng dưới cùng gộp
  "Nhập số trang" + "Tùy chỉnh" + nút "Tách File".
- Cột B: khung Preview cuộn liên tục nhiều trang (giống xem PDF thật), click
  thumbnail ở A3 sẽ cuộn tới đúng trang.

CHƯA gắn logic xử lý PDF thật — toàn bộ nội dung trang/preview là placeholder
giả (_MOCK_PAGE_COUNT trang đánh số). Sẽ nối vào pdf_core.py ở Giai đoạn 2/3
(xem 05_lo_trinh_phat_trien.md). Các chỗ cần thay khi đó được đánh dấu
# TODO Giai đoạn 2/3.
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
    QLineEdit,
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

# Bo góc riêng cho checkbox vuông 22x22 — co giãn theo cùng tỉ lệ với CORNER_RADIUS
# (chuẩn cho control cao CONTROL_HEIGHT=38px) để khối vuông nhỏ không bị "quá tròn"
# nếu dùng thẳng CORNER_RADIUS gốc.
_CHECKBOX_SIZE = 22
_CHECKBOX_RADIUS = round(CORNER_RADIUS * _CHECKBOX_SIZE / CONTROL_HEIGHT)

# Kích thước khung icon vuông trong khối chọn file (A1)
_DROPZONE_ICON_BOX = 56

# Chiều rộng khung "Nhập số trang" (số + 2 nút mũi tên ghép dọc bên phải)
_SPIN_BOX_WIDTH = 84
_SPIN_ARROW_WIDTH = 22


def _spin_arrow_style(is_top: bool) -> str:
    """QSS cho 2 nút mũi tên tăng/giảm ghép trong ô 'Nhập số trang' — thay cho
    nút mặc định của QSpinBox (hiển thị xấu, không đồng bộ giữa các theme
    Windows khác nhau) bằng nút bo góc đúng theme app, có trạng thái hover."""
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


# QSS thanh cuộn dọc dùng chung cho các QScrollArea trong màn Tách File —
# thanh mảnh, bo tròn, không có nút mũi tên 2 đầu (thay thế thanh cuộn mặc
# định của hệ điều hành trông thô/không đồng bộ giao diện).
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
    """1 ô thumbnail giả (số trang) + vạch cờ đỏ mỏng bên cạnh phải.
    Click vào ô: luôn chọn trang để xem Preview; nếu đang ở chế độ Tùy
    chỉnh thì đồng thời bật/tắt cờ ngay sau trang này."""

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

        # Vạch cờ đỏ — luôn chiếm chỗ, chỉ đổi màu khi được đặt cờ.
        self.flag_bar = QFrame()
        self.flag_bar.setFixedWidth(_FLAG_BAR_WIDTH)
        self.flag_bar.setFixedHeight(_THUMB_SIZE)
        self._apply_flag_style()
        row_layout.addWidget(self.flag_bar)

    def _apply_card_style(self) -> None:
        # Trang đang được chọn: viền cam + tô nền cam nhạt (giống ảnh mẫu).
        # Trang thường: viền xám nhạt, nền trắng.
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

    def mousePressEvent(self, event) -> None:  # noqa: D401 - override Qt
        super().mousePressEvent(event)
        self.clicked.emit(self.page_number)


# ----------------------------------------------------------------------
# Checkbox tùy chỉnh — dấu tích (✓) thay vì "X", đơn giản/hiện đại
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
# A1 — Khối chọn file (nền trắng, viền nét đứt, icon khung + 2 dòng chữ)
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

        # Khung icon vuông bo góc, viền cam, icon upload màu cam ở giữa.
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

        # 2 dòng chữ: tiêu đề đậm (đen) + ghi chú phụ (xám).
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

    def mousePressEvent(self, event) -> None:  # noqa: D401 - override Qt
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
    """Giao diện tính năng Tách File — GIAI ĐOẠN UI THUẦN (xem docstring đầu file)."""

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

        # --- A3: khung lưới thumbnail ---
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet(
            f"""
            QScrollArea {{ background: transparent; border: 1.5px solid {COLOR_BORDER}; border-radius: 14px; }}
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
        column_a.addWidget(self.preview_scroll, stretch=1)

        # --- Hàng dưới cùng: Nhập số trang + Tùy chỉnh + Clear + Tách File ---
        # Chiều cao (CONTROL_HEIGHT) và bo góc (CORNER_RADIUS) lấy từ vishipel_theme.py
        # để đồng bộ với các tính năng khác (Merge/Edit/Insert/Rename) sau này.
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.setContentsMargins(0, 0, 0, 0)

        # 1. Nhãn "Nhập số trang:" — chữ thường, không có nền badge.
        pages_label = QLabel("Nhập số trang:")
        pages_label.setFixedHeight(CONTROL_HEIGHT)
        pages_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        pages_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        bottom_row.addWidget(pages_label)

        # 2. Ô nhập số trang — số + 2 nút mũi tên tăng/giảm ghép dọc bên phải,
        # tự vẽ bằng QToolButton thay vì dùng nút mặc định của QSpinBox (nút
        # mặc định hiển thị to/xấu và lệch theme tùy hệ điều hành Windows).
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

        # 3 + 4. Checkbox + nhãn "Tùy chỉnh" — ghép sát thành 1 cụm (spacing hẹp
        # hơn so với khoảng cách giữa các cụm điều khiển khác trên hàng này) để
        # rõ ràng đây là 1 tùy chọn duy nhất, đúng thứ tự checkbox đứng trước chữ.
        custom_group = QHBoxLayout()
        custom_group.setContentsMargins(0, 0, 0, 0)
        custom_group.setSpacing(8)

        self.custom_checkbox = _CheckToggle()
        checkbox_container = QWidget()
        checkbox_container.setFixedHeight(CONTROL_HEIGHT)
        checkbox_layout = QHBoxLayout(checkbox_container)
        checkbox_layout.setContentsMargins(0, 0, 0, 0)
        checkbox_layout.setAlignment(Qt.AlignCenter)
        checkbox_layout.addWidget(self.custom_checkbox)
        self.custom_checkbox.toggled.connect(self._on_custom_toggled)
        custom_group.addWidget(checkbox_container)

        custom_label = QLabel("Tùy chỉnh")
        custom_label.setFixedHeight(CONTROL_HEIGHT)
        custom_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        custom_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        custom_group.addWidget(custom_label)

        custom_group_widget = QWidget()
        custom_group_widget.setLayout(custom_group)
        bottom_row.addWidget(custom_group_widget)

        # Đẩy nhóm thao tác chính sang phải
        bottom_row.addStretch()

        # 5. Nút Clear — nền trắng, viền xám, chữ đen (nút phụ).
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

        # 6. Nút Tách File — nền cam accent, chữ trắng, có icon kéo (nút chính).
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

        # Khung viền bo góc bao quanh toàn bộ cột Preview + thanh cuộn dọc
        # mảnh/bo tròn tự thiết kế (thay thanh cuộn mặc định của hệ điều hành).
        self.preview_scroll_b = QScrollArea()
        self.preview_scroll_b.setWidgetResizable(True)
        self.preview_scroll_b.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: white;
                border: 1.5px solid {COLOR_BORDER};
                border-radius: 14px;
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

        column_b.addWidget(self.preview_scroll_b, stretch=1)

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
        # TODO Giai đoạn 2: thay _MOCK_PAGE_COUNT bằng pdf_core.get_page_count(path)
        # và thay _PageThumbnail bằng ảnh thật từ pdf_core.render_page_thumbnail(path, i).
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
        # TODO Giai đoạn 2: thay bằng ảnh render thật từng trang qua
        # pdf_core.render_page_thumbnail(path, i, max_width=...) với kích thước lớn hơn.
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
        # TODO Giai đoạn 2: gọi pdf_core.open_document(path), bắt
        # CorruptedFileError / PasswordProtectedError, rồi cập nhật lưới
        # thumbnail + preview bằng nội dung thật thay vì dữ liệu giả.
        self._selected_file_path = path
        self._select_page(1)
        self._hide_result()

    def _on_custom_toggled(self, checked: bool) -> None:
        self.pages_per_file_spin.setDisabled(checked)
        self.spin_up_btn.setDisabled(checked)
        self.spin_down_btn.setDisabled(checked)
        if not checked:
            # Thoát chế độ Tùy chỉnh: xóa hết cờ đã đặt để tránh nhầm lẫn.
            for thumb in self._thumbnails:
                thumb.reset_flag()

    def _on_thumbnail_clicked(self, page_number: int) -> None:
        self._select_page(page_number)
        if self.custom_checkbox.isChecked():
            thumb = self._thumbnails[page_number - 1]
            thumb.set_flagged(not thumb.is_flagged)

    def _on_clear_clicked(self) -> None:
        """Xóa toàn bộ thao tác người dùng vừa thực hiện, đưa giao diện về
        trạng thái ban đầu (chưa chọn file, chưa đặt cờ, chưa nhập số trang)."""
        # TODO Giai đoạn 2/3: nếu đã có file thật đang mở, đóng/giải phóng
        # tài nguyên file đó ở đây trước khi reset trạng thái.
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
        # Cuộn khung Preview (Cột B) tới đúng trang được chọn.
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
            # TODO Giai đoạn 2/3: gọi pdf_core.split_by_fixed_count(...)
            self._show_success(f"[Demo giao diện] Sẽ tách theo {n} trang/file — chưa xử lý PDF thật.")
        else:
            flagged = [t.page_number for t in self._thumbnails if t.is_flagged]
            if not flagged:
                self._show_error("Vui lòng đặt ít nhất 1 cờ trước khi tách.")
                return
            # TODO Giai đoạn 2/3: gọi pdf_core.split_by_flags(...)
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