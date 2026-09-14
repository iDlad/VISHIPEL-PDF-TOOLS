"""
Giao diện tính năng Gộp File (Merge) — GIAI ĐOẠN THIẾT KẾ UI THUẦN.

Bố cục 2 cột (A ~55% - B ~45%), dùng chung ngôn ngữ thiết kế với split_widget.py
(màu sắc/CONTROL_HEIGHT/CORNER_RADIUS lấy từ vishipel_theme.py):

- Cột A: A1 khối chọn file (nhiều file, không giới hạn số lượng — đúng
  02_dac_ta_tinh_nang.md mục 2), A2 danh sách file dạng thẻ có thể kéo-thả
  đổi thứ tự (thứ tự trong danh sách = thứ tự ghép vào file kết quả), click
  cả dòng để xem trước ở Cột B, nút "⋮" mỗi dòng để xoá khỏi danh sách,
  dropdown "Sắp xếp" là tiện ích phụ (không thay thế kéo-thả tay).
- Cột B: xem trước file đang chọn — dải thumbnail dọc bên trái (có thanh
  cuộn riêng) + khung xem lớn bên phải + điều hướng trang trước/sau.
  (Không có control Zoom theo yêu cầu đại ca.)

CHƯA gắn logic xử lý PDF thật — dữ liệu file/số trang là placeholder giả.
Sẽ nối vào pdf_core.py ở Giai đoạn 2/3 (xem 05_lo_trinh_phat_trien.md).
Các chỗ cần thay khi đó được đánh dấu # TODO Giai đoạn 2/3.

Ghi chú kỹ thuật quan trọng: Qt không hỗ trợ tốt việc kéo-thả nguyên 1 dòng
QListWidgetItem khi dòng đó có itemWidget tuỳ biến phủ kín (itemWidget sẽ
"ăn" hết sự kiện chuột trước khi QAbstractItemView kịp nhận diện thao tác
kéo) — vì vậy mỗi dòng có riêng 1 tay cầm kéo (icon mdi6.drag-vertical bên
trái) để bắt đầu kéo, thay vì kéo tự do trên cả dòng như hình mẫu.
"""
from __future__ import annotations

from typing import List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QDrag
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
    QListWidget,
    QListWidgetItem,
    QMenu,
    QAbstractItemView,
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
# Dữ liệu giả để dựng giao diện khi chưa nối pdf_core.py (Giai đoạn 2/3).
# ----------------------------------------------------------------------
_MOCK_FILES = [
    {"name": "Tai lieu 01.pdf", "size": "2.4 MB", "pages": 12},
    {"name": "Tai lieu 02.pdf", "size": "1.8 MB", "pages": 8},
    {"name": "Tai lieu 03.pdf", "size": "3.2 MB", "pages": 15},
    {"name": "Tai lieu 04.pdf", "size": "956 KB", "pages": 6},
    {"name": "Tai lieu 05.pdf", "size": "1.6 MB", "pages": 10},
]
# Số trang giả gán cho file mới chọn qua dialog/kéo-thả (chưa đọc PDF thật).
_MOCK_PAGES_FOR_NEW_FILE = 5

_ROW_ICON_SIZE = 34
_HANDLE_ICON_SIZE = 18
_PILL_BG = "#F3F4F6"           # nền pill "N trang" — chỉ dùng riêng màn này
_DROPZONE_ICON_BOX = 56

_THUMB_STRIP_WIDTH = 148
_THUMB_W, _THUMB_H = 92, 118    # tỉ lệ dọc giống trang A4 thu nhỏ
_BADGE_SIZE = 20
_DRAG_THRESHOLD = 8

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


def _parse_size_to_mb(size_text: str) -> float:
    """Quy đổi chuỗi dung lượng hiển thị (VD '2.4 MB', '956 KB') về số MB để
    so sánh khi sắp xếp. Không parse được thì coi như 0 (xếp cuối)."""
    try:
        value_str, unit = size_text.strip().split()
        value = float(value_str)
        return value / 1024 if unit.upper() == "KB" else value
    except (ValueError, AttributeError):
        return 0.0


