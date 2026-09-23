"""
Giao diện tính năng Đổi tên (Rename) — CHỈ XÂY DỰNG GIAO DIỆN, CHƯA NỐI LOGIC THẬT.

Theo đặc tả đã chốt ở 08_dac_ta_doi_ten.md. Toàn bộ phần "sinh tên file thật"
(rename_engine.py) và "ghi file ra đĩa" đều CHƯA tồn tại — mọi chỗ cần dữ liệu đó
trong file này dùng hàm placeholder `_preview_generate_name()` (đánh dấu rõ TẠM
THỜI ngay tại chỗ khai báo) chỉ để có chữ hiển thị lên bảng xem trước, KHÔNG phải
thuật toán chính thức. Khi sang phiên nối logic thật, thay `_preview_generate_name`
bằng lời gọi `rename_engine.py` thật, giữ nguyên toàn bộ phần UI.

Hồ sơ mẫu (profile) hiện quản lý HOÀN TOÀN trong bộ nhớ (tạo/sửa/xóa qua các dialog
đều hoạt động thật để kiểm tra hiển thị) nhưng CHƯA đọc/ghi `rename_profiles.json`
— file đó chỉ được tạo rỗng cạnh `config.json` (xem 08_dac_ta_doi_ten.md mục 2),
việc đọc/ghi thật sẽ nối ở phiên làm việc khác.

Tái sử dụng đúng phong cách thiết kế của merge_widget.py để đồng bộ giao diện:
DropZone, danh sách file kéo-thả (_DraggableFileList/_FileRow), khung card bo góc
14px viền COLOR_BORDER, control cao 38px bo góc 8px, dialog xác nhận tự vẽ nền
trắng/chữ tối/nút Accent, QMessageBox có stylesheet tường minh.

Cột A: danh sách file đã chọn, kéo-thả đổi thứ tự (thứ tự này quyết định thứ tự
sinh Ngày/Ca/Số thứ tự tự tăng) — TỰ ĐỘNG KHÓA HOÀN TOÀN (không thêm/xóa/kéo-thả
được) ngay khi đã chọn 1 hồ sơ mẫu ở nút "Tạo biểu mẫu", chỉ mở khóa lại khi bấm
"Clear" (đúng bảng 6.1).

Cột B: `QStackedWidget` 2 trang — "Preview" (xem trước trang 1 của file đang chọn
ở Cột A, dùng chung `list_page_infos`/`PageRenderer` với các tính năng khác, đọc
thật — không phải giả) và "Form nhập liệu" (đổi nội dung theo đúng hồ sơ đang chọn:
Vận hành có/không Ca, hoặc Phát sinh nhiều khối).
"""
from __future__ import annotations

import copy
import datetime
import os
import uuid
from typing import Dict, List, Optional, Tuple

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QDate
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QFrame,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QDialog,
    QAbstractItemView,
    QStackedWidget,
    QComboBox,
    QSpinBox,
    QCheckBox,
    QDateEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
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

# Nhóm A (dùng chung với Tách file/Gộp file) — chỉ ĐỌC thông tin file để hiển thị
# preview/số trang, KHÔNG phải logic đổi tên. Không sửa gì trong pdf_core.py.
from src.pdf_core import (
    CorruptedFileError,
    PasswordProtectedError,
    FileLockedError,
    PageInfo,
    get_page_count,
    list_page_infos,
    PageRenderer,
)

# ----------------------------------------------------------------------
# Hằng số nghiệp vụ (xem 08_dac_ta_doi_ten.md)
# ----------------------------------------------------------------------
_MAX_BLOCKS = 4
_MIN_CA_COUNT, _MAX_CA_COUNT = 1, 10
_DEFAULT_CA_COUNT = 3  # GỢI Ý — CẦN ĐẠI CA CHỐT (08_dac_ta_doi_ten.md mục 8)

_BLOCK_TYPE_LABELS = {
    "fixed_text": "Văn bản cố định",
    "auto_number": "Số thứ tự tự tăng",
    "date": "Ngày",
    "manual": "Nhập tay theo từng file",
}
_BLOCK_TYPE_ORDER = ["fixed_text", "auto_number", "date", "manual"]

_ROW_ICON_SIZE = 34
_HANDLE_ICON_SIZE = 18
_BADGE_SIZE = 22
_PILL_BG = "#F3F4F6"
_DROPZONE_ICON_BOX = 56
_DRAG_THRESHOLD = 8
_DROP_INDICATOR_COLOR = COLOR_ERROR
_DROP_INDICATOR_HEIGHT = 4
_DROP_INDICATOR_DOT_SIZE = 10
_DROP_DEADZONE_RATIO = 0.20

_PREVIEW_THUMB_WIDTH = 260

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
        height: 0px; background: transparent; border: none;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
