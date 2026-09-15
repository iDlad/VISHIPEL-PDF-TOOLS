"""
Giao diện tính năng Gộp File (Merge) — Đã điều chỉnh theo yêu cầu UI/UX.
"""
from __future__ import annotations

from typing import List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QDragEnterEvent, QDropEvent
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
# Dữ liệu giả để dựng giao diện
# ----------------------------------------------------------------------
_MOCK_FILES = [
    {"name": "Tai lieu 01.pdf", "size": "2.4 MB", "pages": 12},
    {"name": "Tai lieu 02.pdf", "size": "1.8 MB", "pages": 8},
    {"name": "Tai lieu 03.pdf", "size": "3.2 MB", "pages": 15},
    {"name": "Tai lieu 04.pdf", "size": "956 KB", "pages": 6},
    {"name": "Tai lieu 05.pdf", "size": "1.6 MB", "pages": 10},
]
_MOCK_PAGES_FOR_NEW_FILE = 5

_ROW_ICON_SIZE = 34
_HANDLE_ICON_SIZE = 18
_PILL_BG = "#F3F4F6"
_DROPZONE_ICON_BOX = 56

# Đã thu nhỏ thumbnail để dành diện tích cho xem trước
_THUMB_STRIP_WIDTH = 115
_THUMB_W, _THUMB_H = 72, 94
_BADGE_SIZE = 18
_DRAG_THRESHOLD = 8
# Đường kẻ báo vị trí sẽ chèn file khi kéo-thả (kiểu PowerPoint)
_DROP_INDICATOR_COLOR = "#FA9005"
_DROP_INDICATOR_HEIGHT = 4
_DROP_INDICATOR_DOT_SIZE = 10

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


def _parse_size_to_mb(size_text: str) -> float:
    try:
        value_str, unit = size_text.strip().split()
        value = float(value_str)
        return value / 1024 if unit.upper() == "KB" else value
    except (ValueError, AttributeError):
        return 0.0