# ----------------------------------------------------------------------
# A1 — Khối chọn file (giống Split: nền trắng, viền nét đứt, icon khung)
# ----------------------------------------------------------------------
class _DropZone(QFrame):
    files_selected = Signal(list)  # list[str] đường dẫn file

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
        icon_label.setPixmap(qta.icon("mdi6.file-plus-outline", color=COLOR_ACCENT).pixmap(QSize(28, 28)))
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

        # Theo 02_dac_ta_tinh_nang.md mục 2: không giới hạn cứng số file —
        # chỉ nhắc yêu cầu nghiệp vụ tối thiểu 2 file để gộp.
        note_label = QLabel("Lưu ý: CHỌN TỪ 2 FILE TRỞ LÊN")
        note_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(note_label)

        layout.addLayout(text_col)

    def _open_file_dialog(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Chọn file PDF", "", "PDF Files (*.pdf)")
        if paths:
            self.files_selected.emit(paths)

    def mousePressEvent(self, event) -> None:  # noqa: D401 - override Qt
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
            self.files_selected.emit(paths)


# ----------------------------------------------------------------------
# Danh sách file — QListWidget tuỳ biến, chỉ nhận DROP (không tự kéo từ
# việc chọn item) vì thao tác kéo được tay cầm riêng của mỗi dòng khởi tạo.
# ----------------------------------------------------------------------
class _DraggableFileList(QListWidget):
    row_drag_dropped = Signal(int, int)  # (vị trí cũ, vị trí thả tới)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFrameShape(QFrame.NoFrame)
        self.setSpacing(0)
        self.setStyleSheet(
            f"""
            QListWidget {{ background: transparent; border: none; }}
            QListWidget::item {{ background: transparent; border: none; padding: 0px; }}
            QListWidget::item:selected {{ background: transparent; }}
            {_SCROLLBAR_QSS}
            """
        )

    def start_row_drag(self, source_index: int) -> None:
        drag = QDrag(self)
        mime = QMimeData()
        mime.setText(str(source_index))
        drag.setMimeData(mime)
        drag.exec(Qt.MoveAction)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: D401 - override Qt
        if event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if not event.mimeData().hasText():
            return
        try:
            source_index = int(event.mimeData().text())
        except ValueError:
            return
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        target_item = self.itemAt(pos)
        target_index = self.row(target_item) if target_item is not None else self.count()
        event.acceptProposedAction()
        self.row_drag_dropped.emit(source_index, target_index)


class _DragHandle(QLabel):
    """Tay cầm kéo (icon mdi6.drag-vertical) — nơi duy nhất khởi tạo thao
    tác kéo-thả sắp xếp lại danh sách file (xem ghi chú kỹ thuật đầu file)."""

    def __init__(self, owner_row: "_FileRow", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.owner_row = owner_row
        self.setPixmap(qta.icon("mdi6.drag-vertical", color=COLOR_TEXT_SECONDARY).pixmap(QSize(_HANDLE_ICON_SIZE, _HANDLE_ICON_SIZE)))
        self.setFixedSize(_HANDLE_ICON_SIZE, _HANDLE_ICON_SIZE)
        self.setCursor(Qt.OpenHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
        self._press_pos = None

    def mousePressEvent(self, event) -> None:  # noqa: D401 - override Qt
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

    def mouseMoveEvent(self, event) -> None:  # noqa: D401 - override Qt
        if self._press_pos is None:
            return
        current_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        if (current_pos - self._press_pos).manhattanLength() < _DRAG_THRESHOLD:
            return
        self._press_pos = None
        self.owner_row.start_drag()

    def mouseReleaseEvent(self, event) -> None:  # noqa: D401 - override Qt
        self._press_pos = None


# ----------------------------------------------------------------------
# A3 — 1 dòng trong danh sách file
# ----------------------------------------------------------------------
class _FileRow(QFrame):
    clicked = Signal()
    remove_requested = Signal()

    def __init__(self, name: str, size_text: str, pages: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = name
        self.size_text = size_text
        self.pages = pages
        self.is_selected = False
        self.list_widget: Optional[_DraggableFileList] = None
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(66)
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 14, 8)
        layout.setSpacing(10)

        self.drag_handle = _DragHandle(self)
        layout.addWidget(self.drag_handle)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.file-pdf-box", color=COLOR_ERROR).pixmap(QSize(_ROW_ICON_SIZE, _ROW_ICON_SIZE)))
        icon_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(icon_label)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel(name)
        name_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        sub_label = QLabel(f"{size_text}  •  {pages} trang")
        sub_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;"
        )
        text_col.addWidget(name_label)
        text_col.addWidget(sub_label)
        layout.addLayout(text_col, 1)

        pages_pill = QLabel(f"{pages} trang")
        pages_pill.setStyleSheet(
            f"background-color: {_PILL_BG}; color: {COLOR_TEXT_SECONDARY}; font-size: 12px; "
            "font-weight: 600; border-radius: 10px; padding: 4px 10px; border: none;"
        )
        layout.addWidget(pages_pill)

        self.menu_button = QToolButton()
        self.menu_button.setCursor(Qt.PointingHandCursor)
        self.menu_button.setIcon(qta.icon("mdi6.dots-vertical", color=COLOR_TEXT_SECONDARY))
        self.menu_button.setAutoRaise(True)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        self.menu_button.setStyleSheet(
            """
            QToolButton { background: transparent; border: none; padding: 4px; }
            QToolButton:hover { background-color: #F3F4F6; border-radius: 6px; }
            QToolButton::menu-indicator { image: none; }
            """
        )
        menu = QMenu(self.menu_button)
        remove_action = menu.addAction("Xoá khỏi danh sách")
        remove_action.triggered.connect(self.remove_requested.emit)
        self.menu_button.setMenu(menu)
        layout.addWidget(self.menu_button)

    def _apply_style(self) -> None:
        if self.is_selected:
            self.setStyleSheet(
                f"""
                _FileRow {{
                    background-color: {COLOR_ACCENT_LIGHT};
                    border: none;
                    border-left: 3px solid {COLOR_ACCENT};
                }}
                """
            )
        else:
            self.setStyleSheet(
                f"""
                _FileRow {{
                    background-color: white;
                    border: none;
                    border-bottom: 1px solid {COLOR_BORDER};
                }}
                """
            )

    def set_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self._apply_style()

    def current_index(self) -> Optional[int]:
        if self.list_widget is None:
            return None
        for i in range(self.list_widget.count()):
            if self.list_widget.itemWidget(self.list_widget.item(i)) is self:
                return i
        return None

    def start_drag(self) -> None:
        if self.list_widget is None:
            return
        index = self.current_index()
        if index is not None:
            self.list_widget.start_row_drag(index)

    def mousePressEvent(self, event) -> None:  # noqa: D401 - override Qt
        super().mousePressEvent(event)
        self.clicked.emit()


# ----------------------------------------------------------------------
# Cột B — 1 thumbnail trang trong dải xem trước
# ----------------------------------------------------------------------
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
                f"QFrame {{ background-color: {COLOR_ACCENT_LIGHT}; border: 2px solid {COLOR_ACCENT}; border-radius: 8px; }}"
            )
            self.badge.setStyleSheet(
                f"background-color: {COLOR_ACCENT}; color: white; font-size: 11px; font-weight: 700; "
                f"border-radius: {_BADGE_SIZE // 2}px; border: none;"
            )
        else:
            self.setStyleSheet(
                f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 8px; }}"
            )
            self.badge.setStyleSheet("background-color: transparent; color: transparent; border: none;")

    def set_current(self, current: bool) -> None:
        self.is_current = current
        self._apply_style()

    def mousePressEvent(self, event) -> None:  # noqa: D401 - override Qt
        super().mousePressEvent(event)
        self.clicked.emit(self.page_number)