"""

# Tên file JSON lưu hồ sơ — GỢI Ý, đặt cạnh config.json (chưa đọc/ghi thật ở bước
# này, chỉ tạo rỗng nếu chưa có, xem 08_dac_ta_doi_ten.md mục 2 và mục 8).
RENAME_PROFILES_FILE = "rename_profiles.json"


def _format_file_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{max(1, round(num_bytes / 1024))} KB"


def _new_profile_id() -> str:
    return uuid.uuid4().hex[:8]


def _default_block(block_type: str) -> dict:
    """Cấu hình mặc định cho 1 khối mới thêm trong hồ sơ Phát sinh (mục 4)."""
    if block_type == "fixed_text":
        return {"type": "fixed_text", "config": {"value": ""}}
    if block_type == "auto_number":
        return {"type": "auto_number", "config": {"start": 1, "step": 1}}
    if block_type == "date":
        return {"type": "date", "config": {"increment_daily": False}}
    return {"type": "manual", "config": {}}


def _profile_type_label(profile_type: str) -> str:
    return "Vận hành" if profile_type == "van_hanh" else "Phát sinh"


def _preview_generate_name(profile: dict, values: dict, batch_size: int = 1) -> str:
    """TẠM THỜI — placeholder chỉ để có chữ hiển thị lên dòng preview/bảng xem
    trước trong lúc xây giao diện. KHÔNG phải thuật toán chính thức của
    rename_engine.py (file đó chưa tồn tại). Khi nối logic thật, thay hàm này
    bằng lời gọi rename_engine tương ứng, giữ nguyên phần UI gọi nó."""
    ext = ".pdf"
    if profile.get("type") == "van_hanh":
        date_value: datetime.date = values.get("date") or datetime.date.today()
        parts = [date_value.strftime("%d%m%Y")]
        if profile.get("has_ca"):
            ca_index = values.get("ca_index", 1)
            parts.append(f"K{ca_index}")
        fixed_text = (profile.get("fixed_text") or "").strip()
        if fixed_text:
            parts.append(fixed_text)
        return "_".join(parts) + ext

    segments: List[str] = []
    pad_width = max(2, len(str(max(1, batch_size))))
    for block in profile.get("blocks", []):
        btype = block.get("type")
        cfg = block.get("config", {})
        if btype == "fixed_text":
            value = (cfg.get("value") or "").strip()
            if value:
                segments.append(value)
        elif btype == "auto_number":
            start = values.get("auto_number_start", cfg.get("start", 1))
            segments.append(str(start).zfill(pad_width))
        elif btype == "date":
            date_value = values.get("date") or datetime.date.today()
            segments.append(date_value.strftime("%d%m%Y"))
        elif btype == "manual":
            segments.append(values.get("manual_sample") or "TenNhapTay")
    return ("_".join(segments) if segments else "ten_file") + ext


# ----------------------------------------------------------------------
# Khối chọn file (tái sử dụng phong cách DropZone của merge_widget.py)
# ----------------------------------------------------------------------
class _DropZone(QFrame):
    files_selected = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(96)
        self.setCursor(Qt.PointingHandCursor)
        self._locked = False
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 0, 24, 0)
        layout.setSpacing(16)
        layout.setAlignment(Qt.AlignCenter)

        self.icon_box = QFrame()
        self.icon_box.setFixedSize(_DROPZONE_ICON_BOX, _DROPZONE_ICON_BOX)
        self.icon_box.setStyleSheet(
            f"QFrame {{ background-color: white; border: 2px solid {COLOR_ACCENT}; border-radius: 12px; }}"
        )
        icon_box_layout = QVBoxLayout(self.icon_box)
        icon_box_layout.setContentsMargins(0, 0, 0, 0)
        icon_box_layout.setAlignment(Qt.AlignCenter)
        self.icon_label = QLabel()
        self.icon_label.setPixmap(qta.icon("mdi6.tray-arrow-up", color=COLOR_ACCENT).pixmap(QSize(28, 28)))
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("background: transparent; border: none;")
        icon_box_layout.addWidget(self.icon_label)
        layout.addWidget(self.icon_box)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        self.main_label = QLabel("Chọn file hoặc kéo-thả file PDF vào đây")
        self.main_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(self.main_label)

        self.note_label = QLabel("Có thể chọn nhiều file cùng lúc để đổi tên hàng loạt")
        self.note_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(self.note_label)

        layout.addLayout(text_col)

    def _apply_style(self) -> None:
        border_color = COLOR_BORDER if self._locked else COLOR_BORDER_STRONG
        bg = _PILL_BG if self._locked else "white"
        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border: 1.5px dashed {border_color}; border-radius: 14px; }}"
        )

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.setCursor(Qt.ForbiddenCursor if locked else Qt.PointingHandCursor)
        self.setAcceptDrops(not locked)
        self._apply_style()
        if locked:
            self.main_label.setText("Đã khóa danh sách file — bấm \"Clear\" để chọn lại")
            self.note_label.setText("Danh sách đang áp dụng theo 1 hồ sơ mẫu đã chọn")
        else:
            self.main_label.setText("Chọn file hoặc kéo-thả file PDF vào đây")
            self.note_label.setText("Có thể chọn nhiều file cùng lúc để đổi tên hàng loạt")

    def _open_file_dialog(self) -> None:
        if self._locked:
            return
        paths, _ = QFileDialog.getOpenFileNames(self, "Chọn file PDF", "", "PDF Files (*.pdf)")
        if paths:
            self.files_selected.emit(paths)

    def mousePressEvent(self, event) -> None:
        self._open_file_dialog()
        super().mousePressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if not self._locked and event.mimeData().hasUrls():
            event.acceptProposedAction()
            return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        if self._locked:
            return
        paths = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.toLocalFile().lower().endswith(".pdf")
        ]
        if paths:
            self.files_selected.emit(paths)


# ----------------------------------------------------------------------
# Danh sách file kéo-thả (tái sử dụng nguyên cơ chế vạch chỉ thị của merge_widget.py)
# ----------------------------------------------------------------------
class _DraggableFileList(QListWidget):
    row_drag_dropped = Signal(int, int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.NoSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFrameShape(QFrame.NoFrame)
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
        self._locked = False

        self._drop_line = QFrame(self.viewport())
        self._drop_line.setFixedHeight(_DROP_INDICATOR_HEIGHT)
        self._drop_line.setStyleSheet(
            f"background-color: {_DROP_INDICATOR_COLOR}; border-radius: {_DROP_INDICATOR_HEIGHT // 2}px;"
        )
        self._drop_line.hide()

        self._drop_dot = QFrame(self.viewport())
        self._drop_dot.setFixedSize(_DROP_INDICATOR_DOT_SIZE, _DROP_INDICATOR_DOT_SIZE)
        self._drop_dot.setStyleSheet(
            f"background-color: {_DROP_INDICATOR_COLOR}; border-radius: {_DROP_INDICATOR_DOT_SIZE // 2}px;"
        )
        self._drop_dot.hide()

    def set_locked(self, locked: bool) -> None:
        self._locked = locked

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

        deadzone = max(1, round(rect.height() * _DROP_DEADZONE_RATIO))
        previous = self._drop_indicator_index
        if previous is not None and previous in (index, index + 1):
            if center_y - deadzone <= pos.y() <= center_y + deadzone:
                return previous

        if pos.y() > center_y:
            index += 1
        return index

    def update_drop_indicator_from_pos(self, pos) -> None:
        if self._locked:
            return
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
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setPixmap(qta.icon("mdi6.drag-vertical", color=COLOR_TEXT_SECONDARY).pixmap(QSize(_HANDLE_ICON_SIZE, _HANDLE_ICON_SIZE)))
        self.setFixedSize(_HANDLE_ICON_SIZE, _HANDLE_ICON_SIZE)
        self.setCursor(Qt.OpenHandCursor)
        self.setStyleSheet("background: transparent; border: none;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)


class _OrderBadge(QLabel):
    """Số thứ tự vị trí file trong danh sách — vì thứ tự này quyết định trực tiếp
    Ngày/Ca/Số thứ tự tự tăng sinh ra (08_dac_ta_doi_ten.md mục 3, 4), cần hiển thị
    rõ ràng ngay trên mỗi dòng, không chỉ dựa vào vị trí trực quan trong danh sách."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(_BADGE_SIZE, _BADGE_SIZE)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background-color: {_PILL_BG}; color: {COLOR_TEXT_PRIMARY}; "
            f"font-size: 11px; font-weight: 700; border-radius: {_BADGE_SIZE // 2}px; border: none;"
        )

    def set_order(self, order: int) -> None:
        self.setText(str(order))


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
        self.is_locked = False
        self.list_widget: Optional[_DraggableFileList] = None
        self._press_pos = None
        self._dragging = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(66)
        self._apply_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 14, 8)
        layout.setSpacing(10)

        self.order_badge = _OrderBadge(self)
        layout.addWidget(self.order_badge)

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

        self.delete_btn = QToolButton()
        self.delete_btn.setCursor(Qt.PointingHandCursor)
        self.delete_btn.setIcon(qta.icon("mdi6.close", color=COLOR_TEXT_SECONDARY))
        self.delete_btn.setIconSize(QSize(18, 18))
        self.delete_btn.setToolTip("Xoá khỏi danh sách")
        self.delete_btn.setStyleSheet(
            f"""
            QToolButton {{ background: transparent; border: none; border-radius: 6px; padding: 4px; }}
            QToolButton:hover {{ background-color: #FEE2E2; color: {COLOR_ERROR}; }}
            """
        )
        self.delete_btn.clicked.connect(self.remove_requested.emit)
        layout.addWidget(self.delete_btn)

    def _apply_style(self) -> None:
        if self.is_locked:
            self.setStyleSheet(
                f"_FileRow {{ background-color: {_PILL_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; }}"
            )
        elif self.is_selected:
            self.setStyleSheet(
                f"_FileRow {{ background-color: {COLOR_ACCENT_LIGHT}; border: 1px solid {COLOR_ACCENT}; border-radius: 8px; }}"
            )
        else:
            self.setStyleSheet(
                f"_FileRow {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 8px; }}"
            )

    def set_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self._apply_style()

    def set_order(self, order: int) -> None:
        self.order_badge.set_order(order)

    def set_locked(self, locked: bool) -> None:
        """Khóa Cột A (08_dac_ta_doi_ten.md bảng 6.1): ẩn tay cầm kéo-thả + nút
        xóa, đổi con trỏ chuột — nhưng VẪN click trái được để xem preview."""
        self.is_locked = locked
        self.drag_handle.setVisible(not locked)
        self.delete_btn.setVisible(not locked)
        self.setCursor(Qt.ForbiddenCursor if locked else Qt.PointingHandCursor)
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
        if self.is_locked or self._press_pos is None:
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
        self.setCursor(Qt.ForbiddenCursor if self.is_locked else Qt.PointingHandCursor)

        list_widget = self.list_widget
        source_index = self.current_index()
        viewport_pos = self._to_list_viewport_pos(current_pos)
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
# Cột B — Trang "Preview" (đọc thật số trang/kích thước, render thumbnail trang 1)
# ----------------------------------------------------------------------
class _PreviewPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._renderer = PageRenderer()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignTop)

        self.thumb_frame = QFrame()
        self.thumb_frame.setFixedSize(_PREVIEW_THUMB_WIDTH, round(_PREVIEW_THUMB_WIDTH * 1.35))
        self.thumb_frame.setStyleSheet(
            f"QFrame {{ background-color: {COLOR_CONTENT_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 10px; }}"
        )
        thumb_layout = QVBoxLayout(self.thumb_frame)
        thumb_layout.setContentsMargins(0, 0, 0, 0)
        thumb_layout.setAlignment(Qt.AlignCenter)
        self.thumb_image = QLabel()
        self.thumb_image.setAlignment(Qt.AlignCenter)
        self.thumb_image.setScaledContents(False)
        self.thumb_image.setStyleSheet("background: transparent; border: none;")
        thumb_layout.addWidget(self.thumb_image)
        layout.addWidget(self.thumb_frame, alignment=Qt.AlignHCenter)

        self.file_name_label = QLabel("Chọn 1 file ở danh sách bên trái để xem trước")
        self.file_name_label.setAlignment(Qt.AlignCenter)
        self.file_name_label.setWordWrap(True)
        self.file_name_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self.file_name_label)

        self.file_meta_label = QLabel("")
        self.file_meta_label.setAlignment(Qt.AlignCenter)
        self.file_meta_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;"
        )
        layout.addWidget(self.file_meta_label)

        layout.addStretch()
        self._set_placeholder_icon()

    def _set_placeholder_icon(self) -> None:
        self.thumb_image.setPixmap(
            qta.icon("mdi6.file-pdf-box", color=COLOR_BORDER_STRONG).pixmap(QSize(96, 96))
        )

    def show_empty(self) -> None:
        self._set_placeholder_icon()
        self.file_name_label.setText("Chọn 1 file ở danh sách bên trái để xem trước")
        self.file_meta_label.setText("")

    def show_file(self, path: str) -> None:
        name = os.path.basename(path)
        try:
            infos: List[PageInfo] = list_page_infos(path)
            size_text = _format_file_size(os.path.getsize(path))
        except (CorruptedFileError, PasswordProtectedError, FileLockedError, OSError) as exc:
            self._set_placeholder_icon()
            self.file_name_label.setText(name)
            self.file_meta_label.setText(f"Không thể đọc file: {exc}")
            return

        self.file_name_label.setText(name)
        self.file_meta_label.setText(f"{size_text}  •  {len(infos)} trang")

        if infos:
            try:
                data = self._renderer.render_thumbnail(path, 0, max_width=_PREVIEW_THUMB_WIDTH)
                pixmap = QPixmap()
                pixmap.loadFromData(data, "PNG")
                self.thumb_image.setPixmap(pixmap)
            except Exception:
                self._set_placeholder_icon()
        else:
            self._set_placeholder_icon()


