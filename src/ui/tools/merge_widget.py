"""
Giao diện tính năng Gộp File (Merge) — đã nối logic thật với src/pdf_core.py
(Nhóm A dùng chung: PDFDocument/CorruptedFileError/PasswordProtectedError/
FileLockedError, get_page_count, list_page_infos, PageRenderer, merge_pdfs —
không sửa gì trong pdf_core.py).

Cột B: khung xem trước lớn là 1 khung cuộn liên tục nhiều trang (giống Cột B
của tính năng Tách file) — cuộn chuột bình thường để xem, kéo chuột trái để pan
khi đã zoom to hơn khung. Click 1 thumbnail ở dải trái sẽ cuộn khung lớn tới đúng
trang đó (đồng bộ 1 chiều: click thumbnail → cuộn khung lớn; cuộn tay tự do không
đồng bộ ngược lại dải thumbnail). Zoom In/Out ±15% (50%-200%) đặt cùng hàng tiêu đề.
Ảnh thumbnail/trang render nền qua QThread (_MergePreviewWorker), không chặn UI.

Cột A: vạch chỉ vị trí kéo-thả file (sắp xếp danh sách) màu đỏ, có vùng đệm quanh
tâm mỗi dòng để tránh nhấp nháy khi rê chuột nhẹ quanh điểm giữa. Có ô nhập tên
file kết quả (gợi ý sẵn PDF_Merger.pdf) — bấm "Gộp File" sẽ hỏi thư mục lưu, kiểm
tra trùng tên (Ghi đè / Đổi tên khác / Hủy) rồi gọi merge_pdfs().

Khung trang trong Cột B không highlight viền cam khi "đang chọn" — giữ nguyên 1
kiểu hiển thị, không cần trạng thái hover/current riêng cho nội dung preview.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QThread, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QDesktopServices
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QScrollArea,
    QFrame,
    QFileDialog,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
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

# Nhóm A (dùng chung với Tách file) — chỉ IMPORT, không sửa nội dung pdf_core.py.
from src.pdf_core import (
    CorruptedFileError,
    PasswordProtectedError,
    FileLockedError,
    PageInfo,
    get_page_count,
    list_page_infos,
    PageRenderer,
    merge_pdfs,
)

# ----------------------------------------------------------------------
# Hằng số nghiệp vụ
# ----------------------------------------------------------------------
# Tên file gợi ý mặc định (02_dac_ta_tinh_nang.md mục 2) — vẫn cho sửa qua ô nhập.
_DEFAULT_OUTPUT_NAME = "PDF_Merger.pdf"

# Render thumbnail ở độ phân giải cao hơn kích thước hiển thị (72px) để nét khi
# hiển thị trên màn hình mật độ điểm ảnh cao.
_THUMB_RENDER_WIDTH = 220
# Render khung xem trước lớn 1 lần ở độ phân giải cao, tái sử dụng khi Zoom
# (setFixedSize co giãn khung chứa, không cần render lại mỗi lần bấm Zoom).
_DETAIL_RENDER_WIDTH = 1200

_ROW_ICON_SIZE = 34
_HANDLE_ICON_SIZE = 18
_PILL_BG = "#F3F4F6"
_DROPZONE_ICON_BOX = 56

# Đã thu nhỏ thumbnail để dành diện tích cho xem trước
_THUMB_STRIP_WIDTH = 115
_THUMB_W, _THUMB_H = 72, 94
# Khoảng thụt vào giữa ảnh thumbnail và mép frame — chừa chỗ cho viền/màu nền
# accent khi "đang chọn" hiển thị rõ (xem _PreviewThumb).
_THUMB_BORDER_INSET = 3
_BADGE_SIZE = 18
_DRAG_THRESHOLD = 8
# Đường kẻ báo vị trí sẽ chèn file khi kéo-thả (kiểu PowerPoint) — màu đỏ để tách
# biệt rõ với màu Accent cam đang dùng cho trạng thái "đang chọn".
_DROP_INDICATOR_COLOR = COLOR_ERROR
_DROP_INDICATOR_HEIGHT = 4
_DROP_INDICATOR_DOT_SIZE = 10
# Vùng đệm quanh tâm mỗi dòng (tỉ lệ theo chiều cao dòng) — trong vùng này giữ
# nguyên vị trí vạch đang hiển thị, chỉ đổi khi chuột vượt hẳn ra khỏi vùng đệm,
# tránh vạch nhấp nháy đổi vị trí liên tục khi rê chuột nhẹ quanh điểm giữa.
_DROP_DEADZONE_RATIO = 0.20

# Zoom Cột B: mỗi lần bấm Zoom In/Out ±15%, giới hạn 50%-200%.
# Mặc định 100% = chiều rộng "vừa khít khung hiển thị" hiện tại (đồng bộ với Split).
_ZOOM_MIN = 0.5
_ZOOM_MAX = 2.0
_ZOOM_STEP = 0.15
_ZOOM_DEFAULT = 1.0

# Lề trái/phải giữa nội dung preview và biên khung Cột B.
_PREVIEW_SIDE_MARGIN = 12
_PREVIEW_MIN_PAGE_WIDTH = 220
# Tỉ lệ khung hình dự phòng — chỉ dùng khi không đọc được kích thước trang thật
# (VD lỗi đọc file khi build khung rỗng trước lúc render).
_PREVIEW_PAGE_WIDTH_FALLBACK = 340
_PREVIEW_PAGE_HEIGHT_DEFAULT = 460

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


def _format_file_size(num_bytes: int) -> str:
    """Đổi dung lượng byte thật của file (os.path.getsize) sang chuỗi hiển thị,
    cùng định dạng với _parse_size_to_mb ở trên (VD "2.4 MB", "956 KB")."""
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{max(1, round(num_bytes / 1024))} KB"


def _ensure_pdf_extension(name: str) -> str:
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def _zoom_button_style() -> str:
    """Style cho 2 nút Zoom In/Out ở header Cột B — đồng bộ với split_widget.py."""
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
        icon_label.setPixmap(qta.icon("mdi6.tray-arrow-up", color=COLOR_ACCENT).pixmap(QSize(28, 28)))
        icon_label.setAlignment(Qt.AlignCenter)
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
    row_drag_dropped = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFrameShape(QFrame.NoFrame)
        # Giãn khoảng cách giữa các file (8px) để không bị đè lên nhau
        self.setSpacing(8)
        self.setStyleSheet(
            f"""
            QListWidget {{ background: transparent; border: none; }}
            QListWidget::item {{ background: transparent; border: none; padding: 0px; }}
            QListWidget::item:selected {{ background: transparent; }}
            {_SCROLLBAR_QSS}
            """
        )
        self._drop_indicator_index: Optional[int] = None

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
        if self.count() == 0:
            return 0
        item = self.itemAt(pos)
        if item is None:
            first_rect = self.visualItemRect(self.item(0))
            if pos.y() < first_rect.top():
                return 0
            return self.count()

        index = self.row(item)
        rect = self.visualItemRect(item)
        center_y = rect.center().y()

        # Vùng đệm quanh tâm dòng: nếu lần tính trước đã "chốt" 1 trong 2 khả năng
        # của đúng dòng này (trước dòng = index, hoặc sau dòng = index + 1), và
        # chuột vẫn còn trong vùng đệm quanh tâm, giữ nguyên kết quả cũ — tránh
        # vạch nhấp nháy đổi vị trí liên tục khi rê chuột nhẹ quanh điểm giữa.
        deadzone = max(1, round(rect.height() * _DROP_DEADZONE_RATIO))
        previous = self._drop_indicator_index
        if previous is not None and previous in (index, index + 1):
            if center_y - deadzone <= pos.y() <= center_y + deadzone:
                return previous

        if pos.y() > center_y:
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
    def __init__(self, owner_row: "_FileRow", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.owner_row = owner_row
        self.setPixmap(qta.icon("mdi6.drag-vertical", color=COLOR_TEXT_SECONDARY).pixmap(QSize(_HANDLE_ICON_SIZE, _HANDLE_ICON_SIZE)))
        self.setFixedSize(_HANDLE_ICON_SIZE, _HANDLE_ICON_SIZE)
        self.setCursor(Qt.OpenHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)


# ----------------------------------------------------------------------
# A3 — 1 dòng trong danh sách file
# ----------------------------------------------------------------------
class _FileRow(QFrame):
    clicked = Signal()
    remove_requested = Signal()

    def __init__(self, path: str, name: str, size_text: str, pages: int,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.path = path
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
                    border: 1px solid {COLOR_ACCENT};
                    border-radius: 8px;
                }}
                """
            )
        else:
            self.setStyleSheet(
                f"""
                _FileRow {{
                    background-color: white;
                    border: 1px solid {COLOR_BORDER};
                    border-radius: 8px;
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
        if self.list_widget is None:
            return None
        global_pos = self.mapToGlobal(local_pos)
        return self.list_widget.viewport().mapFromGlobal(global_pos)

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

        self.releaseMouse()
        self.setCursor(Qt.PointingHandCursor)

        list_widget = self.list_widget
        source_index = self.current_index()
        viewport_pos = self._to_list_viewport_pos(current_pos)
        # Tính target_index TRƯỚC khi xoá vạch chỉ thị — để vùng đệm (dead-zone)
        # dùng đúng giá trị đang hiển thị lúc thả chuột, tránh trường hợp vạch cho
        # thấy 1 vị trí nhưng lúc thả lại chèn vào vị trí khác do bị reset về None.
        target_index = (
            list_widget.compute_drop_index_from_viewport_pos(viewport_pos)
            if (list_widget is not None and viewport_pos is not None)
            else None
        )
        if list_widget is not None:
            list_widget.clear_drop_indicator()

        if list_widget is not None and source_index is not None and target_index is not None:
            list_widget.row_drag_dropped.emit(source_index, target_index)
            return

        super().mouseReleaseEvent(event)


# ----------------------------------------------------------------------
# Cột B — Thumbnail nhỏ gọn (dải trái, dùng làm "mục lục" nhảy nhanh)
# ----------------------------------------------------------------------
class _PreviewThumb(QFrame):
    clicked = Signal(int)

    def __init__(self, page_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.is_current = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(_THUMB_W, _THUMB_H)

        # Ảnh thumbnail thật — đặt làm nền, nằm dưới badge số trang. Thụt vào so
        # với mép frame (không phủ kín 0,0→W,H) để viền + màu nền accent khi
        # "đang chọn" (_apply_style) vẫn hiển thị được, không bị ảnh đè mất.
        inset = _THUMB_BORDER_INSET
        self.image_label = QLabel(self)
        self.image_label.setGeometry(
            inset, inset, _THUMB_W - inset * 2, _THUMB_H - inset * 2
        )
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setScaledContents(True)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        self.image_label.lower()

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

    def set_image(self, pixmap: QPixmap) -> None:
        self.image_label.setPixmap(pixmap)

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
# Cột B — QScrollArea hỗ trợ kéo bằng chuột trái (pan) khi nội dung vượt khung,
# và phát tín hiệu khi kích thước viewport đổi để widget cha tính lại chiều rộng
# trang preview cho vừa khung (responsive fit-width). Đồng bộ với split_widget.py.
# ----------------------------------------------------------------------
class _PannablePreviewScrollArea(QScrollArea):
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
        if hasattr(event, "position"):
            return event.position().toPoint()
        return event.pos()

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
# Cột B — 1 trang trong khung xem trước lớn, hiển thị ảnh trang PDF thật
# ----------------------------------------------------------------------
class _MergePreviewPage(QFrame):
    """1 khung trang trong danh sách cuộn liên tục bên phải — hiển thị ảnh trang
    thật (render nền qua PageRenderer). Không highlight viền cam khi "đang chọn"
    (khác với dải thumbnail trái) — nội dung preview giữ nguyên 1 kiểu, không cần
    trạng thái hover/current riêng."""

    def __init__(self, page_number: int, aspect_ratio: float,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.aspect_ratio = aspect_ratio

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

    def set_image(self, pixmap: QPixmap) -> None:
        self.image_label.setPixmap(pixmap)


# ----------------------------------------------------------------------
# Worker render nền cho Cột B — theo đúng luồng đã chốt ở
# 04_kien_truc_module_va_flow.md mục 5: list_page_infos đọc metadata đồng bộ để
# dựng khung trước, ảnh thật (thumbnail + trang lớn) render nền qua QThread để
# không chặn UI. Chỉ dùng PageRenderer sẵn có của pdf_core (Nhóm A), không sửa gì.
# ----------------------------------------------------------------------
class _MergePreviewWorker(QThread):
    thumb_ready = Signal(int, int, bytes)   # token, page_index (0-based), PNG bytes
    page_ready = Signal(int, int, bytes)    # token, page_index (0-based), PNG bytes
    render_error = Signal(int, str)         # token, message

    def __init__(self, token: int, path: str, page_indexes: List[int],
                 renderer: PageRenderer, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.token = token
        self.path = path
        self.page_indexes = page_indexes
        self.renderer = renderer
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def run(self) -> None:
        for page_index in self.page_indexes:
            if self._cancelled:
                return
            try:
                thumb_bytes = self.renderer.render_thumbnail(
                    self.path, page_index, max_width=_THUMB_RENDER_WIDTH
                )
                self.thumb_ready.emit(self.token, page_index, thumb_bytes)
            except (CorruptedFileError, PasswordProtectedError, FileLockedError) as exc:
                self.render_error.emit(self.token, str(exc))
                return
            except Exception:
                # Lỗi render 1 trang lẻ (hiếm) — bỏ qua trang đó, không dừng cả
                # tiến trình render các trang còn lại.
                pass

            if self._cancelled:
                return
            try:
                page_bytes = self.renderer.render_page_detail(
                    self.path, page_index, target_width=_DETAIL_RENDER_WIDTH
                )
                self.page_ready.emit(self.token, page_index, page_bytes)
            except Exception:
                pass


# ----------------------------------------------------------------------
# Widget chính
# ----------------------------------------------------------------------
class MergeFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._selected_row: Optional[_FileRow] = None
        self._current_file_name: Optional[str] = None
        self._current_file_path: Optional[str] = None
        self._current_total_pages = 0
        self._current_page = 0
        self._preview_thumbs: List[_PreviewThumb] = []

        # Danh sách khung trang lớn (Cột B) + trạng thái zoom.
        self._preview_pages: Dict[int, _MergePreviewPage] = {}
        self._zoom_level: float = _ZOOM_DEFAULT
        self._current_preview_width: Optional[int] = None
        # Trang được dựng ngay trong __init__ (trước khi cửa sổ hiển thị xong),
        # lúc đó viewport().width() đọc được còn sai (quá nhỏ) nên chiều rộng trang
        # bị tính sai theo → cần tính lại đúng 1 lần khi widget thật sự hiển thị.
        self._initial_width_applied = False

        # Render nền cho Cột B (xem 04_kien_truc_module_va_flow.md mục 5).
        self._renderer = PageRenderer()
        self._render_worker: Optional[_MergePreviewWorker] = None
        self._render_token = 0

        # Lưu lại lần gộp gần nhất để nút "Thử lại" (lỗi FileLockedError) không
        # phải bắt người dùng chọn lại thư mục/tên file từ đầu.
        self._last_merge_attempt: Optional[Tuple[List[str], str]] = None

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

        # --- A3: Tên file kết quả (đã chốt ở 02_dac_ta_tinh_nang.md mục 2 —
        # gợi ý sẵn "PDF_Merger.pdf", người dùng sửa được) ---
        name_block = QVBoxLayout()
        name_block.setSpacing(6)

        name_label = QLabel("Tên file kết quả")
        name_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        name_block.addWidget(name_label)

        self.output_name_edit = QLineEdit(_DEFAULT_OUTPUT_NAME)
        self.output_name_edit.setFixedHeight(CONTROL_HEIGHT)
        self.output_name_edit.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                padding: 0 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {COLOR_ACCENT}; }}
            """
        )
        name_block.addWidget(self.output_name_edit)

        column_a.addLayout(name_block)

        # --- A4: Hàng nút bấm ---
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

        bottom_row.addStretch()
        column_a.addLayout(bottom_row)

        result_row = QHBoxLayout()
        result_row.setSpacing(8)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        result_row.addWidget(self.result_label, 1)

        # Nút "Thử lại" — chỉ hiện khi lỗi ghi file do bị khóa bởi chương trình
        # khác (02_dac_ta_tinh_nang.md mục 6), bấm để ghi lại đúng file/thư mục
        # vừa chọn mà không bắt chọn lại từ đầu.
        self.retry_button = QPushButton("Thử lại")
        self.retry_button.setCursor(Qt.PointingHandCursor)
        self.retry_button.setFixedHeight(28)
        self.retry_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 12px;
            }}
            QPushButton:hover {{ background-color: #E28104; }}
            """
        )
        self.retry_button.clicked.connect(self._retry_last_merge)
        self.retry_button.hide()
        result_row.addWidget(self.retry_button)

        column_a.addLayout(result_row)

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

        # Cụm Zoom Out / % / Zoom In — thay cho nút chuyển trang cũ (◀ X/Y ▶),
        # vì giờ xem trang bằng cách cuộn chuột liên tục thay vì nhảy từng trang.
        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_out_btn.setIcon(qta.icon("mdi6.magnify-minus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_out_btn.setIconSize(QSize(16, 16))
        self.zoom_out_btn.setFixedSize(26, 26)
        self.zoom_out_btn.setStyleSheet(_zoom_button_style())
        self.zoom_out_btn.setToolTip("Thu nhỏ (-15%)")
        self.zoom_out_btn.clicked.connect(self._on_zoom_out_clicked)
        header_row.addWidget(self.zoom_out_btn)

        self.zoom_percent_label = QLabel(f"{round(_ZOOM_DEFAULT * 100)}%")
        self.zoom_percent_label.setAlignment(Qt.AlignCenter)
        self.zoom_percent_label.setFixedWidth(42)
        self.zoom_percent_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        header_row.addWidget(self.zoom_percent_label)

        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_in_btn.setIcon(qta.icon("mdi6.magnify-plus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_in_btn.setIconSize(QSize(16, 16))
        self.zoom_in_btn.setFixedSize(26, 26)
        self.zoom_in_btn.setStyleSheet(_zoom_button_style())
        self.zoom_in_btn.setToolTip("Phóng to (+15%)")
        self.zoom_in_btn.clicked.connect(self._on_zoom_in_clicked)
        header_row.addWidget(self.zoom_in_btn)

        preview_card_layout.addLayout(header_row)

        body_row = QHBoxLayout()
        body_row.setSpacing(10)

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

        # Khung xem trước lớn — cuộn liên tục nhiều trang (thay cho khung 1 trang cố
        # định trước đây), dùng _PannablePreviewScrollArea để hỗ trợ cuộn chuột +
        # kéo chuột trái (pan) khi đã zoom to hơn khung, đồng bộ với split_widget.py.
        self.preview_scroll_b = _PannablePreviewScrollArea()
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
        self.preview_scroll_b.viewport_resized.connect(self._on_preview_viewport_resized)

        preview_pages_container = QWidget()
        preview_pages_container.setStyleSheet("background: transparent;")
        self.preview_layout = QVBoxLayout(preview_pages_container)
        self.preview_layout.setContentsMargins(
            _PREVIEW_SIDE_MARGIN, 12, _PREVIEW_SIDE_MARGIN, 12
        )
        self.preview_layout.setSpacing(16)
        self.preview_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.preview_scroll_b.setWidget(preview_pages_container)

        body_row.addWidget(self.preview_scroll_b, 1)

        preview_card_layout.addLayout(body_row, 1)
        column_b.addWidget(preview_card, 1)

        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, 40)
        root_layout.addWidget(column_b_widget, 60)

        self._select_first_available()
        self._update_zoom_buttons_state()
        self._update_zoom_percent_label()

    # ------------------------------------------------------------------
    # Quản lý danh sách file
    # ------------------------------------------------------------------
    def _add_file_row(
        self, path: str, name: str, size_text: str, pages: int,
        index: Optional[int] = None
    ) -> _FileRow:
        row = _FileRow(path, name, size_text, pages)
        item = QListWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        
        # Đặt QSize cố định để QListWidget tính toán chiều cao không bị đè
        item.setSizeHint(QSize(0, 66))
        
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
        count = self.file_list.count()
        if from_index < 0 or from_index >= count or to_index < 0:
            return

        if to_index > from_index:
            to_index -= 1
        if to_index == from_index:
            return

        old_item = self.file_list.item(from_index)
        old_row = self.file_list.itemWidget(old_item)
        if old_row is None:
            return

        path, name, size_text, pages = (
            old_row.path, old_row.name, old_row.size_text, old_row.pages
        )
        was_selected = old_row is self._selected_row
        if was_selected:
            self._selected_row = None

        self.file_list.takeItem(from_index)

        target_index = max(0, min(to_index, self.file_list.count()))
        new_row = self._add_file_row(path, name, size_text, pages, index=target_index)

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
                self.file_list.itemWidget(self.file_list.item(i)).path,
                self.file_list.itemWidget(self.file_list.item(i)).name,
                self.file_list.itemWidget(self.file_list.item(i)).size_text,
                self.file_list.itemWidget(self.file_list.item(i)).pages,
            )
            for i in range(self.file_list.count())
        ]
        if key == "name":
            rows_data.sort(key=lambda r: r[1].lower())
        elif key == "size":
            rows_data.sort(key=lambda r: _parse_size_to_mb(r[2]), reverse=True)
        elif key == "pages":
            rows_data.sort(key=lambda r: r[3], reverse=True)

        # Dùng path (không dùng name) để chọn lại đúng file sau khi sắp xếp —
        # tránh nhầm khi 2 file trùng tên nhưng khác thư mục nguồn.
        selected_path = self._selected_row.path if self._selected_row else None
        self.file_list.clear()
        self._selected_row = None
        for path, name, size_text, pages in rows_data:
            new_row = self._add_file_row(path, name, size_text, pages)
            if path == selected_path:
                self._select_row(new_row)
        if self._selected_row is None:
            self._select_first_available()

    # ------------------------------------------------------------------
    # Sự kiện
    # ------------------------------------------------------------------
    def _on_files_selected(self, paths: List[str]) -> None:
        # Theo 02_dac_ta_tinh_nang.md mục 6: file hỏng/có mật khẩu bị loại khỏi
        # danh sách, báo lỗi rõ ràng, không crash, vẫn thêm tiếp các file hợp lệ.
        skipped: List[str] = []
        for path in paths:
            name = os.path.basename(path)
            try:
                pages = get_page_count(path)
            except PasswordProtectedError:
                skipped.append(f"{name} (có mật khẩu)")
                continue
            except CorruptedFileError:
                skipped.append(f"{name} (không đọc được, file có thể bị hỏng)")
                continue
            except Exception as exc:
                skipped.append(f"{name} ({exc})")
                continue

            try:
                size_text = _format_file_size(os.path.getsize(path))
            except OSError:
                size_text = "--"

            self._add_file_row(path, name, size_text, pages)

        if self._selected_row is None:
            self._select_first_available()

        if skipped:
            self._show_error(
                f"Không thể thêm {len(skipped)} file: " + "; ".join(skipped)
            )
        else:
            self._hide_result()

    def _on_clear_clicked(self) -> None:
        self.file_list.clear()
        self._selected_row = None
        self._last_merge_attempt = None
        self._update_header_count()
        self._zoom_level = _ZOOM_DEFAULT
        self._show_empty_preview()
        self._update_zoom_percent_label()
        self._hide_result()

    def _on_merge_clicked(self) -> None:
        count = self.file_list.count()
        if count < 2:
            self._show_error("Vui lòng chọn ít nhất 2 file PDF để gộp.")
            return

        ordered_paths = [
            self.file_list.itemWidget(self.file_list.item(i)).path
            for i in range(count)
        ]

        output_name = _ensure_pdf_extension(
            self.output_name_edit.text().strip() or _DEFAULT_OUTPUT_NAME
        )

        # Theo 02_dac_ta_tinh_nang.md mục 0: người dùng tự chọn thư mục lưu,
        # không mặc định cứng.
        output_dir = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu kết quả")
        if not output_dir:
            return

        output_path = os.path.join(output_dir, output_name)

        if os.path.exists(output_path):
            decision = self._ask_overwrite_decision(output_name)
            if decision == "cancel":
                return
            if decision == "rename":
                new_name_raw, ok = self._prompt_new_name(output_name)
                if not ok or not new_name_raw.strip():
                    return
                new_name = _ensure_pdf_extension(new_name_raw.strip())
                output_path = os.path.join(output_dir, new_name)
                if os.path.exists(output_path):
                    self._show_error(
                        f"Tên '{new_name}' cũng đã tồn tại trong thư mục này. "
                        "Vui lòng bấm Gộp File lại và chọn tên khác."
                    )
                    return
            # decision == "overwrite": giữ nguyên output_path, ghi đè khi lưu.

        self._write_merged_file(ordered_paths, output_path)

    def _write_merged_file(self, ordered_paths: List[str], output_path: str) -> None:
        self._last_merge_attempt = (ordered_paths, output_path)
        try:
            merge_pdfs(ordered_paths, output_path)
        except FileLockedError:
            self._show_error(
                "File đang được sử dụng bởi chương trình khác, vui lòng đóng và thử lại.",
                retryable=True,
            )
            return
        except (CorruptedFileError, PasswordProtectedError) as exc:
            self._show_error(f"Không thể gộp file: {exc}")
            return
        except Exception as exc:
            self._show_error(f"Lỗi không xác định khi gộp file: {exc}")
            return

        self._last_merge_attempt = None
        self._show_success(f"Đã gộp {len(ordered_paths)} file thành công → {output_path}")
        # Tự động mở thư mục kết quả (Windows Explorer) — đồng bộ hành vi với
        # tính năng Tách file (04_kien_truc_module_va_flow.md mục 5).
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(output_path)))

    def _retry_last_merge(self) -> None:
        if self._last_merge_attempt is None:
            return
        ordered_paths, output_path = self._last_merge_attempt
        self._write_merged_file(ordered_paths, output_path)

    def _ask_overwrite_decision(self, file_name: str) -> str:
        """Popup style riêng (không dùng mặc định) theo 01_dac_ta_giao_dien.md
        mục 3: nền trắng, chữ tối màu, nút Accent cho hành động chính. 3 lựa chọn
        theo 02_dac_ta_tinh_nang.md mục 6: Ghi đè / Đổi tên khác / Hủy."""
        box = QMessageBox(self)
        box.setWindowTitle("Trùng tên file")
        box.setIcon(QMessageBox.Warning)
        box.setText(
            f"File '{file_name}' đã tồn tại trong thư mục đã chọn.\nBạn muốn làm gì?"
        )
        box.setStyleSheet(
            f"""
            QMessageBox {{ background-color: white; }}
            QMessageBox QLabel {{ color: {COLOR_TEXT_PRIMARY}; font-size: 13px; }}
            QPushButton {{
                background-color: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 600;
                min-width: 96px;
            }}
            QPushButton:hover {{ background-color: #F3F4F6; }}
            """
        )

        overwrite_btn = box.addButton("Ghi đè", QMessageBox.AcceptRole)
        overwrite_btn.setStyleSheet(
            f"background-color: {COLOR_ACCENT}; color: white; border: none; "
            f"border-radius: {CORNER_RADIUS}px; padding: 6px 14px; font-size: 13px; "
            "font-weight: 700; min-width: 96px;"
        )
        rename_btn = box.addButton("Đổi tên khác", QMessageBox.ActionRole)
        box.addButton("Hủy", QMessageBox.RejectRole)
        box.setDefaultButton(overwrite_btn)
        box.exec()

        clicked = box.clickedButton()
        if clicked is overwrite_btn:
            return "overwrite"
        if clicked is rename_btn:
            return "rename"
        return "cancel"

    def _prompt_new_name(self, current_name: str) -> Tuple[str, bool]:
        dialog = QInputDialog(self)
        dialog.setWindowTitle("Đổi tên file kết quả")
        dialog.setLabelText("Nhập tên file mới:")
        dialog.setTextValue(current_name)
        dialog.setStyleSheet(
            f"""
            QInputDialog {{ background-color: white; }}
            QLabel {{ color: {COLOR_TEXT_PRIMARY}; font-size: 13px; background: transparent; }}
            QLineEdit {{
                background-color: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                padding: 4px 8px;
                font-size: 13px;
            }}
            QPushButton {{
                background-color: {COLOR_ACCENT};
                color: white;
                border: none;
                border-radius: {CORNER_RADIUS}px;
                padding: 6px 14px;
                font-size: 13px;
                font-weight: 700;
                min-width: 84px;
            }}
            QPushButton:hover {{ background-color: #E28104; }}
            """
        )
        ok = dialog.exec() == QInputDialog.Accepted
        return dialog.textValue(), ok

    # ------------------------------------------------------------------
    # Xem trước (Cột B)
    # ------------------------------------------------------------------
    def _select_row(self, row: _FileRow) -> None:
        if self._selected_row is not None:
            self._selected_row.set_selected(False)
        row.set_selected(True)
        self._selected_row = row
        self._load_preview(row.path)

    def _select_first_available(self) -> None:
        if self.file_list.count() == 0:
            self._selected_row = None
            self._show_empty_preview()
            return
        first_item = self.file_list.item(0)
        first_row = self.file_list.itemWidget(first_item)
        self._select_row(first_row)

    def _load_preview(self, path: str) -> None:
        """Theo đúng luồng đã chốt ở 04_kien_truc_module_va_flow.md mục 5:
        list_page_infos đọc metadata thật (đồng bộ, nhanh) để dựng khung trước,
        sau đó ảnh thật render nền qua QThread, không chặn UI."""
        self._cancel_active_render()

        name = os.path.basename(path)
        self._current_file_name = name
        self._current_file_path = path
        self.preview_title.setText(f"Xem trước: {name}")

        try:
            infos = list_page_infos(path)
        except (CorruptedFileError, PasswordProtectedError) as exc:
            self._show_error(f"Không thể xem trước '{name}': {exc}")
            infos = []
        except Exception as exc:
            self._show_error(f"Không thể xem trước '{name}': {exc}")
            infos = []

        self._current_total_pages = len(infos)
        self._current_page = 1 if infos else 0
        self._build_preview_thumbs(infos)
        self._build_preview_pages(infos)
        self._refresh_page_view()

        if infos:
            self._start_render_worker(path, infos)

    def _show_empty_preview(self) -> None:
        self._cancel_active_render()
        self._current_file_name = None
        self._current_file_path = None
        self._current_total_pages = 0
        self._current_page = 0
        self.preview_title.setText("Xem trước: —")
        self._build_preview_thumbs([])
        self._build_preview_pages([])
        self._refresh_page_view()

    def _build_preview_thumbs(self, infos: List[PageInfo]) -> None:
        while self.thumb_layout.count():
            child = self.thumb_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        self._preview_thumbs = []

        for info in infos:
            page_number = info.source_index + 1
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.setSpacing(2)
            wrapper_layout.setAlignment(Qt.AlignTop)

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

            # Khóa cứng chiều cao đúng bằng nội dung thật (thumb + nhãn số) —
            # nếu không, khi tổng số thumbnail ít hơn chiều cao khung cuộn,
            # QScrollArea (setWidgetResizable=True) sẽ kéo container cao lên và
            # layout dồn khoảng trống thừa xen giữa các thumbnail thay vì để
            # trống ở cuối, gây giãn cách bất thường.
            wrapper.setFixedHeight(wrapper.sizeHint().height())

            self.thumb_layout.addWidget(wrapper, alignment=Qt.AlignTop)
            self._preview_thumbs.append(thumb)

    def _build_preview_pages(self, infos: List[PageInfo]) -> None:
        """Dựng lại danh sách khung trang lớn (Cột B) theo file đang chọn — khung
        rỗng dựng trước theo đúng tỉ lệ khung hình thật của từng trang (PageInfo),
        ảnh được điền vào sau khi worker render xong (_on_page_ready)."""
        for frame in self._preview_pages.values():
            self.preview_layout.removeWidget(frame)
            frame.deleteLater()
        self._preview_pages.clear()
        self._current_preview_width = None

        if not infos:
            self._update_zoom_buttons_state()
            return

        width = self._compute_preview_width()
        self._current_preview_width = width
        for info in infos:
            page_number = info.source_index + 1
            # Trang xoay 90/270 độ thì kích thước hiển thị (rộng x cao) đảo chiều
            # so với kích thước gốc trong PDF.
            if info.rotation in (90, 270):
                eff_w, eff_h = info.height, info.width
            else:
                eff_w, eff_h = info.width, info.height
            aspect_ratio = (
                eff_h / eff_w if eff_w else
                _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK
            )

            frame = _MergePreviewPage(page_number, aspect_ratio)
            height = round(width * aspect_ratio)
            frame.setFixedSize(width, height)
            self.preview_layout.addWidget(frame, alignment=Qt.AlignHCenter)
            self._preview_pages[page_number] = frame

        self._update_zoom_buttons_state()

    # ------------------------------------------------------------------
    # Render nền (QThread) cho Cột B
    # ------------------------------------------------------------------
    def _cancel_active_render(self) -> None:
        if self._render_worker is not None:
            self._render_worker.cancel()
            self._render_worker.wait()
            self._render_worker = None

    def _start_render_worker(self, path: str, infos: List[PageInfo]) -> None:
        self._render_token += 1
        token = self._render_token
        page_indexes = [info.source_index for info in infos]
        worker = _MergePreviewWorker(token, path, page_indexes, self._renderer, self)
        worker.thumb_ready.connect(self._on_thumb_ready)
        worker.page_ready.connect(self._on_page_ready)
        worker.render_error.connect(self._on_render_error)
        worker.finished.connect(lambda w=worker: self._on_worker_finished(w))
        self._render_worker = worker
        worker.start()

    def _on_worker_finished(self, worker: _MergePreviewWorker) -> None:
        if self._render_worker is worker:
            self._render_worker = None
        worker.deleteLater()

    def _on_thumb_ready(self, token: int, page_index: int, data: bytes) -> None:
        if token != self._render_token:
            return  # đã chuyển sang file khác — bỏ kết quả cũ
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        if 0 <= page_index < len(self._preview_thumbs):
            self._preview_thumbs[page_index].set_image(pixmap)

    def _on_page_ready(self, token: int, page_index: int, data: bytes) -> None:
        if token != self._render_token:
            return
        pixmap = QPixmap()
        pixmap.loadFromData(data, "PNG")
        frame = self._preview_pages.get(page_index + 1)
        if frame is not None:
            frame.set_image(pixmap)

    def _on_render_error(self, token: int, message: str) -> None:
        if token != self._render_token:
            return
        self._show_error(f"Lỗi khi render xem trước: {message}")

    def _on_thumb_clicked(self, page_number: int) -> None:
        self._current_page = page_number
        self._refresh_page_view()

    def _refresh_page_view(self) -> None:
        # Dải thumbnail trái: highlight đúng trang + cuộn cho thấy trang đó.
        for thumb in self._preview_thumbs:
            thumb.set_current(thumb.page_number == self._current_page)
        if 0 <= self._current_page - 1 < len(self._preview_thumbs):
            current_thumb = self._preview_thumbs[self._current_page - 1]
            self.thumb_scroll.ensureWidgetVisible(current_thumb, 0, 20)

        # Khung lớn Cột B: chỉ cuộn tới đúng trang, không highlight viền (nội dung
        # preview giữ nguyên 1 kiểu, không cần trạng thái hover/current riêng).
        # Lưu ý: đây là đồng bộ 1 chiều — cuộn tay tự do trong khung lớn không
        # cập nhật ngược lại highlight ở dải thumbnail trái (đã thống nhất với đại ca).
        current_frame = self._preview_pages.get(self._current_page)
        if current_frame is not None:
            self.preview_scroll_b.ensureWidgetVisible(current_frame, 0, 0)

    # ------------------------------------------------------------------
    # Zoom cho khung xem trước lớn (Cột B) — đồng bộ với split_widget.py
    # ------------------------------------------------------------------
    def _fit_base_width(self) -> int:
        viewport_width = self.preview_scroll_b.viewport().width()
        usable = viewport_width - (_PREVIEW_SIDE_MARGIN * 2)
        return max(_PREVIEW_MIN_PAGE_WIDTH, usable)

    def _compute_preview_width(self) -> int:
        base_width = self._fit_base_width()
        return max(_PREVIEW_MIN_PAGE_WIDTH, round(base_width * self._zoom_level))

    def _apply_preview_zoom(self) -> None:
        if not self._preview_pages:
            self._update_zoom_buttons_state()
            self._update_zoom_percent_label()
            return

        new_width = self._compute_preview_width()
        if new_width == self._current_preview_width:
            self._update_zoom_buttons_state()
            self._update_zoom_percent_label()
            return
        self._current_preview_width = new_width

        for frame in self._preview_pages.values():
            new_height = round(new_width * frame.aspect_ratio)
            frame.setFixedSize(new_width, new_height)

        self._update_zoom_buttons_state()
        self._update_zoom_percent_label()

    def _on_zoom_in_clicked(self) -> None:
        self._set_zoom_level(self._zoom_level + _ZOOM_STEP)

    def _on_zoom_out_clicked(self) -> None:
        self._set_zoom_level(self._zoom_level - _ZOOM_STEP)

    def _set_zoom_level(self, new_level: float) -> None:
        clamped = max(_ZOOM_MIN, min(_ZOOM_MAX, round(new_level, 2)))
        if abs(clamped - self._zoom_level) < 1e-6:
            return
        self._zoom_level = clamped
        self._apply_preview_zoom()

    def _update_zoom_buttons_state(self) -> None:
        has_pages = bool(self._preview_pages)
        self.zoom_in_btn.setEnabled(has_pages and self._zoom_level < _ZOOM_MAX - 1e-6)
        self.zoom_out_btn.setEnabled(has_pages and self._zoom_level > _ZOOM_MIN + 1e-6)

    def _update_zoom_percent_label(self) -> None:
        self.zoom_percent_label.setText(f"{round(self._zoom_level * 100)}%")

    def _on_preview_viewport_resized(self) -> None:
        if self._preview_pages:
            self._apply_preview_zoom()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Lần hiển thị đầu tiên: cửa sổ đã có kích thước thật, tính lại chiều rộng
        # trang cho khớp khung Cột B thật sự (sửa lỗi khoảng trắng lớn 2 bên do
        # trang mock bị dựng quá sớm lúc __init__, khi viewport còn chưa có size đúng).
        if not self._initial_width_applied and self._preview_pages:
            self._initial_width_applied = True
            self._current_preview_width = None
            self._apply_preview_zoom()

    # ------------------------------------------------------------------
    def _show_success(self, message: str) -> None:
        self.result_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"✓ {message}")
        self.result_label.show()
        self.retry_button.hide()

    def _show_error(self, message: str, retryable: bool = False) -> None:
        self.result_label.setStyleSheet(f"color: {COLOR_ERROR}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"✕ {message}")
        self.result_label.show()
        self.retry_button.setVisible(retryable)

    def _hide_result(self) -> None:
        self.result_label.hide()
        self.retry_button.hide()