# ----------------------------------------------------------------------
# A1 — Khối chọn file
# ----------------------------------------------------------------------
class _DropZone(QFrame):
    files_selected = Signal(list)

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

    def mousePressEvent(self, event) -> None:
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
# Danh sách file kéo-thả
# ----------------------------------------------------------------------
class _DraggableFileList(QListWidget):
    """Danh sách file, hỗ trợ kéo-thả đổi thứ tự.

    LƯU Ý: KHÔNG dùng cơ chế Drag & Drop gốc của Qt (QDrag/dragMoveEvent).
    Lý do: mỗi dòng trong danh sách là 1 widget riêng gắn qua
    setItemWidget(), và cơ chế DnD gốc của Qt xử lý không ổn định khi con
    trỏ di chuyển qua nhiều item-widget khác nhau trong lúc kéo — sự kiện
    dragMoveEvent chỉ tới đúng ở vài vị trí (thường chỉ đúng lúc vào ngay
    dòng đầu tiên) rồi bị Qt "nuốt mất" ở các dòng còn lại, khiến đường kẻ
    báo vị trí không hiển thị đúng.

    Thay vào đó, việc kéo được tự viết bằng grabMouse() ở `_FileRow`: khi
    bắt đầu kéo, dòng đó giữ toàn bộ sự kiện chuột cho riêng nó (dù con trỏ
    đi qua bất kỳ dòng nào khác), rồi tự gọi các hàm bên dưới để cập nhật
    đường kẻ và tính vị trí thả — ổn định tuyệt đối, không phụ thuộc vào
    việc Qt có chuyển tiếp sự kiện đúng hay không.
    """

    row_drag_dropped = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
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
        # Vị trí (index) sẽ chèn file nếu thả ngay lúc này — None nghĩa là
        # không đang kéo, ẩn đường kẻ.
        self._drop_indicator_index: Optional[int] = None

        # QUAN TRỌNG: đường kẻ báo vị trí PHẢI là 1 widget con thật sự (chứ
        # không phải vẽ bằng QPainter trong paintEvent) — vì mỗi dòng file
        # (_FileRow) cũng là 1 widget con gắn qua setItemWidget(), và trong
        # Qt, widget con LUÔN được vẽ đè lên trên bất kỳ thứ gì cha nó tự vẽ
        # bằng QPainter trong paintEvent, bất kể thứ tự code. Nếu vẽ bằng
        # QPainter, đường kẻ sẽ luôn bị các dòng file che kín. Dùng widget
        # riêng + raise_() mỗi lần cập nhật thì đường kẻ luôn nổi lên trên
        # cùng, hiển thị đúng ở MỌI vị trí.
        self._drop_line = QFrame(self.viewport())
        self._drop_line.setFixedHeight(_DROP_INDICATOR_HEIGHT)
        self._drop_line.setStyleSheet(
            f"background-color: {_DROP_INDICATOR_COLOR}; "
            f"border-radius: {_DROP_INDICATOR_HEIGHT // 2}px;"
        )
        self._drop_line.hide()

        self._drop_dot = QFrame(self.viewport())
        self._drop_dot.setFixedSize(_DROP_INDICATOR_DOT_SIZE, _DROP_INDICATOR_DOT_SIZE)
        self._drop_dot.setStyleSheet(
            f"background-color: {_DROP_INDICATOR_COLOR}; "
            f"border-radius: {_DROP_INDICATOR_DOT_SIZE // 2}px;"
        )
        self._drop_dot.hide()

    def compute_drop_index_from_viewport_pos(self, pos) -> int:
        """Tính vị trí sẽ chèn file dựa vào con trỏ đang ở NỬA TRÊN hay
        NỬA DƯỚI của dòng đang trỏ tới (kiểu PowerPoint khi kéo-thả slide),
        thay vì luôn chèn trước dòng đó. `pos` phải là tọa độ trong hệ
        viewport() của chính danh sách này."""
        if self.count() == 0:
            return 0
        item = self.itemAt(pos)
        if item is None:
            first_rect = self.visualItemRect(self.item(0))
            if pos.y() < first_rect.top():
                return 0  # kéo lên phía trên dòng đầu tiên
            return self.count()  # kéo xuống phía dưới dòng cuối cùng
        index = self.row(item)
        rect = self.visualItemRect(item)
        if pos.y() > rect.center().y():
            index += 1
        return index

    def update_drop_indicator_from_pos(self, pos) -> None:
        index = self.compute_drop_index_from_viewport_pos(pos)
        self._drop_indicator_index = index
        self._show_drop_indicator_at(index)

    def _show_drop_indicator_at(self, index: int) -> None:
        y = self._indicator_y_for_index(index)
        viewport_width = self.viewport().width()
        dot_radius = _DROP_INDICATOR_DOT_SIZE // 2
        left = 6
        line_left = left + _DROP_INDICATOR_DOT_SIZE + 2
        line_right = max(line_left, viewport_width - 6)

        self._drop_dot.move(left, y - dot_radius)
        self._drop_line.setGeometry(
            line_left, y - _DROP_INDICATOR_HEIGHT // 2,
            max(0, line_right - line_left), _DROP_INDICATOR_HEIGHT,
        )
        self._drop_dot.show()
        self._drop_line.show()
        # Bắt buộc raise_() mỗi lần hiện — đảm bảo luôn nổi trên các dòng file
        self._drop_dot.raise_()
        self._drop_line.raise_()

    def clear_drop_indicator(self) -> None:
        self._drop_indicator_index = None
        self._drop_line.hide()
        self._drop_dot.hide()

    def _indicator_y_for_index(self, index: int) -> int:
        count = self.count()
        if count == 0:
            return 0
        if index >= count:
            return self.visualItemRect(self.item(count - 1)).bottom()
        return self.visualItemRect(self.item(index)).top()