# ----------------------------------------------------------------------
# Cột B — Trang "Form nhập liệu" (đổi theo đúng hồ sơ đang chọn, mục 6.2)
# ----------------------------------------------------------------------
class _RenameFormPage(QWidget):
    values_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._profile: Optional[dict] = None

        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(0, 0, 0, 0)
        self.root_layout.setSpacing(14)
        self.root_layout.setAlignment(Qt.AlignTop)

        self.profile_title = QLabel("")
        self.profile_title.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        self.root_layout.addWidget(self.profile_title)

        self.form_layout = QFormLayout()
        self.form_layout.setSpacing(10)
        self.form_layout.setLabelAlignment(Qt.AlignLeft)
        self.root_layout.addLayout(self.form_layout)

        self.root_layout.addStretch()

        preview_box = QFrame()
        preview_box.setStyleSheet(
            f"QFrame {{ background-color: {COLOR_ACCENT_LIGHT}; border: 1px solid {COLOR_ACCENT}; border-radius: 10px; }}"
        )
        preview_box_layout = QVBoxLayout(preview_box)
        preview_box_layout.setContentsMargins(14, 10, 14, 10)
        preview_box_layout.setSpacing(2)
        hint = QLabel("Mẫu tên file đầu tiên trong danh sách")
        hint.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; background: transparent; border: none;")
        preview_box_layout.addWidget(hint)
        self.preview_name_label = QLabel("—")
        self.preview_name_label.setWordWrap(True)
        self.preview_name_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        preview_box_layout.addWidget(self.preview_name_label)
        self.root_layout.addWidget(preview_box)

        self._date_edit: Optional[QDateEdit] = None
        self._ca_combo: Optional[QComboBox] = None
        self._auto_number_spin: Optional[QSpinBox] = None
        self._auto_step_spin: Optional[QSpinBox] = None
        self._manual_sample_edit: Optional[QLineEdit] = None

    def _clear_form(self) -> None:
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)
        self._date_edit = None
        self._ca_combo = None
        self._auto_number_spin = None
        self._auto_step_spin = None
        self._manual_sample_edit = None

    @staticmethod
    def _styled_date_edit() -> QDateEdit:
        edit = QDateEdit(QDate.currentDate())
        edit.setCalendarPopup(True)
        edit.setDisplayFormat("dd/MM/yyyy")
        edit.setFixedHeight(CONTROL_HEIGHT)
        edit.setStyleSheet(
            f"""
            QDateEdit {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                padding: 0 10px; font-size: 13px;
            }}
            QDateEdit:focus {{ border-color: {COLOR_ACCENT}; }}
            """
        )
        return edit

    @staticmethod
    def _styled_spin(minimum: int, maximum: int, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setFixedHeight(CONTROL_HEIGHT)
        spin.setStyleSheet(
            f"""
            QSpinBox {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                padding: 0 8px; font-size: 13px;
            }}
            QSpinBox:focus {{ border-color: {COLOR_ACCENT}; }}
            """
        )
        return spin

    @staticmethod
    def _styled_combo(items: List[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(items)
        combo.setFixedHeight(CONTROL_HEIGHT)
        combo.setStyleSheet(
            f"""
            QComboBox {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                padding: 0 10px; font-size: 13px;
            }}
            QComboBox:focus {{ border-color: {COLOR_ACCENT}; }}
            """
        )
        return combo

    @staticmethod
    def _styled_line_edit(placeholder: str = "") -> QLineEdit:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setFixedHeight(CONTROL_HEIGHT)
        edit.setStyleSheet(
            f"""
            QLineEdit {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                padding: 0 10px; font-size: 13px;
            }}
            QLineEdit:focus {{ border-color: {COLOR_ACCENT}; }}
            """
        )
        return edit

    def set_profile(self, profile: Optional[dict]) -> None:
        self._profile = profile
        self._clear_form()

        if profile is None:
            self.profile_title.setText("")
            self.preview_name_label.setText("—")
            return

        self.profile_title.setText(
            f"Hồ sơ: {profile['name']}  ·  {_profile_type_label(profile['type'])}"
        )

        if profile["type"] == "van_hanh":
            self._date_edit = self._styled_date_edit()
            self._date_edit.dateChanged.connect(self._emit_changed)
            self.form_layout.addRow("Ngày bắt đầu", self._date_edit)

            if profile.get("has_ca"):
                ca_count = profile.get("ca_count", _DEFAULT_CA_COUNT)
                self._ca_combo = self._styled_combo([f"K{i}" for i in range(1, ca_count + 1)])
                self._ca_combo.currentIndexChanged.connect(self._emit_changed)
                self.form_layout.addRow("Ca bắt đầu", self._ca_combo)
        else:
            for block in profile.get("blocks", []):
                btype = block.get("type")
                cfg = block.get("config", {})
                if btype == "auto_number":
                    row = QHBoxLayout()
                    self._auto_number_spin = self._styled_spin(0, 999999, cfg.get("start", 1))
                    self._auto_step_spin = self._styled_spin(1, 999, cfg.get("step", 1))
                    self._auto_number_spin.valueChanged.connect(self._emit_changed)
                    self._auto_step_spin.valueChanged.connect(self._emit_changed)
                    row.addWidget(QLabel("Bắt đầu"))
                    row.addWidget(self._auto_number_spin)
                    row.addWidget(QLabel("Bước nhảy"))
                    row.addWidget(self._auto_step_spin)
                    wrap = QWidget()
                    wrap.setLayout(row)
                    self.form_layout.addRow("Số thứ tự tự tăng", wrap)
                elif btype == "date":
                    self._date_edit = self._styled_date_edit()
                    self._date_edit.dateChanged.connect(self._emit_changed)
                    self.form_layout.addRow("Ngày bắt đầu", self._date_edit)
                elif btype == "manual":
                    self._manual_sample_edit = self._styled_line_edit("VD: giá trị mẫu cho file đầu tiên")
                    self._manual_sample_edit.textChanged.connect(self._emit_changed)
                    self.form_layout.addRow("Nhập tay (mẫu xem trước)", self._manual_sample_edit)
                # "fixed_text": không cần trường trong form (đã cấu hình sẵn ở hồ sơ).

        self._emit_changed()

    def current_values(self) -> dict:
        values: dict = {}
        if self._date_edit is not None:
            values["date"] = self._date_edit.date().toPython()
        if self._ca_combo is not None:
            values["ca_index"] = self._ca_combo.currentIndex() + 1
        if self._auto_number_spin is not None:
            values["auto_number_start"] = self._auto_number_spin.value()
        if self._auto_step_spin is not None:
            values["auto_number_step"] = self._auto_step_spin.value()
        if self._manual_sample_edit is not None:
            values["manual_sample"] = self._manual_sample_edit.text().strip() or "TenNhapTay"
        return values

    def is_valid(self) -> bool:
        return self._profile is not None

    def _emit_changed(self, *args) -> None:
        if self._profile is not None:
            name = _preview_generate_name(self._profile, self.current_values())
            self.preview_name_label.setText(name)
        self.values_changed.emit()


# ----------------------------------------------------------------------
# Toggle 2 lựa chọn (Vận hành / Phát sinh) — dùng trong dialog Tạo/Sửa hồ sơ
# ----------------------------------------------------------------------
class _SegmentedToggle(QWidget):
    value_changed = Signal(str)

    def __init__(self, options: List[Tuple[str, str]], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = options[0][0]
        self._buttons: Dict[str, QPushButton] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        for i, (value, label) in enumerate(options):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(CONTROL_HEIGHT)
            radius_css = ""
            if i == 0:
                radius_css = f"border-top-left-radius: {CORNER_RADIUS}px; border-bottom-left-radius: {CORNER_RADIUS}px;"
            elif i == len(options) - 1:
                radius_css = f"border-top-right-radius: {CORNER_RADIUS}px; border-bottom-right-radius: {CORNER_RADIUS}px;"
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: white; color: {COLOR_TEXT_PRIMARY};
                    border: 1.5px solid {COLOR_BORDER_STRONG}; {radius_css}
                    font-size: 13px; font-weight: 700; padding: 0 16px;
                }}
                QPushButton:checked {{ background-color: {COLOR_ACCENT}; color: white; border-color: {COLOR_ACCENT}; }}
                QPushButton:disabled {{ background-color: {_PILL_BG}; color: {COLOR_TEXT_SECONDARY}; }}
                """
            )
            btn.clicked.connect(lambda checked, v=value: self._on_clicked(v))
            layout.addWidget(btn, 1)
            self._buttons[value] = btn

        self._buttons[self._value].setChecked(True)

    def _on_clicked(self, value: str) -> None:
        self.set_value(value)
        self.value_changed.emit(value)

    def set_value(self, value: str) -> None:
        self._value = value
        for v, btn in self._buttons.items():
            btn.setChecked(v == value)

    def value(self) -> str:
        return self._value

    def set_locked(self, locked: bool) -> None:
        for btn in self._buttons.values():
            btn.setEnabled(not locked)


# ----------------------------------------------------------------------
# 1 dòng cấu hình khối trong hồ sơ "Phát sinh" (mục 4, 6.4)
# ----------------------------------------------------------------------
class _PhatSinhBlockRow(QFrame):
    changed = Signal()
    move_up_requested = Signal(object)
    move_down_requested = Signal(object)
    remove_requested = Signal(object)

    def __init__(self, block: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.block = block
        self.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 10px; }}"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.type_combo = _RenameFormPage._styled_combo(
            [_BLOCK_TYPE_LABELS[t] for t in _BLOCK_TYPE_ORDER]
        )
        self.type_combo.setCurrentIndex(_BLOCK_TYPE_ORDER.index(block["type"]))
        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        top_row.addWidget(self.type_combo, 1)

        self.up_btn = QToolButton()
        self.up_btn.setIcon(qta.icon("mdi6.arrow-up-bold", color=COLOR_TEXT_PRIMARY))
        self.up_btn.setCursor(Qt.PointingHandCursor)
        self.up_btn.setToolTip("Di chuyển lên")
        self.up_btn.clicked.connect(lambda: self.move_up_requested.emit(self))
        top_row.addWidget(self.up_btn)

        self.down_btn = QToolButton()
        self.down_btn.setIcon(qta.icon("mdi6.arrow-down-bold", color=COLOR_TEXT_PRIMARY))
        self.down_btn.setCursor(Qt.PointingHandCursor)
        self.down_btn.setToolTip("Di chuyển xuống")
        self.down_btn.clicked.connect(lambda: self.move_down_requested.emit(self))
        top_row.addWidget(self.down_btn)

        self.remove_btn = QToolButton()
        self.remove_btn.setIcon(qta.icon("mdi6.close", color=COLOR_ERROR))
        self.remove_btn.setCursor(Qt.PointingHandCursor)
        self.remove_btn.setToolTip("Xoá khối")
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self))
        top_row.addWidget(self.remove_btn)

        outer.addLayout(top_row)

        self.config_container = QWidget()
        self.config_layout = QHBoxLayout(self.config_container)
        self.config_layout.setContentsMargins(0, 0, 0, 0)
        self.config_layout.setSpacing(10)
        outer.addWidget(self.config_container)

        self._build_config_widgets()

    def _clear_config_widgets(self) -> None:
        while self.config_layout.count():
            item = self.config_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _build_config_widgets(self) -> None:
        self._clear_config_widgets()
        btype = self.block["type"]
        cfg = self.block.setdefault("config", {})

        if btype == "fixed_text":
            edit = _RenameFormPage._styled_line_edit("Nội dung cố định, VD: QT.VHTB-STDVH-TX")
            edit.setText(cfg.get("value", ""))
            edit.textChanged.connect(lambda text: self._update_config("value", text))
            self.config_layout.addWidget(QLabel("Nội dung:"))
            self.config_layout.addWidget(edit, 1)

        elif btype == "auto_number":
            start_spin = _RenameFormPage._styled_spin(0, 999999, cfg.get("start", 1))
            start_spin.valueChanged.connect(lambda v: self._update_config("start", v))
            step_spin = _RenameFormPage._styled_spin(1, 999, cfg.get("step", 1))
            step_spin.valueChanged.connect(lambda v: self._update_config("step", v))
            self.config_layout.addWidget(QLabel("Bắt đầu:"))
            self.config_layout.addWidget(start_spin)
            self.config_layout.addWidget(QLabel("Bước nhảy:"))
            self.config_layout.addWidget(step_spin)
            self.config_layout.addStretch()

        elif btype == "date":
            checkbox = QCheckBox("Tăng dần mỗi file")
            checkbox.setChecked(cfg.get("increment_daily", False))
            checkbox.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px;")
            checkbox.toggled.connect(lambda checked: self._update_config("increment_daily", checked))
            self.config_layout.addWidget(checkbox)
            self.config_layout.addStretch()

        else:  # manual
            note = QLabel("Giá trị nhập tay điền trực tiếp ở bảng xem trước lúc bấm \"Đổi tên\".")
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px;")
            self.config_layout.addWidget(note, 1)

        self.changed.emit()

    def _update_config(self, key: str, value) -> None:
        self.block.setdefault("config", {})[key] = value
        self.changed.emit()

    def _on_type_changed(self, index: int) -> None:
        new_type = _BLOCK_TYPE_ORDER[index]
        self.block = _default_block(new_type)
        self._build_config_widgets()

    def set_move_buttons_enabled(self, can_up: bool, can_down: bool) -> None:
        self.up_btn.setEnabled(can_up)
        self.down_btn.setEnabled(can_down)


# ----------------------------------------------------------------------
# Dialog Tạo/Sửa hồ sơ mẫu (mục 5.1, 5.2, 6.4)
# ----------------------------------------------------------------------
class _ProfileFormDialog(QDialog):
    def __init__(
        self,
        existing_names: List[str],
        profile: Optional[dict] = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.is_edit_mode = profile is not None
        self._existing_names = existing_names  # đã loại tên của chính hồ sơ đang sửa
        self._result_profile: Optional[dict] = None
        self._blocks_rows: List[_PhatSinhBlockRow] = []

        self.setWindowTitle("Sửa hồ sơ mẫu" if self.is_edit_mode else "Tạo biểu mẫu mới")
        self.setMinimumWidth(480)
        self.setStyleSheet(f"QDialog {{ background-color: white; }} QLabel {{ color: {COLOR_TEXT_PRIMARY}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(14)

        name_label = QLabel("Tên hồ sơ")
        name_label.setStyleSheet("font-size: 13px; font-weight: 700; background: transparent;")
        root.addWidget(name_label)
        self.name_edit = _RenameFormPage._styled_line_edit("VD: TX, RX, Báo cáo sự cố...")
        self.name_edit.textChanged.connect(self._revalidate)
        root.addWidget(self.name_edit)

        type_label = QLabel("Loại biểu mẫu")
        type_label.setStyleSheet("font-size: 13px; font-weight: 700; background: transparent;")
        root.addWidget(type_label)
        self.type_toggle = _SegmentedToggle([("van_hanh", "Vận hành"), ("phat_sinh", "Phát sinh")])
        self.type_toggle.value_changed.connect(self._on_type_changed)
        root.addWidget(self.type_toggle)

        # ---- Form động: Vận hành ----
        self.van_hanh_page = QWidget()
        vh_layout = QVBoxLayout(self.van_hanh_page)
        vh_layout.setContentsMargins(0, 4, 0, 0)
        vh_layout.setSpacing(10)

        self.has_ca_checkbox = QCheckBox("Có ca trực")
        self.has_ca_checkbox.setStyleSheet(f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 600;")
        self.has_ca_checkbox.toggled.connect(self._on_has_ca_toggled)
        vh_layout.addWidget(self.has_ca_checkbox)

        ca_row = QHBoxLayout()
        ca_row.addWidget(QLabel("Số ca trong ngày"))
        self.ca_count_spin = _RenameFormPage._styled_spin(_MIN_CA_COUNT, _MAX_CA_COUNT, _DEFAULT_CA_COUNT)
        self.ca_count_spin.valueChanged.connect(self._update_preview)
        ca_row.addWidget(self.ca_count_spin)
        ca_row.addStretch()
        self.ca_row_widget = QWidget()
        self.ca_row_widget.setLayout(ca_row)
        self.ca_row_widget.setVisible(False)
        vh_layout.addWidget(self.ca_row_widget)

        vh_layout.addWidget(QLabel("Văn bản cố định"))
        self.fixed_text_edit = _RenameFormPage._styled_line_edit("VD: QT.VHTB-STDVH-TX")
        self.fixed_text_edit.textChanged.connect(self._update_preview)
        vh_layout.addWidget(self.fixed_text_edit)

        root.addWidget(self.van_hanh_page)

        # ---- Form động: Phát sinh ----
        self.phat_sinh_page = QWidget()
        ps_layout = QVBoxLayout(self.phat_sinh_page)
        ps_layout.setContentsMargins(0, 4, 0, 0)
        ps_layout.setSpacing(8)

        self.blocks_container = QVBoxLayout()
        self.blocks_container.setSpacing(8)
        ps_layout.addLayout(self.blocks_container)

        self.add_block_btn = QPushButton(" + Thêm khối")
        self.add_block_btn.setCursor(Qt.PointingHandCursor)
        self.add_block_btn.setFixedHeight(CONTROL_HEIGHT)
        self.add_block_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: white; color: {COLOR_ACCENT}; border: 1.5px dashed {COLOR_ACCENT};
                border-radius: {CORNER_RADIUS}px; font-size: 13px; font-weight: 700;
            }}
            QPushButton:hover {{ background-color: {COLOR_ACCENT_LIGHT}; }}
            QPushButton:disabled {{ color: {COLOR_TEXT_SECONDARY}; border-color: {COLOR_BORDER_STRONG}; }}
            """
        )
        self.add_block_btn.clicked.connect(self._add_block)
        ps_layout.addWidget(self.add_block_btn)

        root.addWidget(self.phat_sinh_page)

        # ---- Dòng preview mẫu (CHỐT, bắt buộc — mục 5.1) ----
        preview_box = QFrame()
        preview_box.setStyleSheet(
            f"QFrame {{ background-color: {COLOR_ACCENT_LIGHT}; border: 1px solid {COLOR_ACCENT}; border-radius: 10px; }}"
        )
        preview_box_layout = QVBoxLayout(preview_box)
        preview_box_layout.setContentsMargins(14, 8, 14, 8)
        preview_box_layout.setSpacing(2)
        hint = QLabel("Mẫu tên file")
        hint.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 11px; background: transparent;")
        preview_box_layout.addWidget(hint)
        self.preview_label = QLabel("—")
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; background: transparent;"
        )
        preview_box_layout.addWidget(self.preview_label)
        root.addWidget(preview_box)

        # ---- Nút Hủy / Lưu hồ sơ ----
        button_row = QHBoxLayout()
        button_row.addStretch()
        self.cancel_btn = QPushButton("Hủy")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.setFixedHeight(CONTROL_HEIGHT)
        self.cancel_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {_PILL_BG}; }}
            """
        )
        self.cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_btn)

        self.save_btn = QPushButton("Lưu hồ sơ")
        self.save_btn.setCursor(Qt.PointingHandCursor)
        self.save_btn.setFixedHeight(CONTROL_HEIGHT)
        self.save_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ACCENT}; color: white; border: none;
                border-radius: {CORNER_RADIUS}px; font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: #E28104; }}
            QPushButton:disabled {{ background-color: {COLOR_BORDER_STRONG}; }}
            """
        )
        self.save_btn.clicked.connect(self._on_save_clicked)
        button_row.addWidget(self.save_btn)
        root.addLayout(button_row)

        # ---- Nạp dữ liệu nếu đang Sửa ----
        if profile is not None:
            self.name_edit.setText(profile["name"])
            self.type_toggle.set_value(profile["type"])
            self.type_toggle.set_locked(True)  # CHỐT — không cho đổi Loại khi Sửa
            if profile["type"] == "van_hanh":
                self.has_ca_checkbox.setChecked(profile.get("has_ca", False))
                self.ca_count_spin.setValue(profile.get("ca_count", _DEFAULT_CA_COUNT))
                self.fixed_text_edit.setText(profile.get("fixed_text", ""))
            else:
                for block in profile.get("blocks", []):
                    self._add_block(copy.deepcopy(block))

        self._on_type_changed(self.type_toggle.value())
        self._update_preview()
        self._revalidate()

    # ------------------------------------------------------------------
    def _on_type_changed(self, value: str) -> None:
        self.van_hanh_page.setVisible(value == "van_hanh")
        self.phat_sinh_page.setVisible(value == "phat_sinh")
        self._update_preview()
        self._revalidate()

    def _on_has_ca_toggled(self, checked: bool) -> None:
        self.ca_row_widget.setVisible(checked)
        self._update_preview()

    def _add_block(self, block: Optional[dict] = None) -> None:
        if len(self._blocks_rows) >= _MAX_BLOCKS:
            return
        block = block or _default_block("fixed_text")
        row = _PhatSinhBlockRow(block)
        row.changed.connect(self._update_preview)
        row.move_up_requested.connect(self._move_block_up)
        row.move_down_requested.connect(self._move_block_down)
        row.remove_requested.connect(self._remove_block)
        self.blocks_container.addWidget(row)
        self._blocks_rows.append(row)
        self._refresh_block_buttons()
        self._update_preview()
        self._revalidate()

    def _remove_block(self, row: _PhatSinhBlockRow) -> None:
        self._blocks_rows.remove(row)
        self.blocks_container.removeWidget(row)
        row.deleteLater()
        self._refresh_block_buttons()
        self._update_preview()
        self._revalidate()

    def _move_block_up(self, row: _PhatSinhBlockRow) -> None:
        index = self._blocks_rows.index(row)
        if index == 0:
            return
        self._swap_blocks(index, index - 1)

    def _move_block_down(self, row: _PhatSinhBlockRow) -> None:
        index = self._blocks_rows.index(row)
        if index == len(self._blocks_rows) - 1:
            return
        self._swap_blocks(index, index + 1)

    def _swap_blocks(self, i: int, j: int) -> None:
        self._blocks_rows[i], self._blocks_rows[j] = self._blocks_rows[j], self._blocks_rows[i]
        for k in reversed(range(self.blocks_container.count())):
            self.blocks_container.takeAt(k)
        for row in self._blocks_rows:
            self.blocks_container.addWidget(row)
        self._refresh_block_buttons()
        self._update_preview()

    def _refresh_block_buttons(self) -> None:
        count = len(self._blocks_rows)
        for i, row in enumerate(self._blocks_rows):
            row.set_move_buttons_enabled(i > 0, i < count - 1)
        self.add_block_btn.setEnabled(count < _MAX_BLOCKS)

    def _build_profile_dict(self) -> dict:
        profile_type = self.type_toggle.value()
        profile = {
            "id": _new_profile_id(),
            "name": self.name_edit.text().strip(),
            "type": profile_type,
        }
        if profile_type == "van_hanh":
            profile["has_ca"] = self.has_ca_checkbox.isChecked()
            profile["ca_count"] = self.ca_count_spin.value()
            profile["fixed_text"] = self.fixed_text_edit.text().strip()
        else:
            profile["blocks"] = [copy.deepcopy(row.block) for row in self._blocks_rows]
        return profile

    def _update_preview(self, *args) -> None:
        profile = self._build_profile_dict()
        sample_values = {
            "date": datetime.date.today(),
            "ca_index": 1,
            "auto_number_start": None,
            "manual_sample": "TenNhapTay",
        }
        for block in profile.get("blocks", []):
            if block["type"] == "auto_number":
                sample_values["auto_number_start"] = block["config"].get("start", 1)
        self.preview_label.setText(_preview_generate_name(profile, sample_values))

    def _revalidate(self, *args) -> None:
        name = self.name_edit.text().strip()
        valid = bool(name) and name not in self._existing_names
        if self.type_toggle.value() == "phat_sinh":
            valid = valid and len(self._blocks_rows) >= 1
        self.save_btn.setEnabled(valid)

    def _on_save_clicked(self) -> None:
        self._result_profile = self._build_profile_dict()
        self.accept()

    def get_profile(self) -> Optional[dict]:
        return self._result_profile