# ----------------------------------------------------------------------
# Widget chính
# ----------------------------------------------------------------------
class MergeFeatureWidget(QWidget):
    """Giao diện tính năng Gộp File — GIAI ĐOẠN UI THUẦN (xem docstring đầu file)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._selected_row: Optional[_FileRow] = None
        self._current_file_name: Optional[str] = None
        self._current_total_pages = 0
        self._current_page = 0
        self._preview_thumbs: List[_PreviewThumb] = []

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # ================= CỘT A (~55%) =================
        column_a = QVBoxLayout()
        column_a.setSpacing(14)

        # --- A1: Drop zone ---
        self.drop_zone = _DropZone()
        self.drop_zone.files_selected.connect(self._on_files_selected)
        column_a.addWidget(self.drop_zone)

        # --- A2: khung danh sách file ---
        list_card = QFrame()
        list_card.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: 14px; }}"
        )
        list_card_layout = QVBoxLayout(list_card)
        list_card_layout.setContentsMargins(18, 14, 18, 10)
        list_card_layout.setSpacing(8)

        list_header = QHBoxLayout()
        list_icon = QLabel()
        list_icon.setPixmap(qta.icon("mdi6.format-list-bulleted", color=COLOR_TEXT_PRIMARY).pixmap(QSize(18, 18)))
        list_icon.setStyleSheet("background: transparent; border: none;")
        list_header.addWidget(list_icon)

        self.list_count_label = QLabel("Danh sách file (0)")
        self.list_count_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        list_header.addWidget(self.list_count_label)
        list_header.addStretch()

        # Dropdown "Sắp xếp" — tiện ích phụ, KHÔNG thay thế kéo-thả tay.
        self.sort_button = QToolButton()
        self.sort_button.setText(" Sắp xếp")
        self.sort_button.setIcon(qta.icon("mdi6.sort", color=COLOR_TEXT_SECONDARY))
        self.sort_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.sort_button.setCursor(Qt.PointingHandCursor)
        self.sort_button.setPopupMode(QToolButton.InstantPopup)
        self.sort_button.setStyleSheet(
            f"""
            QToolButton {{
                background: transparent;
                border: none;
                color: {COLOR_TEXT_SECONDARY};
                font-size: 13px;
                font-weight: 600;
                padding: 4px 8px;
                border-radius: 6px;
            }}
            QToolButton:hover {{ background-color: #F3F4F6; }}
            QToolButton::menu-indicator {{ image: none; }}
            """
        )
        sort_menu = QMenu(self.sort_button)
        sort_menu.addAction("Tên (A → Z)", lambda: self._sort_files("name"))
        sort_menu.addAction("Dung lượng (lớn → nhỏ)", lambda: self._sort_files("size"))
        sort_menu.addAction("Số trang (nhiều → ít)", lambda: self._sort_files("pages"))
        self.sort_button.setMenu(sort_menu)
        list_header.addWidget(self.sort_button)

        list_card_layout.addLayout(list_header)

        self.empty_hint = QLabel("Chưa có file nào — hãy chọn hoặc kéo-thả file PDF phía trên để bắt đầu.")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; padding: 28px 12px; "
            "background: transparent; border: none;"
        )
        self.empty_hint.hide()
        list_card_layout.addWidget(self.empty_hint)

        self.file_list = _DraggableFileList()
        self.file_list.row_drag_dropped.connect(self._on_row_drag_dropped)
        list_card_layout.addWidget(self.file_list, 1)

        column_a.addWidget(list_card, 1)

        # --- A4: hàng nút hành động ---
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.addStretch()

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

        self.merge_button = QPushButton(" Gộp File")
        self.merge_button.setIcon(qta.icon("mdi6.file-multiple-outline", color="white"))
        self.merge_button.setCursor(Qt.PointingHandCursor)
        self.merge_button.setFixedHeight(CONTROL_HEIGHT)
        self.merge_button.setMinimumWidth(130)
        self.merge_button.setStyleSheet(
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
        self.merge_button.clicked.connect(self._on_merge_clicked)
        bottom_row.addWidget(self.merge_button)

        column_a.addLayout(bottom_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        column_a.addWidget(self.result_label)

        # ================= CỘT B (50%) — Xem trước =================
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

        self.prev_page_btn = QToolButton()
        self.prev_page_btn.setIcon(qta.icon("mdi6.chevron-left", color=COLOR_TEXT_SECONDARY))
        self.prev_page_btn.setCursor(Qt.PointingHandCursor)
        self.prev_page_btn.setAutoRaise(True)
        self.prev_page_btn.clicked.connect(lambda: self._change_page(-1))
        header_row.addWidget(self.prev_page_btn)

        self.page_indicator = QLabel("0 / 0")
        self.page_indicator.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.page_indicator)

        self.next_page_btn = QToolButton()
        self.next_page_btn.setIcon(qta.icon("mdi6.chevron-right", color=COLOR_TEXT_SECONDARY))
        self.next_page_btn.setCursor(Qt.PointingHandCursor)
        self.next_page_btn.setAutoRaise(True)
        self.next_page_btn.clicked.connect(lambda: self._change_page(1))
        header_row.addWidget(self.next_page_btn)

        preview_card_layout.addLayout(header_row)

        body_row = QHBoxLayout()
        body_row.setSpacing(14)

        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setFixedWidth(_THUMB_STRIP_WIDTH)
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }} {_SCROLLBAR_QSS}"
        )
        self.thumb_container = QWidget()
        self.thumb_container.setStyleSheet("background: transparent;")
        self.thumb_layout = QVBoxLayout(self.thumb_container)
        self.thumb_layout.setContentsMargins(2, 2, 10, 2)
        self.thumb_layout.setSpacing(12)
        self.thumb_layout.setAlignment(Qt.AlignTop)
        self.thumb_scroll.setWidget(self.thumb_container)
        body_row.addWidget(self.thumb_scroll)

        self.main_viewer = QFrame()
        self.main_viewer.setStyleSheet(
            f"QFrame {{ background-color: {COLOR_CONTENT_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 10px; }}"
        )
        viewer_layout = QVBoxLayout(self.main_viewer)
        viewer_layout.setAlignment(Qt.AlignCenter)
        self.main_page_label = QLabel("—")
        self.main_page_label.setAlignment(Qt.AlignCenter)
        self.main_page_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 56px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        viewer_layout.addWidget(self.main_page_label)
        body_row.addWidget(self.main_viewer, 1)

        preview_card_layout.addLayout(body_row, 1)
        column_b.addWidget(preview_card, 1)

        # Ghép 2 cột theo tỉ lệ 55/45
        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, 50)
        root_layout.addWidget(column_b_widget, 50)

        # Nạp sẵn dữ liệu demo (giống cách split_widget.py luôn hiện sẵn lưới
        # mock) để đại ca thấy ngay bố cục khi chạy thử, chưa cần chọn file.
        # TODO Giai đoạn 2: bỏ đoạn nạp mock này, bắt đầu từ danh sách rỗng.
        for f in _MOCK_FILES:
            self._add_file_row(f["name"], f["size"], f["pages"])
        self._select_first_available()

    # ------------------------------------------------------------------
    # Quản lý danh sách file (Cột A)
    # ------------------------------------------------------------------
    def _add_file_row(self, name: str, size_text: str, pages: int) -> _FileRow:
        row = _FileRow(name, size_text, pages)
        item = QListWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        item.setSizeHint(row.sizeHint())
        self.file_list.addItem(item)
        self.file_list.setItemWidget(item, row)
        row.list_widget = self.file_list
        row.clicked.connect(lambda r=row: self._select_row(r))
        row.remove_requested.connect(lambda r=row: self._remove_row(r))
        self._update_header_count()
        return row

    def _find_item_for_row(self, row: _FileRow) -> Optional[QListWidgetItem]:
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if self.file_list.itemWidget(item) is row:
                return item
        return None

    def _remove_row(self, row: _FileRow) -> None:
        item = self._find_item_for_row(row)
        if item is None:
            return
        was_selected = row is self._selected_row
        self.file_list.takeItem(self.file_list.row(item))
        row.deleteLater()
        self._update_header_count()
        if was_selected:
            self._select_first_available()
        self._hide_result()

    def _move_row(self, from_index: int, to_index: int) -> None:
        count = self.file_list.count()
        if from_index < 0 or from_index >= count or to_index < 0:
            return
        item = self.file_list.item(from_index)
        widget = self.file_list.itemWidget(item)
        self.file_list.takeItem(from_index)
        if to_index > from_index:
            to_index -= 1
        to_index = max(0, min(to_index, self.file_list.count()))
        self.file_list.insertItem(to_index, item)
        self.file_list.setItemWidget(item, widget)

    def _on_row_drag_dropped(self, source_index: int, target_index: int) -> None:
        self._move_row(source_index, target_index)

    def _update_header_count(self) -> None:
        count = self.file_list.count()
        self.list_count_label.setText(f"Danh sách file ({count})")
        self.file_list.setVisible(count > 0)
        self.empty_hint.setVisible(count == 0)

    def _sort_files(self, key: str) -> None:
        rows_data = [
            (
                self.file_list.itemWidget(self.file_list.item(i)).name,
                self.file_list.itemWidget(self.file_list.item(i)).size_text,
                self.file_list.itemWidget(self.file_list.item(i)).pages,
            )
            for i in range(self.file_list.count())
        ]
        if key == "name":
            rows_data.sort(key=lambda r: r[0].lower())
        elif key == "size":
            rows_data.sort(key=lambda r: _parse_size_to_mb(r[1]), reverse=True)
        elif key == "pages":
            rows_data.sort(key=lambda r: r[2], reverse=True)

        selected_name = self._selected_row.name if self._selected_row else None
        self.file_list.clear()
        self._selected_row = None
        for name, size_text, pages in rows_data:
            new_row = self._add_file_row(name, size_text, pages)
            if name == selected_name:
                self._select_row(new_row)
        if self._selected_row is None:
            self._select_first_available()

    # ------------------------------------------------------------------
    # Sự kiện
    # ------------------------------------------------------------------
    def _on_files_selected(self, paths: List[str]) -> None:
        # TODO Giai đoạn 2: gọi pdf_core.open_document(path) + get_page_count(path)
        # để lấy dung lượng/số trang thật, thay cho giá trị placeholder dưới đây.
        # Cũng cần bắt CorruptedFileError / PasswordProtectedError ở đây.
        for path in paths:
            name = path.replace("\\", "/").split("/")[-1]
            self._add_file_row(name, "-- MB", _MOCK_PAGES_FOR_NEW_FILE)
        if self._selected_row is None:
            self._select_first_available()
        self._hide_result()

    def _on_clear_clicked(self) -> None:
        self.file_list.clear()
        self._selected_row = None
        self._update_header_count()
        self._show_empty_preview()
        self._hide_result()

    def _on_merge_clicked(self) -> None:
        count = self.file_list.count()
        if count < 2:
            self._show_error("Vui lòng chọn ít nhất 2 file PDF để gộp.")
            return
        order = [
            self.file_list.itemWidget(self.file_list.item(i)).name for i in range(count)
        ]
        # TODO Giai đoạn 2/3: gọi pdf_core.merge_pdfs(order, output_path) đúng thứ tự này.
        self._show_success(f"[Demo giao diện] Sẽ gộp {count} file theo thứ tự: {', '.join(order)} — chưa xử lý PDF thật.")

    # ------------------------------------------------------------------
    # Xem trước (Cột B)
    # ------------------------------------------------------------------
    def _select_row(self, row: _FileRow) -> None:
        if self._selected_row is not None:
            self._selected_row.set_selected(False)
        row.set_selected(True)
        self._selected_row = row
        self._load_preview(row.name, row.pages)

    def _select_first_available(self) -> None:
        if self.file_list.count() == 0:
            self._selected_row = None
            self._show_empty_preview()
            return
        first_item = self.file_list.item(0)
        first_row = self.file_list.itemWidget(first_item)
        self._select_row(first_row)

    def _load_preview(self, name: str, pages: int) -> None:
        # TODO Giai đoạn 2: thay bằng ảnh render thật từng trang qua
        # pdf_core.render_page_thumbnail(path, i).
        self._current_file_name = name
        self._current_total_pages = pages
        self._current_page = 1 if pages > 0 else 0
        self.preview_title.setText(f"Xem trước: {name}")
        self._build_preview_thumbs(pages)
        self._refresh_page_view()

    def _show_empty_preview(self) -> None:
        self._current_file_name = None
        self._current_total_pages = 0
        self._current_page = 0
        self.preview_title.setText("Xem trước: —")
        self._build_preview_thumbs(0)
        self._refresh_page_view()

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
            wrapper_layout.setSpacing(4)

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

    def _on_thumb_clicked(self, page_number: int) -> None:
        self._current_page = page_number
        self._refresh_page_view()

    def _change_page(self, delta: int) -> None:
        if self._current_total_pages == 0:
            return
        new_page = self._current_page + delta
        if 1 <= new_page <= self._current_total_pages:
            self._current_page = new_page
            self._refresh_page_view()

    def _refresh_page_view(self) -> None:
        if self._current_total_pages == 0:
            self.page_indicator.setText("0 / 0")
            self.main_page_label.setText("—")
            return
        self.page_indicator.setText(f"{self._current_page} / {self._current_total_pages}")
        self.main_page_label.setText(str(self._current_page))
        for thumb in self._preview_thumbs:
            thumb.set_current(thumb.page_number == self._current_page)
        if 0 <= self._current_page - 1 < len(self._preview_thumbs):
            current_widget = self._preview_thumbs[self._current_page - 1]
            self.thumb_scroll.ensureWidgetVisible(current_widget, 0, 20)

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