class _DragHandle(QLabel):
    """Icon '⋮⋮' chỉ mang tính gợi ý trực quan (có thể kéo dòng này) —
    bản thân không xử lý sự kiện chuột, để việc kéo-thả có thể bắt đầu từ
    BẤT KỲ đâu trên dòng (xử lý tại _FileRow), không riêng gì icon này."""

    def __init__(self, owner_row: "_FileRow", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.owner_row = owner_row
        self.setPixmap(qta.icon("mdi6.drag-vertical", color=COLOR_TEXT_SECONDARY).pixmap(QSize(_HANDLE_ICON_SIZE, _HANDLE_ICON_SIZE)))
        self.setFixedSize(_HANDLE_ICON_SIZE, _HANDLE_ICON_SIZE)
        self.setCursor(Qt.OpenHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
        # Không nhận sự kiện chuột -> tự động "xuyên qua" cho _FileRow (cha) xử lý
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)


# ----------------------------------------------------------------------
# A3 — 1 dòng trong danh sách file (Thay nút 3 chấm bằng nút X xóa trực tiếp)
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
        self._press_pos = None
        self._dragging = False
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

        # Nút icon X xóa trực tiếp
        self.delete_btn = QToolButton()
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setIcon(qta.icon("mdi6.close", color=COLOR_TEXT_SECONDARY))
        self.delete_btn.setIconSize(QSize(18, 18))
        self.delete_btn.setToolTip("Xoá khỏi danh sách")
        self.delete_btn.setStyleSheet(
            f"""
            QToolButton {{
                background: transparent;
                border: none;
                border-radius: 6px;
                padding: 4px;
            }}
            QToolButton:hover {{
                background-color: #FEE2E2;
                color: {COLOR_ERROR};
            }}
            """
        )
        self.delete_btn.clicked.connect(self.remove_requested.emit)
        layout.addWidget(self.delete_btn)

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

    def _to_list_viewport_pos(self, local_pos: QPoint) -> Optional[QPoint]:
        """Đổi tọa độ local (trên chính dòng này) sang tọa độ trong
        viewport() của danh sách file — dùng để biết đang trỏ vào đâu
        trong toàn bộ danh sách, kể cả khi con trỏ đang ở trên 1 dòng khác."""
        if self.list_widget is None:
            return None
        global_pos = self.mapToGlobal(local_pos)
        return self.list_widget.viewport().mapFromGlobal(global_pos)

    # ------------------------------------------------------------------
    # Nhấn giữ + kéo (ở BẤT KỲ đâu trên dòng) = sắp xếp lại vị trí.
    # Nhấn rồi thả ra mà KHÔNG di chuyển = click chọn dòng để xem preview.
    #
    # Việc kéo dùng grabMouse() (không dùng QDrag của Qt) để dòng này giữ
    # toàn bộ sự kiện chuột cho riêng nó trong suốt quá trình kéo, dù con
    # trỏ đang ở trên bất kỳ dòng nào khác — xem giải thích chi tiết ở
    # docstring của _DraggableFileList.
    # ------------------------------------------------------------------
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._press_pos is None:
            super().mouseMoveEvent(event)
            return
        current_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()

        if not self._dragging:
            if (current_pos - self._press_pos).manhattanLength() < _DRAG_THRESHOLD:
                super().mouseMoveEvent(event)
                return
            self._dragging = True
            self.setCursor(Qt.ClosedHandCursor)
            self.grabMouse()

        viewport_pos = self._to_list_viewport_pos(current_pos)
        if viewport_pos is not None and self.list_widget is not None:
            self.list_widget.update_drop_indicator_from_pos(viewport_pos)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.LeftButton:
            super().mouseReleaseEvent(event)
            return

        was_dragging = self._dragging
        current_pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        self._dragging = False
        self._press_pos = None

        if not was_dragging:
            self.clicked.emit()
            super().mouseReleaseEvent(event)
            return

        # Kết thúc kéo: nhả grab + trả lại con trỏ trước, vì sau khi phát
        # tín hiệu bên dưới, dòng này (self) có thể bị hủy và tạo lại mới
        # hoàn toàn ngay lập tức nếu chính nó là dòng được kéo đi (xem
        # _move_row) — nên phải làm hết mọi việc cần đến `self` TRƯỚC khi
        # emit, và không được đụng tới `self` sau dòng emit.
        self.releaseMouse()
        self.setCursor(Qt.PointingHandCursor)

        list_widget = self.list_widget
        source_index = self.current_index()
        list_widget.clear_drop_indicator() if list_widget is not None else None
        viewport_pos = self._to_list_viewport_pos(current_pos)
        target_index = (
            list_widget.compute_drop_index_from_viewport_pos(viewport_pos)
            if (list_widget is not None and viewport_pos is not None)
            else None
        )

        if list_widget is not None and source_index is not None and target_index is not None:
            list_widget.row_drag_dropped.emit(source_index, target_index)
            return  # KHÔNG đụng self sau dòng này

        super().mouseReleaseEvent(event)


# ----------------------------------------------------------------------
# Cột B — Thumbnail nhỏ gọn hơn
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
                f"QFrame {{ background-color: {COLOR_ACCENT_LIGHT}; border: 2px solid {COLOR_ACCENT}; border-radius: 6px; }}"
            )
            self.badge.setStyleSheet(
                f"background-color: {COLOR_ACCENT}; color: white; font-size: 10px; font-weight: 700; "
                f"border-radius: {_BADGE_SIZE // 2}px; border: none;"
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
        super().mousePressEvent(event)
        self.clicked.emit(self.page_number)


# ----------------------------------------------------------------------
# Widget chính
# ----------------------------------------------------------------------
class MergeFeatureWidget(QWidget):
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

        # ================= CỘT A (50%) =================
        column_a = QVBoxLayout()
        column_a.setSpacing(14)

        # --- A1: Drop zone ---
        self.drop_zone = _DropZone()
        self.drop_zone.files_selected.connect(self._on_files_selected)
        column_a.addWidget(self.drop_zone)

        # --- A2: Danh sách file ---
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

        # Nút Sắp xếp: Chữ và Icon màu đen (COLOR_TEXT_PRIMARY)
        self.sort_button = QToolButton()
        self.sort_button.setText(" Sắp xếp")
        self.sort_button.setIcon(qta.icon("mdi6.sort", color=COLOR_TEXT_PRIMARY))
        self.sort_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.sort_button.setCursor(Qt.PointingHandCursor)
        self.sort_button.setPopupMode(QToolButton.InstantPopup)
        self.sort_button.setStyleSheet(
            f"""
            QToolButton {{
                background: transparent;
                border: none;
                color: {COLOR_TEXT_PRIMARY};
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
        sort_menu.setStyleSheet(
            f"QMenu {{ background-color: white; color: {COLOR_TEXT_PRIMARY}; border: 1px solid {COLOR_BORDER}; }}"
            f"QMenu::item:selected {{ background-color: #F3F4F6; color: {COLOR_TEXT_PRIMARY}; }}"
        )
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

        # --- A4: Hàng nút bấm (ĐÃ CĂN TRÁI) ---
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

        # Căn trái bằng cách đẩy khoảng trống ra đằng sau
        bottom_row.addStretch()

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
        body_row.setSpacing(10)

        # Thu nhỏ khung scrollbar thumbnail
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setFixedWidth(_THUMB_STRIP_WIDTH)
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setStyleSheet(
            f"QScrollArea {{ background: transparent; border: none; }} {_SCROLLBAR_QSS}"
        )
        self.thumb_container = QWidget()
        self.thumb_container.setStyleSheet("background: transparent;")
        self.thumb_layout = QVBoxLayout(self.thumb_container)
        self.thumb_layout.setContentsMargins(2, 2, 6, 2)
        self.thumb_layout.setSpacing(10)
        self.thumb_layout.setAlignment(Qt.AlignTop)
        self.thumb_scroll.setWidget(self.thumb_container)
        body_row.addWidget(self.thumb_scroll)

        # Mở rộng vùng preview chính
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

        # Ghép 2 cột theo tỉ lệ chuẩn 50 / 50
        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, 40)
        root_layout.addWidget(column_b_widget, 60)

        for f in _MOCK_FILES:
            self._add_file_row(f["name"], f["size"], f["pages"])
        self._select_first_available()

    # ------------------------------------------------------------------
    # Quản lý danh sách file
    # ------------------------------------------------------------------
    def _add_file_row(
        self, name: str, size_text: str, pages: int, index: Optional[int] = None
    ) -> _FileRow:
        """Tạo 1 dòng file mới. Nếu `index` được truyền vào, chèn tại đúng
        vị trí đó thay vì luôn thêm vào cuối danh sách (dùng khi kéo-thả sắp
        xếp lại thứ tự, xem `_move_row`)."""
        row = _FileRow(name, size_text, pages)
        item = QListWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        item.setSizeHint(row.sizeHint())
        if index is None:
            self.file_list.addItem(item)
        else:
            self.file_list.insertItem(index, item)
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
        """Sắp xếp lại thứ tự file khi kéo-thả.

        LƯU Ý QUAN TRỌNG (nguyên nhân lỗi cũ): Qt tự động HỦY (delete) ở tầng
        C++ widget đã gắn qua `setItemWidget()` ngay khi item chứa nó bị lấy
        ra khỏi QListWidget bằng `takeItem()` — đây là cơ chế "persistent
        editor" nội bộ của Qt, không liên quan gì đến Python giữ hay không
        giữ reference tới widget đó. Vì vậy KHÔNG được lấy item ra rồi chèn
        lại và gắn lại đúng instance `_FileRow` cũ như trước đây — widget đó
        đã là "xác chết" (C++ object đã bị xóa), dùng lại sẽ khiến dòng file
        biến mất khỏi giao diện ngay lập tức, và crash với
        `RuntimeError: ... already deleted` ngay khi có thao tác tiếp theo
        chạm vào nó (VD: click chọn dòng, đổi style...).

        Cách khắc phục: đọc dữ liệu (tên, size, số trang) từ dòng cũ trước,
        xóa hẳn dòng cũ, rồi tạo MỚI hoàn toàn 1 `_FileRow` khác và chèn vào
        đúng vị trí đích — giống đúng cách `_sort_files` đang làm.
        """
        count = self.file_list.count()
        if from_index < 0 or from_index >= count or to_index < 0:
            return

        # `to_index` được _DraggableFileList.compute_drop_index_from_viewport_pos()
        # tính trên
        # danh sách ĐẦY ĐỦ (còn cả dòng nguồn). Nếu đích nằm sau nguồn, cần
        # lùi lại 1 để khớp với danh sách sau khi đã bớt đi dòng nguồn.
        if to_index > from_index:
            to_index -= 1
        if to_index == from_index:
            return  # thả lại đúng vị trí cũ -> không làm gì

        old_item = self.file_list.item(from_index)
        old_row = self.file_list.itemWidget(old_item)
        if old_row is None:
            return

        # Lưu lại dữ liệu + trạng thái đang chọn của dòng cũ trước khi nó bị hủy
        name, size_text, pages = old_row.name, old_row.size_text, old_row.pages
        was_selected = old_row is self._selected_row
        if was_selected:
            self._selected_row = None

        self.file_list.takeItem(from_index)  # widget cũ sẽ bị Qt tự hủy ở đây

        # Giới hạn vị trí chèn hợp lệ sau khi danh sách đã ngắn đi 1 phần tử
        target_index = max(0, min(to_index, self.file_list.count()))
        new_row = self._add_file_row(name, size_text, pages, index=target_index)

        if was_selected:
            self._select_row(new_row)

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
            wrapper_layout.setSpacing(2)

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
            self.prev_page_btn.setEnabled(False)
            self.next_page_btn.setEnabled(False)
            return

        self.prev_page_btn.setEnabled(self._current_page > 1)
        self.next_page_btn.setEnabled(self._current_page < self._current_total_pages)

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