# ----------------------------------------------------------------------
# Dialog xác nhận xóa hồ sơ (mục 5.3) — tự vẽ, đồng bộ style nền trắng/chữ tối/Accent
# ----------------------------------------------------------------------
class _ConfirmDeleteProfileDialog(QDialog):
    def __init__(self, profile_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Xóa hồ sơ mẫu")
        self.setStyleSheet(f"QDialog {{ background-color: white; }} QLabel {{ color: {COLOR_TEXT_PRIMARY}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(16)

        message = QLabel(f"Xóa hồ sơ mẫu '{profile_name}'? Không thể hoàn tác.")
        message.setWordWrap(True)
        message.setStyleSheet("font-size: 13px; background: transparent;")
        layout.addWidget(message)

        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(CONTROL_HEIGHT)
        cancel_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {_PILL_BG}; }}
            """
        )
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)

        delete_btn = QPushButton("Xóa hồ sơ")
        delete_btn.setCursor(Qt.PointingHandCursor)
        delete_btn.setFixedHeight(CONTROL_HEIGHT)
        delete_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ERROR}; color: white; border: none;
                border-radius: {CORNER_RADIUS}px; font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: #B91C1C; }}
            """
        )
        delete_btn.clicked.connect(self.accept)
        button_row.addWidget(delete_btn)

        layout.addLayout(button_row)


# ----------------------------------------------------------------------
# Dialog "Quản lý biểu mẫu" (mục 5.4, 6.5)
# ----------------------------------------------------------------------
class _ManageProfilesDialog(QDialog):
    profiles_changed = Signal()

    def __init__(self, profiles: List[dict], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.profiles = profiles  # tham chiếu trực tiếp danh sách của widget cha
        self.setWindowTitle("Quản lý biểu mẫu")
        self.setMinimumSize(420, 380)
        self.setStyleSheet(f"QDialog {{ background-color: white; }} QLabel {{ color: {COLOR_TEXT_PRIMARY}; }}")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            f"""
            QListWidget {{
                background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: {CORNER_RADIUS}px;
                font-size: 13px; color: {COLOR_TEXT_PRIMARY};
            }}
            QListWidget::item {{ padding: 8px; }}
            QListWidget::item:selected {{ background-color: {COLOR_ACCENT_LIGHT}; color: {COLOR_TEXT_PRIMARY}; }}
            """
        )
        self.list_widget.itemSelectionChanged.connect(self._update_buttons)
        layout.addWidget(self.list_widget, 1)

        button_row = QHBoxLayout()
        self.edit_btn = QPushButton(" Sửa")
        self.edit_btn.setIcon(qta.icon("mdi6.pencil-outline", color=COLOR_TEXT_PRIMARY))
        self.delete_btn = QPushButton(" Xóa")
        self.delete_btn.setIcon(qta.icon("mdi6.trash-can-outline", color=COLOR_ERROR))
        self.close_btn = QPushButton("Đóng")

        for btn in (self.edit_btn, self.delete_btn, self.close_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(CONTROL_HEIGHT)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: white; color: {COLOR_TEXT_PRIMARY};
                    border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                    font-size: 13px; font-weight: 700; padding: 0 14px;
                }}
                QPushButton:hover:enabled {{ background-color: {_PILL_BG}; }}
                QPushButton:disabled {{ color: {COLOR_TEXT_SECONDARY}; }}
                """
            )
        self.edit_btn.clicked.connect(self._on_edit_clicked)
        self.delete_btn.clicked.connect(self._on_delete_clicked)
        self.close_btn.clicked.connect(self.accept)

        button_row.addWidget(self.edit_btn)
        button_row.addWidget(self.delete_btn)
        button_row.addStretch()
        button_row.addWidget(self.close_btn)
        layout.addLayout(button_row)

        self._reload_list()
        self._update_buttons()

    def _reload_list(self) -> None:
        self.list_widget.clear()
        for profile in self.profiles:
            item = QListWidgetItem(f"{profile['name']} — ({_profile_type_label(profile['type'])})")
            item.setData(Qt.UserRole, profile["id"])
            self.list_widget.addItem(item)

    def _update_buttons(self) -> None:
        has_selection = self.list_widget.currentItem() is not None
        self.edit_btn.setEnabled(has_selection)
        self.delete_btn.setEnabled(has_selection)

    def _selected_profile(self) -> Optional[dict]:
        item = self.list_widget.currentItem()
        if item is None:
            return None
        profile_id = item.data(Qt.UserRole)
        return next((p for p in self.profiles if p["id"] == profile_id), None)

    def _on_edit_clicked(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        other_names = [p["name"] for p in self.profiles if p["id"] != profile["id"]]
        dialog = _ProfileFormDialog(other_names, profile=copy.deepcopy(profile), parent=self)
        if dialog.exec() == QDialog.Accepted:
            updated = dialog.get_profile()
            updated["id"] = profile["id"]  # giữ nguyên id — ghi đè đúng bản ghi cũ
            index = self.profiles.index(profile)
            self.profiles[index] = updated
            self._reload_list()
            self.profiles_changed.emit()

    def _on_delete_clicked(self) -> None:
        profile = self._selected_profile()
        if profile is None:
            return
        confirm = _ConfirmDeleteProfileDialog(profile["name"], parent=self)
        if confirm.exec() == QDialog.Accepted:
            self.profiles.remove(profile)
            self._reload_list()
            self._update_buttons()
            self.profiles_changed.emit()


# ----------------------------------------------------------------------
# Dialog xem trước Tên cũ → Tên mới trước khi "Đổi tên" thật (mục 0, 6.1)
# ----------------------------------------------------------------------
class _RenamePreviewDialog(QDialog):
    def __init__(
        self,
        files: List[Tuple[str, str]],  # (path, current_name), đúng thứ tự Cột A
        profile: dict,
        base_values: dict,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Xem trước tên file")
        self.setMinimumSize(620, 420)
        self.setStyleSheet(f"QDialog {{ background-color: white; }} QLabel {{ color: {COLOR_TEXT_PRIMARY}; }}")

        self.profile = profile
        self.files = files
        self.base_values = base_values
        self._manual_edits: Dict[int, str] = {}
        self._output_dir: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        note = QLabel(
            "Đây là bảng xem trước — theo quy ước chung, file gốc không bị ghi đè, "
            "kết quả sẽ lưu vào thư mục bạn chọn bên dưới với tên mới."
        )
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; background: transparent;")
        layout.addWidget(note)

        has_manual_block = profile["type"] == "phat_sinh" and any(
            b["type"] == "manual" for b in profile.get("blocks", [])
        )

        self.table = QTableWidget(len(files), 3 if has_manual_block else 2)
        headers = ["Tên file gốc", "Tên file mới"]
        if has_manual_block:
            headers.insert(1, "Giá trị nhập tay")
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(
            QAbstractItemView.DoubleClicked if not has_manual_block else QAbstractItemView.NoEditTriggers
        )
        self.table.setStyleSheet(
            f"""
            QTableWidget {{
                background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: {CORNER_RADIUS}px;
                font-size: 13px; color: {COLOR_TEXT_PRIMARY};
            }}
            QHeaderView::section {{
                background-color: {_PILL_BG}; color: {COLOR_TEXT_PRIMARY}; font-weight: 700;
                padding: 6px; border: none; border-bottom: 1px solid {COLOR_BORDER};
            }}
            """
        )
        layout.addWidget(self.table, 1)

        self._has_manual_block = has_manual_block
        self._fill_table()

        # ---- Chọn thư mục lưu (theo quy ước chung mục 0 — không ghi đè gốc) ----
        dir_row = QHBoxLayout()
        dir_row.addWidget(QLabel("Thư mục lưu kết quả"))
        self.dir_edit = _RenameFormPage._styled_line_edit("Chưa chọn thư mục...")
        self.dir_edit.setReadOnly(True)
        dir_row.addWidget(self.dir_edit, 1)
        browse_btn = QPushButton("Duyệt...")
        browse_btn.setCursor(Qt.PointingHandCursor)
        browse_btn.setFixedHeight(CONTROL_HEIGHT)
        browse_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                font-size: 13px; font-weight: 700; padding: 0 14px;
            }}
            QPushButton:hover {{ background-color: {_PILL_BG}; }}
            """
        )
        browse_btn.clicked.connect(self._on_browse_clicked)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # ---- Nút Hủy / Xác nhận ----
        button_row = QHBoxLayout()
        button_row.addStretch()
        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(CONTROL_HEIGHT)
        cancel_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {_PILL_BG}; }}
            """
        )
        cancel_btn.clicked.connect(self.reject)
        button_row.addWidget(cancel_btn)

        self.confirm_btn = QPushButton("Xác nhận đổi tên")
        self.confirm_btn.setCursor(Qt.PointingHandCursor)
        self.confirm_btn.setFixedHeight(CONTROL_HEIGHT)
        self.confirm_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ACCENT}; color: white; border: none;
                border-radius: {CORNER_RADIUS}px; font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: #E28104; }}
            """
        )
        self.confirm_btn.clicked.connect(self._on_confirm_clicked)
        button_row.addWidget(self.confirm_btn)
        layout.addLayout(button_row)

    def _fill_table(self) -> None:
        batch_size = len(self.files)
        for row_index, (path, current_name) in enumerate(self.files):
            values = dict(self.base_values)
            values = self._apply_batch_progression(values, row_index)

            self.table.setItem(row_index, 0, self._readonly_item(current_name))
            col = 1
            if self._has_manual_block:
                manual_edit = _RenameFormPage._styled_line_edit("Nhập giá trị cho file này")
                manual_edit.setText(self._manual_edits.get(row_index, values.get("manual_sample", "")))
                manual_edit.textChanged.connect(
                    lambda text, i=row_index: self._on_manual_edit_changed(i, text)
                )
                self.table.setCellWidget(row_index, 1, manual_edit)
                col = 2
            values["manual_sample"] = self._manual_edits.get(row_index, values.get("manual_sample", ""))
            new_name = _preview_generate_name(self.profile, values, batch_size=batch_size)
            self.table.setItem(row_index, col, self._readonly_item(new_name))

    def _apply_batch_progression(self, values: dict, row_index: int) -> dict:
        """TẠM THỜI — mô phỏng quy tắc xoay vòng Ngày/Ca (mục 3) và tăng dần Số thứ
        tự/Ngày (mục 4) chỉ để bảng xem trước có dữ liệu khác nhau từng dòng. Thay
        bằng rename_engine.py thật khi nối logic."""
        values = dict(values)
        if self.profile["type"] == "van_hanh":
            base_date: datetime.date = values.get("date") or datetime.date.today()
            if self.profile.get("has_ca"):
                ca_count = self.profile.get("ca_count", _DEFAULT_CA_COUNT)
                start_ca = values.get("ca_index", 1)
                absolute = (start_ca - 1) + row_index
                values["ca_index"] = (absolute % ca_count) + 1
                values["date"] = base_date + datetime.timedelta(days=absolute // ca_count)
            else:
                values["date"] = base_date + datetime.timedelta(days=row_index)
        else:
            start = values.get("auto_number_start")
            step = values.get("auto_number_step", 1)
            if start is not None:
                values["auto_number_start"] = start + row_index * step
            for block in self.profile.get("blocks", []):
                if block["type"] == "date" and block.get("config", {}).get("increment_daily"):
                    base_date = values.get("date") or datetime.date.today()
                    values["date"] = base_date + datetime.timedelta(days=row_index)
        return values

    def _on_manual_edit_changed(self, row_index: int, text: str) -> None:
        self._manual_edits[row_index] = text
        values = self._apply_batch_progression(dict(self.base_values), row_index)
        values["manual_sample"] = text
        new_name = _preview_generate_name(self.profile, values, batch_size=len(self.files))
        col = 2 if self._has_manual_block else 1
        self.table.setItem(row_index, col, self._readonly_item(new_name))

    @staticmethod
    def _readonly_item(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        return item

    def _on_browse_clicked(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu kết quả")
        if directory:
            self._output_dir = directory
            self.dir_edit.setText(directory)

    def _on_confirm_clicked(self) -> None:
        if not self._output_dir:
            QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng chọn thư mục lưu kết quả trước.")
            return
        # CHƯA NỐI LOGIC THẬT — sẽ gọi rename_engine.py + ghi file thật ở phiên sau.
        info_box = QMessageBox(self)
        info_box.setWindowTitle("Chưa nối logic thật")
        info_box.setIcon(QMessageBox.Information)
        info_box.setText(
            "Đây là bản demo giao diện — chức năng đổi tên & ghi file thật sẽ được "
            "nối logic ở phiên làm việc sau."
        )
        info_box.setStyleSheet(
            f"""
            QMessageBox {{ background-color: white; }}
            QMessageBox QLabel {{ color: {COLOR_TEXT_PRIMARY}; font-size: 13px; }}
            QPushButton {{
                background-color: {COLOR_ACCENT}; color: white; border: none;
                border-radius: {CORNER_RADIUS}px; padding: 6px 14px; font-size: 13px; font-weight: 700; min-width: 90px;
            }}
            QPushButton:hover {{ background-color: #E28104; }}
            """
        )
        info_box.exec()
        self.accept()


# ----------------------------------------------------------------------
# Widget chính
# ----------------------------------------------------------------------
class RenameFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Hồ sơ mẫu — HOÀN TOÀN trong bộ nhớ ở bước này (xem docstring đầu file).
        self._profiles: List[dict] = []
        self._selected_profile_id: Optional[str] = None
        self._selected_row: Optional[_FileRow] = None
        self._is_locked = False

        # Tạo sẵn rename_profiles.json rỗng cạnh config.json nếu chưa có, theo
        # 08_dac_ta_doi_ten.md mục 2 — CHƯA đọc/ghi nội dung thật từ file này.
        self._ensure_profiles_file_exists()

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # ================= CỘT A (40%) =================
        column_a = QVBoxLayout()
        column_a.setSpacing(14)

        self.drop_zone = _DropZone()
        self.drop_zone.files_selected.connect(self._on_files_selected)
        column_a.addWidget(self.drop_zone)

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
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; background: transparent; border: none;"
        )
        list_header.addWidget(self.list_count_label)
        list_header.addStretch()

        self.lock_badge = QLabel(" Đã khóa")
        self.lock_badge.setStyleSheet(
            f"background-color: {_PILL_BG}; color: {COLOR_TEXT_SECONDARY}; font-size: 11px; "
            "font-weight: 700; border-radius: 8px; padding: 3px 8px;"
        )
        self.lock_badge.hide()
        list_header.addWidget(self.lock_badge)

        list_card_layout.addLayout(list_header)

        self.empty_hint = QLabel("Chưa có file nào — hãy chọn hoặc kéo-thả file PDF phía trên để bắt đầu.")
        self.empty_hint.setAlignment(Qt.AlignCenter)
        self.empty_hint.setWordWrap(True)
        self.empty_hint.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; padding: 28px 12px; background: transparent; border: none;"
        )
        list_card_layout.addWidget(self.empty_hint)

        self.file_list = _DraggableFileList()
        self.file_list.row_drag_dropped.connect(self._on_row_drag_dropped)
        list_card_layout.addWidget(self.file_list, 1)

        column_a.addWidget(list_card, 1)

        # --- Hàng nút: Tạo biểu mẫu / Clear / Đổi tên ---
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        self.create_profile_btn = QToolButton()
        self.create_profile_btn.setText(" Tạo biểu mẫu")
        self.create_profile_btn.setIcon(qta.icon("mdi6.plus-box-outline", color=COLOR_TEXT_PRIMARY))
        self.create_profile_btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.create_profile_btn.setCursor(Qt.PointingHandCursor)
        self.create_profile_btn.setFixedHeight(CONTROL_HEIGHT)
        self.create_profile_btn.setStyleSheet(
            f"""
            QToolButton {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                font-size: 13px; font-weight: 700; padding: 0 14px;
            }}
            QToolButton:hover {{ background-color: {_PILL_BG}; }}
            """
        )
        bottom_row.addWidget(self.create_profile_btn)

        self.clear_button = QPushButton(" Clear")
        self.clear_button.setIcon(qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY))
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setFixedHeight(CONTROL_HEIGHT)
        self.clear_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: white; color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG}; border-radius: {CORNER_RADIUS}px;
                font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: {_PILL_BG}; }}
            """
        )
        self.clear_button.clicked.connect(self._on_clear_clicked)
        bottom_row.addWidget(self.clear_button)

        bottom_row.addStretch()

        self.rename_button = QPushButton(" Đổi tên")
        self.rename_button.setIcon(qta.icon("mdi6.form-textbox", color="white"))
        self.rename_button.setCursor(Qt.PointingHandCursor)
        self.rename_button.setFixedHeight(CONTROL_HEIGHT)
        self.rename_button.setMinimumWidth(120)
        self.rename_button.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {COLOR_ACCENT}; color: white; border: none;
                border-radius: {CORNER_RADIUS}px; font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover:enabled {{ background-color: #E28104; }}
            QPushButton:disabled {{ background-color: {COLOR_BORDER_STRONG}; color: {COLOR_TEXT_SECONDARY}; }}
            """
        )
        self.rename_button.clicked.connect(self._on_rename_clicked)
        bottom_row.addWidget(self.rename_button)

        column_a.addLayout(bottom_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        column_a.addWidget(self.result_label)

        # ================= CỘT B (60%) =================
        column_b = QVBoxLayout()

        content_card = QFrame()
        content_card.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: 14px; }}"
        )
        content_card_layout = QVBoxLayout(content_card)
        content_card_layout.setContentsMargins(18, 16, 18, 16)
        content_card_layout.setSpacing(10)

        self.stack = QStackedWidget()
        self.preview_page = _PreviewPage()
        self.form_page = _RenameFormPage()
        self.form_page.values_changed.connect(self._on_form_values_changed)
        self.stack.addWidget(self.preview_page)
        self.stack.addWidget(self.form_page)
        content_card_layout.addWidget(self.stack, 1)

        column_b.addWidget(content_card, 1)

        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, 40)
        root_layout.addWidget(column_b_widget, 60)

        self._rebuild_create_profile_menu()
        self._update_rename_button_state()

    # ------------------------------------------------------------------
    # Hồ sơ mẫu (rename_profiles.json — chỉ tạo rỗng, chưa đọc/ghi thật)
    # ------------------------------------------------------------------
    @staticmethod
    def _ensure_profiles_file_exists() -> None:
        try:
            if not os.path.exists(RENAME_PROFILES_FILE):
                with open(RENAME_PROFILES_FILE, "w", encoding="utf-8") as f:
                    f.write("[]")
        except OSError:
            # Không chặn hiển thị UI nếu vì lý do nào đó không tạo được file —
            # chỉ ảnh hưởng bước lưu hồ sơ thật ở phiên làm việc khác.
            pass

    def _rebuild_create_profile_menu(self) -> None:
        try:
            self.create_profile_btn.clicked.disconnect()
        except (TypeError, RuntimeError):
            pass

        if not self._profiles:
            self.create_profile_btn.setMenu(None)
            self.create_profile_btn.setPopupMode(QToolButton.DelayedPopup)
            self.create_profile_btn.clicked.connect(self._open_create_profile_dialog)
            return

        menu = QMenu(self.create_profile_btn)
        menu.setStyleSheet(
            f"QMenu {{ background-color: white; color: {COLOR_TEXT_PRIMARY}; border: 1px solid {COLOR_BORDER}; }}"
            f"QMenu::item:selected {{ background-color: {_PILL_BG}; color: {COLOR_TEXT_PRIMARY}; }}"
            f"QMenu::separator {{ height: 1px; background: {COLOR_BORDER}; margin: 4px 8px; }}"
        )
        for profile in self._profiles:
            label = f"{profile['name']}  ({_profile_type_label(profile['type'])})"
            menu.addAction(label, lambda p=profile: self._apply_profile(p))
        menu.addSeparator()
        menu.addAction(
            qta.icon("mdi6.plus", color=COLOR_TEXT_PRIMARY), "Tạo biểu mẫu mới",
            self._open_create_profile_dialog,
        )
        menu.addAction(
            qta.icon("mdi6.cog-outline", color=COLOR_TEXT_PRIMARY), "Quản lý biểu mẫu...",
            self._open_manage_profiles_dialog,
        )
        self.create_profile_btn.setPopupMode(QToolButton.InstantPopup)
        self.create_profile_btn.setMenu(menu)

    def _open_create_profile_dialog(self) -> None:
        existing_names = [p["name"] for p in self._profiles]
        dialog = _ProfileFormDialog(existing_names, parent=self)
        if dialog.exec() == QDialog.Accepted:
            new_profile = dialog.get_profile()
            self._profiles.append(new_profile)
            self._rebuild_create_profile_menu()
            self._apply_profile(new_profile)

    def _open_manage_profiles_dialog(self) -> None:
        dialog = _ManageProfilesDialog(self._profiles, parent=self)
        dialog.profiles_changed.connect(self._on_profiles_changed_in_manage_dialog)
        dialog.exec()
        self._rebuild_create_profile_menu()

    def _on_profiles_changed_in_manage_dialog(self) -> None:
        # Nếu hồ sơ đang áp dụng bị sửa/xóa trong dialog Quản lý, đồng bộ lại Cột B.
        if self._selected_profile_id is not None:
            current = next((p for p in self._profiles if p["id"] == self._selected_profile_id), None)
            if current is None:
                self._on_clear_clicked()
            else:
                self.form_page.set_profile(current)

    def _apply_profile(self, profile: dict) -> None:
        self._selected_profile_id = profile["id"]
        self._set_locked(True)
        self.form_page.set_profile(profile)
        self.stack.setCurrentWidget(self.form_page)
        self._update_rename_button_state()
        self._hide_result()

    # ------------------------------------------------------------------
    # Khóa/mở khóa Cột A
    # ------------------------------------------------------------------
    def _set_locked(self, locked: bool) -> None:
        self._is_locked = locked
        self.drop_zone.set_locked(locked)
        self.file_list.set_locked(locked)
        self.lock_badge.setVisible(locked)
        for i in range(self.file_list.count()):
            row = self.file_list.itemWidget(self.file_list.item(i))
            if row is not None:
                row.set_locked(locked)

    # ------------------------------------------------------------------
    # Quản lý danh sách file (Cột A) — cùng cơ chế với merge_widget.py
    # ------------------------------------------------------------------
    def _add_file_row(
        self, path: str, name: str, size_text: str, pages: int, index: Optional[int] = None
    ) -> _FileRow:
        row = _FileRow(path, name, size_text, pages)
        item = QListWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        item.setSizeHint(QSize(0, 66))
        if index is None:
            self.file_list.addItem(item)
        else:
            self.file_list.insertItem(index, item)
        self.file_list.setItemWidget(item, row)
        row.list_widget = self.file_list
        row.set_locked(self._is_locked)
        row.clicked.connect(lambda r=row: self._select_row(r))
        row.remove_requested.connect(lambda r=row: self._remove_row(r))
        self._update_header_count()
        self._renumber_rows()
        return row

    def _renumber_rows(self) -> None:
        for i in range(self.file_list.count()):
            row = self.file_list.itemWidget(self.file_list.item(i))
            if row is not None:
                row.set_order(i + 1)

    def _find_item_for_row(self, row: _FileRow) -> Optional[QListWidgetItem]:
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if self.file_list.itemWidget(item) is row:
                return item
        return None

    def _remove_row(self, row: _FileRow) -> None:
        if self._is_locked:
            return
        item = self._find_item_for_row(row)
        if item is None:
            return
        was_selected = row is self._selected_row
        self.file_list.takeItem(self.file_list.row(item))
        row.deleteLater()
        self._update_header_count()
        self._renumber_rows()
        if was_selected:
            self._select_first_available()
        self._hide_result()
        self._update_rename_button_state()

    def _move_row(self, from_index: int, to_index: int) -> None:
        if self._is_locked:
            return
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

        path, name, size_text, pages = old_row.path, old_row.name, old_row.size_text, old_row.pages
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

    # ------------------------------------------------------------------
    # Sự kiện
    # ------------------------------------------------------------------
    def _on_files_selected(self, paths: List[str]) -> None:
        if self._is_locked:
            return
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
            self._show_error(f"Không thể thêm {len(skipped)} file: " + "; ".join(skipped))
        else:
            self._hide_result()
        self._update_rename_button_state()

    def _on_clear_clicked(self) -> None:
        self.file_list.clear()
        self._selected_row = None
        self._selected_profile_id = None
        self._set_locked(False)
        self.form_page.set_profile(None)
        self.stack.setCurrentWidget(self.preview_page)
        self.preview_page.show_empty()
        self._update_header_count()
        self._hide_result()
        self._update_rename_button_state()

    def _select_row(self, row: _FileRow) -> None:
        if self._selected_row is not None:
            self._selected_row.set_selected(False)
        row.set_selected(True)
        self._selected_row = row
        # Cột B chỉ đổi trang khi CHỌN/BỎ CHỌN hồ sơ (đúng bảng 6.1), không phải
        # khi đổi file đang xem — nên chỉ cần nạp preview khi trang Preview đang
        # hiển thị (lúc chưa khóa Cột A bằng hồ sơ nào).
        if self.stack.currentWidget() is self.preview_page:
            self.preview_page.show_file(row.path)

    def _select_first_available(self) -> None:
        if self.file_list.count() == 0:
            self._selected_row = None
            self.preview_page.show_empty()
            return
        first_row = self.file_list.itemWidget(self.file_list.item(0))
        self._select_row(first_row)

    def _on_form_values_changed(self) -> None:
        self._update_rename_button_state()

    def _update_rename_button_state(self) -> None:
        has_files = self.file_list.count() > 0
        has_profile = self._selected_profile_id is not None and self.form_page.is_valid()
        self.rename_button.setEnabled(has_files and has_profile)

    def _on_rename_clicked(self) -> None:
        profile = next((p for p in self._profiles if p["id"] == self._selected_profile_id), None)
        if profile is None or self.file_list.count() == 0:
            return

        files: List[Tuple[str, str]] = []
        for i in range(self.file_list.count()):
            row = self.file_list.itemWidget(self.file_list.item(i))
            files.append((row.path, row.name))

        base_values = self.form_page.current_values()
        dialog = _RenamePreviewDialog(files, profile, base_values, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._show_success(
                "Đã xem trước xong — chức năng ghi file đổi tên thật sẽ được nối logic ở phiên làm việc sau."
            )

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