"""
/src/ui/tools/compress_widget.py

Giao diện tính năng Nén file PDF (Ver2).

Widget chỉ lo giao diện; toàn bộ logic nén nằm ở `src/compress_engine.py` (file riêng cho
tính năng này, không đụng vào pdf_core.py dùng chung). Widget không tự xử lý PDF.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QUrl, QEventLoop, QThread, QObject
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QDesktopServices,
    QFontMetrics,
    QPainter,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QScrollArea,
    QFrame,
    QFileDialog,
    QCheckBox,
    QProgressBar,
    QStackedWidget,
    QButtonGroup,
    QDialog,
    QSizePolicy,
)

from src.compress_engine import (
    CompressError,
    compress_pdf,
    has_digital_signature,
    render_compressed_page,
)
from src.pdf_core import (
    CorruptedFileError,
    FileLockedError,
    PageInfo,
    PageRenderer,
    PasswordProtectedError,
    list_page_infos,
)
from src.logger import log_error, log_info

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
# Hằng số giao diện & mặc định
# ----------------------------------------------------------------------
_THUMB_STRIP_WIDTH = 115
_THUMB_W, _THUMB_H = 72, 94
_BADGE_SIZE = 18

_ZOOM_MIN = 0.5
_ZOOM_MAX = 2.0
_ZOOM_STEP = 0.15
_ZOOM_DEFAULT = 1.0

_PREVIEW_SIDE_MARGIN = 12
_PREVIEW_MIN_PAGE_WIDTH = 220
_PREVIEW_PAGE_WIDTH_FALLBACK = 340
_PREVIEW_PAGE_HEIGHT_DEFAULT = 460

_DEFAULT_OUTPUT_SUFFIX = "_compressed"

# Mức nén: (khóa truyền cho hàm lõi, nhãn hiển thị). Thứ tự = thứ tự nút phân đoạn.
_LEVELS = [
    ("light", "Nhẹ"),
    ("medium", "Vừa"),
    ("strong", "Mạnh"),
    ("max", "Tối đa"),
]
_DEFAULT_LEVEL_INDEX = 1  # Vừa

# Mô tả ngắn từng mức — TẠM theo bảng GỢI Ý mục 3 file yêu cầu, chốt lại sau khi thử file thật.
_LEVEL_HINTS = [
    "Chỉ nén không mất dữ liệu, không đụng vào ảnh. Hợp với file Word; với file scan ít hiệu quả.",
    "Hạ ảnh xuống ~150 DPI, JPEG ~70, giữ màu. Mức khuyến nghị.",
    "Hạ ảnh xuống ~120 DPI, JPEG ~55. File nhỏ hơn, chữ nhỏ bắt đầu kém sắc nét.",
    "Hạ ảnh xuống ~100 DPI, JPEG ~45. Nhỏ nhất, chữ nhỏ có thể khó đọc — nên bấm Xem thử trước.",
]

_LABEL_STYLE = f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; background: transparent; border: none;"
_NOTE_STYLE = f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;"

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

# Dùng cho khung so sánh (cần cuộn cả ngang lẫn dọc)
_SCROLLBAR_QSS_BOTH = _SCROLLBAR_QSS + f"""
    QScrollBar:horizontal {{
        background: transparent;
        height: 8px;
        margin: 0px 4px 2px 4px;
    }}
    QScrollBar::handle:horizontal {{
        background: {COLOR_BORDER_STRONG};
        border-radius: 4px;
        min-width: 32px;
    }}
    QScrollBar::handle:horizontal:hover {{
        background: {COLOR_ACCENT};
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0px;
        background: transparent;
        border: none;
    }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
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


def _secondary_button_qss() -> str:
    return f"""
        QPushButton {{
            background-color: white;
            color: {COLOR_TEXT_PRIMARY};
            border: 1.5px solid {COLOR_BORDER_STRONG};
            border-radius: {CORNER_RADIUS}px;
            font-size: 13px;
            font-weight: 700;
            padding: 0 16px;
        }}
        QPushButton:hover:enabled {{ background-color: #F3F4F6; }}
        QPushButton:pressed:enabled {{ background-color: #E5E7EB; }}
        QPushButton:disabled {{
            background-color: #F9FAFB;
            color: #9CA3AF;
            border-color: {COLOR_BORDER};
        }}
    """


def _primary_button_qss() -> str:
    return f"""
        QPushButton {{
            background-color: {COLOR_ACCENT};
            color: white;
            border: none;
            border-radius: {CORNER_RADIUS}px;
            font-size: 13px;
            font-weight: 700;
            padding: 0 16px;
        }}
        QPushButton:hover:enabled {{ background-color: #E28104; }}
        QPushButton:pressed:enabled {{ background-color: #C87203; }}
        QPushButton:disabled {{
            background-color: {COLOR_ACCENT};
            color: white;
        }}
    """


def _format_size(num_bytes: int) -> str:
    """Định dạng dung lượng dễ đọc (B / KB / MB / GB)."""
    size = float(max(0, num_bytes))
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"


def _set_elided(label: QLabel, text: str, max_px: int) -> None:
    """Gán text cho label, cắt giữa bằng '…' nếu dài hơn max_px; tooltip giữ tên đầy đủ."""
    metrics = QFontMetrics(label.font())
    label.setText(metrics.elidedText(text, Qt.ElideMiddle, max_px))
    label.setToolTip(text)


# ----------------------------------------------------------------------
# A1 — Khối chọn file đơn (Single DropZone)
# ----------------------------------------------------------------------
class _SingleDropZone(QFrame):
    file_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setFixedHeight(82)
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
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(14)
        layout.setAlignment(Qt.AlignCenter)

        icon_box = QFrame()
        icon_box.setFixedSize(44, 44)
        icon_box.setStyleSheet(
            f"""
            QFrame {{
                background-color: white;
                border: 1.5px solid {COLOR_ACCENT};
                border-radius: 10px;
            }}
            """
        )
        icon_box_layout = QVBoxLayout(icon_box)
        icon_box_layout.setContentsMargins(0, 0, 0, 0)
        icon_box_layout.setAlignment(Qt.AlignCenter)
        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.tray-arrow-up", color=COLOR_ACCENT).pixmap(QSize(22, 22)))
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_box_layout.addWidget(icon_label)
        layout.addWidget(icon_box)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        text_col.setContentsMargins(0, 0, 0, 0)

        self.main_label = QLabel("Chọn file hoặc kéo-thả file vào đây")
        self.main_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        text_col.addWidget(self.main_label)

        note_label = QLabel("Lưu ý: CHỈ CHỌN 1 FILE")
        note_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
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
# Segmented Button
# ----------------------------------------------------------------------
class _SegmentedControl(QFrame):
    selection_changed = Signal(int)

    def __init__(self, options: List[str], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedHeight(38)
        self.setStyleSheet(
            """
            QFrame {
                background-color: #F1F5F9;
                border-radius: 8px;
            }
            """
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self.button_group = QButtonGroup(self)
        self.buttons: List[QPushButton] = []

        for idx, text in enumerate(options):
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(32)
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background-color: transparent;
                    color: {COLOR_TEXT_SECONDARY};
                    border: none;
                    border-radius: 6px;
                    font-size: 13px;
                    font-weight: 600;
                }}
                QPushButton:checked {{
                    background-color: white;
                    color: {COLOR_TEXT_PRIMARY};
                    font-weight: 700;
                }}
                """
            )
            self.button_group.addButton(btn, idx)
            layout.addWidget(btn)
            self.buttons.append(btn)

        self.buttons[0].setChecked(True)
        self.button_group.idClicked.connect(self.selection_changed.emit)

    def current_index(self) -> int:
        return self.button_group.checkedId()

    def set_current_index(self, index: int) -> None:
        if 0 <= index < len(self.buttons):
            self.buttons[index].setChecked(True)


# ----------------------------------------------------------------------
# Cột B — Các thành phần Preview
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
        layout.setSpacing(2)

        badge_row = QHBoxLayout()
        self.badge = QLabel(str(page_number))
        self.badge.setFixedSize(_BADGE_SIZE, _BADGE_SIZE)
        self.badge.setAlignment(Qt.AlignCenter)
        badge_row.addWidget(self.badge)
        badge_row.addStretch()
        layout.addLayout(badge_row)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(self.image_label, 1)

        self._apply_style()

    def sizeHint(self) -> QSize:
        return QSize(_THUMB_W, _THUMB_H)

    def minimumSizeHint(self) -> QSize:
        return QSize(_THUMB_W, _THUMB_H)

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

    def set_thumbnail(self, pixmap: QPixmap) -> None:
        """Gán ảnh render thật của trang. Bỏ qua im lặng nếu ảnh rỗng/lỗi — giữ khung
        trắng làm placeholder, không làm crash UI."""
        if pixmap is None or pixmap.isNull():
            return
        avail_w = max(1, _THUMB_W - 12)
        avail_h = max(1, _THUMB_H - _BADGE_SIZE - 10)
        scaled = pixmap.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(scaled)

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        self.clicked.emit(self.page_number)


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


class _PreviewPage(QFrame):
    """Khung hiển thị 1 trang PDF ở Cột B (không vẽ chồng gì thêm lên trang)."""

    def __init__(self, page_number: int, aspect_ratio: Optional[float] = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.aspect_ratio = aspect_ratio or (_PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK)
        self.page_pixmap: Optional[QPixmap] = None
        self.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
        )

    def set_page_pixmap(self, pixmap: QPixmap) -> None:
        self.page_pixmap = pixmap
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.page_pixmap is not None and not self.page_pixmap.isNull():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(self.rect(), self.page_pixmap, self.page_pixmap.rect())
            painter.end()


class _CompareSide(QWidget):
    """1 bên của khung so sánh Xem thử: tiêu đề + ảnh trang ở 100%, cuộn/kéo được."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(self.title_label)

        self.scroll = _PannablePreviewScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {COLOR_CONTENT_BG};
                border: 1px solid {COLOR_BORDER};
                border-radius: 10px;
            }}
            {_SCROLLBAR_QSS_BOTH}
            """
        )
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.image_label.setStyleSheet("background: white; border: none;")
        self.scroll.setWidget(self.image_label)
        layout.addWidget(self.scroll, 1)

    def set_pixmap(self, pixmap: QPixmap) -> None:
        self.image_label.setPixmap(pixmap)
        self.image_label.resize(pixmap.size())

    def clear(self) -> None:
        self.image_label.clear()
        self.image_label.resize(1, 1)


# ----------------------------------------------------------------------
# Dialog xác nhận trùng tên file (Ghi đè / Đổi tên khác / Hủy)
# ----------------------------------------------------------------------
class _OverwriteConfirmDialog(QDialog):

    RESULT_OVERWRITE = "overwrite"
    RESULT_RENAME = "rename"
    RESULT_CANCEL = "cancel"

    def __init__(self, filename: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trùng tên file")
        self.setModal(True)
        self.setFixedWidth(420)
        self._result = self.RESULT_CANCEL

        self.setStyleSheet("QDialog { background-color: white; }")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(18)

        message_row = QHBoxLayout()
        message_row.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.alert", color=COLOR_ACCENT).pixmap(QSize(28, 28)))
        icon_label.setStyleSheet("background: transparent; border: none;")
        icon_label.setAlignment(Qt.AlignTop)
        message_row.addWidget(icon_label)

        text_label = QLabel(
            f"File '{filename}' đã tồn tại trong thư mục đã chọn.\nBạn muốn làm gì?"
        )
        text_label.setWordWrap(True)
        text_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 500; "
            "background: transparent; border: none;"
        )
        message_row.addWidget(text_label, 1)
        layout.addLayout(message_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        overwrite_btn = QPushButton("Ghi đè")
        overwrite_btn.setCursor(Qt.PointingHandCursor)
        overwrite_btn.setFixedHeight(CONTROL_HEIGHT)
        overwrite_btn.setStyleSheet(
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
        overwrite_btn.clicked.connect(self._on_overwrite)
        button_row.addWidget(overwrite_btn)

        rename_btn = QPushButton("Đổi tên khác")
        rename_btn.setCursor(Qt.PointingHandCursor)
        rename_btn.setFixedHeight(CONTROL_HEIGHT)
        rename_btn.setStyleSheet(self._secondary_btn_qss())
        rename_btn.clicked.connect(self._on_rename)
        button_row.addWidget(rename_btn)

        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(CONTROL_HEIGHT)
        cancel_btn.setStyleSheet(self._secondary_btn_qss())
        cancel_btn.clicked.connect(self._on_cancel)
        button_row.addWidget(cancel_btn)

        layout.addLayout(button_row)

    def _secondary_btn_qss(self) -> str:
        return f"""
            QPushButton {{
                background-color: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                font-size: 13px;
                font-weight: 600;
                padding: 0 16px;
            }}
            QPushButton:hover {{ background-color: #F3F4F6; }}
            QPushButton:pressed {{ background-color: #E5E7EB; }}
        """

    def _on_overwrite(self) -> None:
        self._result = self.RESULT_OVERWRITE
        self.accept()

    def _on_rename(self) -> None:
        self._result = self.RESULT_RENAME
        self.accept()

    def _on_cancel(self) -> None:
        self._result = self.RESULT_CANCEL
        self.reject()

    @staticmethod
    def ask(parent: Optional[QWidget], filename: str) -> str:
        dialog = _OverwriteConfirmDialog(filename, parent)
        dialog.exec()
        return dialog._result


# ----------------------------------------------------------------------
# Luồng nền chạy nén (không chặn UI)
# ----------------------------------------------------------------------
class _CompressWorker(QThread):
    """Chạy nén ở luồng nền bằng compress_engine.compress_pdf. Chỉ phát tín hiệu kết quả,
    không đụng widget trực tiếp."""

    succeeded = Signal(dict)
    failed = Signal(str, str)  # (loại lỗi: password|corrupt|locked|check|unknown, thông điệp)

    def __init__(self, src_path: str, dst_path: str, level_key: str,
                 to_grayscale: bool, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._src = src_path
        self._dst = dst_path
        self._level_key = level_key
        self._gray = to_grayscale

    def run(self) -> None:
        try:
            result = compress_pdf(self._src, self._level_key, self._dst, self._gray)
            self.succeeded.emit(dict(result))
        except PasswordProtectedError:
            self.failed.emit("password", "File có mật khẩu, không thể xử lý.")
        except CorruptedFileError:
            self.failed.emit("corrupt", "File PDF hỏng hoặc không đọc được.")
        except FileLockedError:
            self.failed.emit("locked", "File đang được sử dụng bởi chương trình khác, vui lòng đóng và thử lại.")
        except ValueError as exc:
            self.failed.emit("unknown", str(exc))
        except CompressError as exc:
            log_error("Nén PDF không đạt kiểm tra", exc)
            self.failed.emit("check", str(exc))
        except Exception as exc:  # không để luồng nền chết âm thầm
            log_error("Lỗi không xác định khi nén PDF", exc)
            self.failed.emit("unknown", f"Đã xảy ra lỗi khi nén file: {exc}")


# ----------------------------------------------------------------------
# Widget Chính (CompressFeatureWidget)
# ----------------------------------------------------------------------
class CompressFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._current_file_path: Optional[str] = None
        self._current_page_infos: List[PageInfo] = []
        self._current_total_pages = 0
        self._current_page = 0
        self._preview_thumbs: List[_PreviewThumb] = []
        self._preview_pages: Dict[int, _PreviewPage] = {}
        self._renderer = PageRenderer()
        # True khi result_label đang hiện thông báo "đang tải file"
        self._is_loading = False

        self._zoom_level: float = _ZOOM_DEFAULT
        self._current_preview_width: Optional[int] = None
        self._initial_width_applied = False

        # Trạng thái nén / xem thử
        self._worker: Optional[_CompressWorker] = None
        self._last_job: Optional[tuple] = None  # (save_path, level_index, gray) cho nút Thử lại
        self._is_busy = False
        self._compare_active = False

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # ================= CỘT A (40%) =================
        column_a = QVBoxLayout()
        column_a.setSpacing(14)

        # --- A1: Single DropZone ---
        self.drop_zone = _SingleDropZone()
        self.drop_zone.file_selected.connect(self._on_file_selected)
        column_a.addWidget(self.drop_zone)

        # --- A2: Card tùy chọn nén ---
        config_card = QFrame()
        config_card.setObjectName("configCard")
        config_card.setStyleSheet(
            f"QFrame#configCard {{ background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: 14px; }}"
        )
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(18, 16, 18, 16)
        config_layout.setSpacing(14)

        card_title = QLabel("Tùy chọn nén")
        card_title.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        config_layout.addWidget(card_title)

        # --- Thông tin file đã chọn ---
        info_box = QFrame()
        info_box.setObjectName("infoBox")
        info_box.setStyleSheet(
            f"QFrame#infoBox {{ background-color: {COLOR_CONTENT_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 10px; }}"
        )
        info_layout = QVBoxLayout(info_box)
        info_layout.setContentsMargins(12, 10, 12, 10)
        info_layout.setSpacing(6)

        self.info_name_value = self._add_info_row(info_layout, "Tên file")
        self.info_pages_value = self._add_info_row(info_layout, "Số trang")
        self.info_size_value = self._add_info_row(info_layout, "Dung lượng gốc")

        # Cảnh báo chữ ký số (ẩn mặc định)
        self.signature_warning = QFrame()
        self.signature_warning.setObjectName("sigWarn")
        self.signature_warning.setStyleSheet(
            f"QFrame#sigWarn {{ background-color: {COLOR_ACCENT_LIGHT}; border: 1px solid {COLOR_ACCENT}; border-radius: 8px; }}"
        )
        sig_layout = QHBoxLayout(self.signature_warning)
        sig_layout.setContentsMargins(10, 8, 10, 8)
        sig_layout.setSpacing(8)
        sig_icon = QLabel()
        sig_icon.setPixmap(qta.icon("mdi6.alert-outline", color=COLOR_ACCENT).pixmap(QSize(18, 18)))
        sig_icon.setAlignment(Qt.AlignTop)
        sig_icon.setStyleSheet("background: transparent; border: none;")
        sig_layout.addWidget(sig_icon)
        sig_text = QLabel("File có chữ ký số. Nén sẽ làm mất hiệu lực chữ ký số.")
        sig_text.setWordWrap(True)
        sig_text.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 12px; font-weight: 600; background: transparent; border: none;"
        )
        sig_layout.addWidget(sig_text, 1)
        self.signature_warning.hide()
        info_layout.addWidget(self.signature_warning)

        config_layout.addWidget(info_box)

        # --- Chọn mức nén ---
        level_label = QLabel("Mức nén")
        level_label.setStyleSheet(_LABEL_STYLE)
        config_layout.addWidget(level_label)

        self.level_segmented = _SegmentedControl([label for _, label in _LEVELS])
        self.level_segmented.set_current_index(_DEFAULT_LEVEL_INDEX)
        self.level_segmented.selection_changed.connect(self._on_level_changed)
        config_layout.addWidget(self.level_segmented)

        self.level_hint = QLabel(_LEVEL_HINTS[_DEFAULT_LEVEL_INDEX])
        self.level_hint.setWordWrap(True)
        self.level_hint.setStyleSheet(_NOTE_STYLE)
        config_layout.addWidget(self.level_hint)

        # --- Chuyển ảnh xám ---
        self.gray_checkbox = QCheckBox("Chuyển ảnh xám")
        self.gray_checkbox.setCursor(Qt.PointingHandCursor)
        self.gray_checkbox.setStyleSheet(
            f"""
            QCheckBox {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 13px;
                font-weight: 700;
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox:disabled {{ color: #9CA3AF; }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: 4px;
                background-color: white;
            }}
            QCheckBox::indicator:hover:enabled {{ border-color: {COLOR_ACCENT}; }}
            QCheckBox::indicator:checked {{
                background-color: {COLOR_ACCENT};
                border-color: {COLOR_ACCENT};
            }}
            QCheckBox::indicator:disabled {{ background-color: #F3F4F6; }}
            """
        )
        self.gray_checkbox.toggled.connect(self._on_gray_toggled)
        config_layout.addWidget(self.gray_checkbox)

        self.gray_note = QLabel(
            "Giảm thêm dung lượng nhưng dấu đỏ, mực xanh, chữ ký màu sẽ mất màu. "
            "Không áp dụng cho mức Nhẹ."
        )
        self.gray_note.setWordWrap(True)
        self.gray_note.setStyleSheet(_NOTE_STYLE)
        config_layout.addWidget(self.gray_note)

        # --- Ghi chú chung ---
        general_note = QFrame()
        general_note.setObjectName("generalNote")
        general_note.setStyleSheet(
            f"QFrame#generalNote {{ background-color: {COLOR_CONTENT_BG}; border: 1px solid {COLOR_BORDER}; border-radius: 8px; }}"
        )
        note_layout = QHBoxLayout(general_note)
        note_layout.setContentsMargins(10, 8, 10, 8)
        note_layout.setSpacing(8)
        note_icon = QLabel()
        note_icon.setPixmap(qta.icon("mdi6.information-outline", color=COLOR_TEXT_SECONDARY).pixmap(QSize(16, 16)))
        note_icon.setAlignment(Qt.AlignTop)
        note_icon.setStyleSheet("background: transparent; border: none;")
        note_layout.addWidget(note_icon)
        note_text = QLabel(
            "File xuất từ Word (chữ vector) thường giảm rất ít; file scan giảm nhiều hơn."
        )
        note_text.setWordWrap(True)
        note_text.setStyleSheet(_NOTE_STYLE)
        note_layout.addWidget(note_text, 1)
        config_layout.addWidget(general_note)

        # --- Nút Xem thử ---
        self.trial_button = QPushButton(" Xem thử trang đang xem")
        self.trial_button.setIcon(qta.icon("mdi6.eye-outline", color=COLOR_TEXT_PRIMARY))
        self.trial_button.setCursor(Qt.PointingHandCursor)
        self.trial_button.setFixedHeight(CONTROL_HEIGHT)
        self.trial_button.setStyleSheet(_secondary_button_qss())
        self.trial_button.setToolTip("Nén thử trang đang xem trong bộ nhớ và so sánh trước/sau ở độ phóng 100% (không ghi file)")
        self.trial_button.clicked.connect(self._on_trial_clicked)
        config_layout.addWidget(self.trial_button)

        config_layout.addStretch()

        config_card_scroll = QScrollArea()
        config_card_scroll.setWidgetResizable(True)
        config_card_scroll.setFrameShape(QFrame.NoFrame)
        config_card_scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }} {_SCROLLBAR_QSS}")
        config_card_scroll.setWidget(config_card)
        column_a.addWidget(config_card_scroll, 1)

        # --- A3: Hàng nút bấm hành động cuối màn hình (Clear - Lưu File, canh lề trái) ---
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)

        self.clear_button = QPushButton(" Clear")
        self.clear_button.setIcon(qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY))
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setFixedHeight(CONTROL_HEIGHT)
        self.clear_button.setMinimumWidth(90)
        self.clear_button.setStyleSheet(_secondary_button_qss())
        self.clear_button.clicked.connect(self._on_clear_clicked)
        bottom_row.addWidget(self.clear_button)

        self.save_button = QPushButton(" Lưu File")
        self.save_button.setIcon(qta.icon("mdi6.content-save-outline", color="white"))
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.setFixedHeight(CONTROL_HEIGHT)
        self.save_button.setMinimumWidth(130)
        self.save_button.setStyleSheet(_primary_button_qss())
        self.save_button.clicked.connect(self._on_save_clicked)
        bottom_row.addWidget(self.save_button)

        bottom_row.addStretch()
        column_a.addLayout(bottom_row)

        # --- A4: Thanh tiến độ + khu kết quả ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # không xác định
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setStyleSheet(
            f"""
            QProgressBar {{ background-color: #E2E8F0; border: none; border-radius: 3px; }}
            QProgressBar::chunk {{ background-color: {COLOR_ACCENT}; border-radius: 3px; }}
            """
        )
        self.progress_bar.hide()
        column_a.addWidget(self.progress_bar)

        self.result_card = QFrame()
        self.result_card.setObjectName("resultCard")
        self.result_card.setStyleSheet(
            f"QFrame#resultCard {{ background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: 12px; }}"
        )
        result_card_layout = QVBoxLayout(self.result_card)
        result_card_layout.setContentsMargins(16, 12, 16, 12)
        result_card_layout.setSpacing(4)

        self.result_size_label = QLabel("")
        self.result_size_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 15px; font-weight: 700; background: transparent; border: none;"
        )
        result_card_layout.addWidget(self.result_size_label)

        self.result_percent_label = QLabel("")
        self.result_percent_label.setWordWrap(True)
        self.result_percent_label.setStyleSheet(
            f"color: {COLOR_SUCCESS}; font-size: 13px; font-weight: 700; background: transparent; border: none;"
        )
        result_card_layout.addWidget(self.result_percent_label)
        self.result_card.hide()
        column_a.addWidget(self.result_card)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        column_a.addWidget(self.result_label)

        self.retry_button = QPushButton(" Thử lại")
        self.retry_button.setIcon(qta.icon("mdi6.refresh", color=COLOR_TEXT_PRIMARY))
        self.retry_button.setCursor(Qt.PointingHandCursor)
        self.retry_button.setFixedHeight(CONTROL_HEIGHT)
        self.retry_button.setStyleSheet(_secondary_button_qss())
        self.retry_button.clicked.connect(self._on_retry_clicked)
        self.retry_button.hide()
        retry_row = QHBoxLayout()
        retry_row.addWidget(self.retry_button)
        retry_row.addStretch()
        column_a.addLayout(retry_row)

        # ================= CỘT B (60%) — Preview =================
        column_b = QVBoxLayout()

        preview_card = QFrame()
        preview_card.setObjectName("previewCard")
        preview_card.setStyleSheet(
            f"QFrame#previewCard {{ background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: 14px; }}"
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

        # Nút thoát chế độ so sánh Xem thử (chỉ hiện khi đang so sánh)
        self.exit_compare_btn = QPushButton(" Quay lại xem trước")
        self.exit_compare_btn.setIcon(qta.icon("mdi6.arrow-left", color=COLOR_TEXT_PRIMARY))
        self.exit_compare_btn.setCursor(Qt.PointingHandCursor)
        self.exit_compare_btn.setFixedHeight(28)
        self.exit_compare_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: 6px;
                font-size: 12px;
                font-weight: 700;
                padding: 0 10px;
            }}
            QPushButton:hover {{ background-color: {COLOR_ACCENT_LIGHT}; border-color: {COLOR_ACCENT}; }}
            """
        )
        self.exit_compare_btn.clicked.connect(self._exit_compare_mode)
        self.exit_compare_btn.hide()
        header_row.addWidget(self.exit_compare_btn)

        # Zoom Controls
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

        # Strip Thumbnails trái
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

        # Vùng bên phải thumbnail: trang 0 = xem trước bình thường, trang 1 = so sánh Xem thử.
        # Dùng QStackedWidget để giữ đúng 1 vùng kích thước cố định cho cả 2 trạng thái.
        self.right_stack = QStackedWidget()
        self.right_stack.setStyleSheet("QStackedWidget { background: transparent; border: none; }")

        # Pannable Scroll Area cho khung Preview chính
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
        self.right_stack.addWidget(self.preview_scroll_b)

        # --- Trang so sánh Xem thử ---
        compare_page = QWidget()
        compare_page.setStyleSheet("background: transparent;")
        compare_layout = QVBoxLayout(compare_page)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        compare_layout.setSpacing(8)

        self.compare_info_label = QLabel("")
        self.compare_info_label.setWordWrap(True)
        self.compare_info_label.setStyleSheet(_NOTE_STYLE)
        compare_layout.addWidget(self.compare_info_label)

        compare_sides = QHBoxLayout()
        compare_sides.setSpacing(10)
        self.compare_before = _CompareSide("Trước (gốc)")
        self.compare_after = _CompareSide("Sau (nén thử)")
        compare_sides.addWidget(self.compare_before, 1)
        compare_sides.addWidget(self.compare_after, 1)
        compare_layout.addLayout(compare_sides, 1)
        self._link_scrollbars(self.compare_before.scroll, self.compare_after.scroll)
        self.right_stack.addWidget(compare_page)

        body_row.addWidget(self.right_stack, 1)

        preview_card_layout.addLayout(body_row, 1)
        column_b.addWidget(preview_card, 1)

        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, 40)
        root_layout.addWidget(column_b_widget, 60)

        self._reset_file_info()
        self._show_empty_preview()
        self._update_controls_state()

    # ------------------------------------------------------------------
    # Dựng thành phần phụ
    # ------------------------------------------------------------------
    def _add_info_row(self, parent_layout: QVBoxLayout, caption: str) -> QLabel:
        """Thêm 1 dòng 'Nhãn: giá trị' vào khối thông tin file, trả về label giá trị."""
        row = QHBoxLayout()
        row.setSpacing(10)
        cap = QLabel(caption)
        cap.setFixedWidth(100)
        cap.setStyleSheet(_NOTE_STYLE)
        value = QLabel("—")
        value.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent; border: none;"
        )
        value.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row.addWidget(cap)
        row.addWidget(value, 1)
        parent_layout.addLayout(row)
        return value

    @staticmethod
    def _link_scrollbars(a: QScrollArea, b: QScrollArea) -> None:
        """Đồng bộ cuộn 2 khung so sánh (setValue không phát lại tín hiệu nếu giá trị không đổi
        nên không bị lặp vô hạn)."""
        for bar_a, bar_b in (
            (a.verticalScrollBar(), b.verticalScrollBar()),
            (a.horizontalScrollBar(), b.horizontalScrollBar()),
        ):
            bar_a.valueChanged.connect(bar_b.setValue)
            bar_b.valueChanged.connect(bar_a.setValue)

    # ------------------------------------------------------------------
    # Trạng thái bật/tắt control
    # ------------------------------------------------------------------
    def _update_controls_state(self) -> None:
        has_file = self._current_file_path is not None
        busy = self._is_busy
        level_index = self.level_segmented.current_index()

        self.drop_zone.setEnabled(not busy)
        self.level_segmented.setEnabled(not busy)
        # Chuyển xám không áp dụng cho mức Nhẹ
        self.gray_checkbox.setEnabled(not busy and level_index != 0)
        self.gray_note.setEnabled(level_index != 0)
        self.trial_button.setEnabled(has_file and not busy)
        # Nút Lưu File luôn bấm được (chưa chọn file thì báo cảnh báo), chỉ khóa khi đang nén
        self.save_button.setEnabled(not busy)
        self.clear_button.setEnabled(not busy)

    def _on_level_changed(self, index: int) -> None:
        self.level_hint.setText(_LEVEL_HINTS[index])
        self._update_controls_state()
        if self._compare_active:
            self._refresh_compare()

    def _on_gray_toggled(self, _checked: bool) -> None:
        if self._compare_active:
            self._refresh_compare()

    def _current_job_options(self) -> tuple:
        """(level_index, to_grayscale) hiện tại. Mức Nhẹ luôn không chuyển xám."""
        level_index = self.level_segmented.current_index()
        gray = self.gray_checkbox.isChecked() and level_index != 0
        return level_index, gray

    # ------------------------------------------------------------------
    # Thông tin file
    # ------------------------------------------------------------------
    def _reset_file_info(self) -> None:
        self.info_name_value.setText("—")
        self.info_name_value.setToolTip("")
        self.info_pages_value.setText("—")
        self.info_size_value.setText("—")
        self.signature_warning.hide()

    def _fill_file_info(self, path: str, total_pages: int) -> None:
        _set_elided(self.info_name_value, os.path.basename(path), 230)
        self.info_pages_value.setText(str(total_pages))
        try:
            self.info_size_value.setText(_format_size(os.path.getsize(path)))
        except OSError:
            self.info_size_value.setText("—")
        self.signature_warning.setVisible(has_digital_signature(path))

    # ------------------------------------------------------------------
    # Chọn file / Clear
    # ------------------------------------------------------------------
    def _on_file_selected(self, path: str) -> None:
        # Báo ngay cho người dùng biết file đang được đọc — các bước bên dưới chạy đồng bộ
        # trên UI thread nên phải vẽ lại thông báo trước khi bị chặn.
        self._hide_result()
        self._show_loading("Đang đọc file, vui lòng chờ…")
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

        try:
            page_infos = list_page_infos(path)
        except PasswordProtectedError:
            self._show_error(f"File có mật khẩu, không thể mở: {os.path.basename(path)}")
            return
        except CorruptedFileError:
            self._show_error(f"Không thể đọc file, file có thể bị hỏng: {os.path.basename(path)}")
            return
        except Exception as exc:  # phòng hờ lỗi không lường trước, không để crash UI
            log_error(f"Lỗi không xác định khi mở file: {path}", exc)
            self._show_error(f"Không thể mở file: {os.path.basename(path)}")
            return

        # Dọn cache của file cũ trước khi gán đường dẫn mới
        if self._current_file_path:
            self._renderer.clear_cache(self._current_file_path)

        self._current_file_path = path
        self._current_page_infos = page_infos

        if self._compare_active:
            self._exit_compare_mode()

        name = os.path.basename(path)
        self._fill_file_info(path, len(page_infos))

        # Dựng lưới + render ảnh chạy đồng bộ: báo tiến độ qua _tick_loading trong các vòng render.
        # finally đảm bảo luôn tắt trạng thái "đang tải" kể cả khi có lỗi bất ngờ.
        try:
            self._show_loading(f"Đang dựng giao diện {len(page_infos)} trang…")
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
            self._load_preview(name, len(page_infos))
        finally:
            self._hide_result()

        # Trong lúc dựng, sự kiện đổi kích thước viewport bị bỏ qua — áp lại độ rộng nếu bị lệch
        self._apply_preview_zoom()
        self._update_controls_state()

    def _on_clear_clicked(self) -> None:
        if self._is_busy:
            return
        if self._current_file_path:
            self._renderer.clear_cache(self._current_file_path)

        self._current_file_path = None
        self._current_page_infos = []
        self._last_job = None

        if self._compare_active:
            self._exit_compare_mode()

        self.level_segmented.set_current_index(_DEFAULT_LEVEL_INDEX)
        self.level_hint.setText(_LEVEL_HINTS[_DEFAULT_LEVEL_INDEX])
        self.gray_checkbox.setChecked(False)

        self._zoom_level = _ZOOM_DEFAULT
        self._update_zoom_percent_label()

        self._reset_file_info()
        self._show_empty_preview()
        self._hide_result()
        self._update_controls_state()

    # ------------------------------------------------------------------
    # Lưu file (nén)
    # ------------------------------------------------------------------
    def _prompt_save_path(self, default_dir: str, default_name: str) -> Optional[str]:
        """Hộp thoại Save As (tắt cảnh báo ghi đè của Windows) + hộp thoại tự vẽ
        Ghi đè / Đổi tên khác / Hủy. Chặn ghi đè lên chính file gốc."""
        current_dir = default_dir
        current_name = default_name
        while True:
            suggested = os.path.join(current_dir, current_name)
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Lưu file kết quả", suggested, "PDF Files (*.pdf)",
                options=QFileDialog.Option.DontConfirmOverwrite,
            )
            if not save_path:
                return None

            # Không bao giờ ghi đè file gốc
            if self._current_file_path and (
                os.path.normcase(os.path.abspath(save_path))
                == os.path.normcase(os.path.abspath(self._current_file_path))
            ):
                self._show_error("Không được ghi đè lên chính file gốc, vui lòng chọn tên file khác")
                return None

            if os.path.exists(save_path):
                filename = os.path.basename(save_path)
                choice = _OverwriteConfirmDialog.ask(self, filename)
                if choice == _OverwriteConfirmDialog.RESULT_OVERWRITE:
                    return save_path
                elif choice == _OverwriteConfirmDialog.RESULT_RENAME:
                    current_dir = os.path.dirname(save_path)
                    current_name = filename
                    continue
                else:
                    return None

            return save_path

    def _open_result_folder(self, file_path: str) -> None:
        folder = os.path.dirname(file_path)
        if folder:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_save_clicked(self) -> None:
        if not self._current_file_path:
            self._hide_result()
            self._show_error("Vui lòng chọn file PDF trước khi thực hiện.")
            return

        base_name = os.path.splitext(os.path.basename(self._current_file_path))[0]
        default_dir = os.path.dirname(self._current_file_path)
        default_name = f"{base_name}{_DEFAULT_OUTPUT_SUFFIX}.pdf"

        save_path = self._prompt_save_path(default_dir, default_name)
        if not save_path:
            return

        level_index, gray = self._current_job_options()
        self._start_compress(save_path, level_index, gray)

    def _on_retry_clicked(self) -> None:
        if self._last_job is None or not self._current_file_path:
            return
        save_path, level_index, gray = self._last_job
        self._start_compress(save_path, level_index, gray)

    def _start_compress(self, save_path: str, level_index: int, gray: bool) -> None:
        if self._is_busy or not self._current_file_path:
            return
        self._last_job = (save_path, level_index, gray)

        self._hide_result()
        self._set_busy(True)
        self._show_loading("Đang nén…")

        level_key = _LEVELS[level_index][0]
        self._worker = _CompressWorker(
            self._current_file_path, save_path, level_key, gray, self
        )
        self._worker.succeeded.connect(self._on_compress_succeeded)
        self._worker.failed.connect(self._on_compress_failed)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _set_busy(self, busy: bool) -> None:
        self._is_busy = busy
        self.progress_bar.setVisible(busy)
        self._update_controls_state()

    def _on_worker_finished(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _on_compress_succeeded(self, result: dict) -> None:
        self._set_busy(False)
        save_path = self._last_job[0] if self._last_job else ""

        before = int(result.get("size_before", 0))
        after = int(result.get("size_after", 0))
        percent = float(result.get("percent", 0.0))
        status = result.get("status", "ok")

        diag = str(result.get("diag", ""))
        log_info(f"Chẩn đoán nén '{self._current_file_path}': {diag}")

        if status == "not_smaller":
            # Không giảm được: không lưu file, không phải lỗi
            self._show_size_card(before, after, percent, ok=False)
            self._show_info(
                "Không giảm được: kết quả không nhỏ hơn bản gốc nên không lưu file. "
                "Ảnh trong file đã được nén tốt hơn mức đã chọn, hoặc phần lớn dung lượng "
                "không nằm ở ảnh — đây không phải lỗi. "
                f"Chẩn đoán: {diag}"
            )
            log_info(f"Nén PDF không giảm được: '{self._current_file_path}'")
            return

        self._show_size_card(before, after, percent, ok=True)
        log_info(
            f"Đã nén PDF '{self._current_file_path}' -> '{save_path}' "
            f"({_format_size(before)} -> {_format_size(after)}, giảm {percent:.0f}%)"
        )
        if percent < 5:
            self._show_info(
                "Đã nén xong nhưng giảm rất ít — file chủ yếu là chữ vector hoặc ảnh đã tối ưu "
                f"sẵn, đây là bình thường. Kết quả: {save_path}"
            )
        else:
            self._show_success(f"Đã nén xong! Kết quả: {save_path}")
        self._open_result_folder(save_path)

    def _on_compress_failed(self, kind: str, message: str) -> None:
        self._set_busy(False)
        self._show_error(message)
        # File đích bị khóa: cho phép thử lại ngay (02_ mục 8)
        self.retry_button.setVisible(kind == "locked" and self._last_job is not None)

    # ------------------------------------------------------------------
    # Xem thử (so sánh trước/sau ở 100%)
    # ------------------------------------------------------------------
    def _on_trial_clicked(self) -> None:
        if not self._current_file_path or self._current_page < 1:
            self._show_error("Vui lòng chọn file PDF trước khi xem thử.")
            return
        self._hide_result()
        self._enter_compare_mode()

    def _enter_compare_mode(self) -> None:
        self._compare_active = True
        self.right_stack.setCurrentIndex(1)
        self.exit_compare_btn.show()
        self.zoom_in_btn.setEnabled(False)
        self.zoom_out_btn.setEnabled(False)
        self._refresh_compare()

    def _exit_compare_mode(self) -> None:
        self._compare_active = False
        self.right_stack.setCurrentIndex(0)
        self.exit_compare_btn.hide()
        self.compare_before.clear()
        self.compare_after.clear()
        if self._current_file_path:
            self.preview_title.setText(f"Xem trước: {os.path.basename(self._current_file_path)}")
        self._update_zoom_buttons_state()

    def _refresh_compare(self) -> None:
        """Dựng lại ảnh trước/sau cho trang đang chọn theo mức nén hiện tại."""
        if not self._current_file_path or self._current_page < 1:
            return
        self.setCursor(Qt.WaitCursor)
        try:
            before, after = self._build_trial_pixmaps(self._current_page - 1)
        except CompressError as exc:
            log_error(f"Xem thử trang {self._current_page} thất bại", exc)
            self._exit_compare_mode()
            self._show_error(str(exc))
            return
        except Exception as exc:
            log_error(f"Lỗi xem thử trang {self._current_page}", exc)
            self._exit_compare_mode()
            self._show_error("Không thể tạo ảnh xem thử cho trang này.")
            return
        finally:
            self.unsetCursor()

        level_index, gray = self._current_job_options()
        self.compare_before.set_pixmap(before)
        self.compare_after.set_pixmap(after)
        self.preview_title.setText(f"So sánh trang {self._current_page}")
        gray_text = "bật" if gray else "tắt"
        extra = " Mức Nhẹ không đụng vào ảnh nên hai bên giống nhau." if level_index == 0 else ""
        self.compare_info_label.setText(
            f"Mức: {_LEVELS[level_index][1]} · Chuyển xám: {gray_text} · Xem ở 100%. "
            f"Ảnh bên phải là bản nén thử riêng trang này (không ghi file).{extra}"
        )

    def _build_trial_pixmaps(self, page_index: int) -> tuple:
        """Trả về (ảnh gốc, ảnh sau nén thử) của 1 trang ở độ phóng 100%.

        Ảnh 'sau' do compress_engine nén riêng 1 trang trong bộ nhớ theo mức đang chọn."""
        info = self._current_page_infos[page_index]
        width_points = info.width or _PREVIEW_PAGE_WIDTH_FALLBACK
        # 100% = 1 point PDF ứng với 96 DPI màn hình (1 point = 1/72 inch)
        width_px = max(200, round(width_points * 96 / 72))

        data = self._renderer.render_page_detail(self._current_file_path, page_index, target_width=width_px)
        before = QPixmap()
        before.loadFromData(data)

        level_index, gray = self._current_job_options()
        after_data = render_compressed_page(
            self._current_file_path, page_index, _LEVELS[level_index][0], gray, width_px
        )
        after = QPixmap()
        after.loadFromData(after_data)
        return before, after

    # ------------------------------------------------------------------
    # Xử lý Preview (Cột B)
    # ------------------------------------------------------------------
    def _page_aspect_ratio(self, page_index: int) -> float:
        if 0 <= page_index < len(self._current_page_infos):
            info = self._current_page_infos[page_index]
            if info.width:
                return info.height / info.width
        return _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK

    def _render_page_into_frame(self, frame: "_PreviewPage", page_index: int, width: int) -> None:
        if not self._current_file_path:
            return
        try:
            data = self._renderer.render_page_detail(self._current_file_path, page_index, target_width=width)
            pixmap = QPixmap()
            pixmap.loadFromData(data)
            frame.set_page_pixmap(pixmap)
        except Exception as exc:
            log_error(f"Lỗi render preview trang {page_index + 1}", exc)

    def _load_preview(self, name: str, pages: int) -> None:
        self._current_total_pages = pages
        self._current_page = 1 if pages > 0 else 0
        self.preview_title.setText(f"Xem trước: {name}")
        self._build_preview_thumbs(pages)
        self._build_preview_pages(pages)
        self._refresh_page_view()

    def _show_empty_preview(self) -> None:
        self._current_total_pages = 0
        self._current_page = 0
        self.preview_title.setText("Xem trước: —")
        self._build_preview_thumbs(0)
        self._build_preview_pages(0)
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

            wrapper.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
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

            if self._current_file_path:
                try:
                    data = self._renderer.render_thumbnail(
                        self._current_file_path, i, max_width=_THUMB_W - 8
                    )
                    pixmap = QPixmap()
                    pixmap.loadFromData(data)
                    thumb.set_thumbnail(pixmap)
                except Exception as exc:
                    log_error(f"Lỗi render thumbnail trang {page_number}", exc)
            self._tick_loading("Đang tạo ảnh thu nhỏ", page_number, total_pages)

        self.thumb_layout.addStretch()

    def _build_preview_pages(self, total_pages: int) -> None:
        for frame in self._preview_pages.values():
            self.preview_layout.removeWidget(frame)
            frame.deleteLater()
        self._preview_pages.clear()
        self._current_preview_width = None

        if total_pages == 0:
            self._update_zoom_buttons_state()
            return

        width = self._compute_preview_width()
        self._current_preview_width = width
        for i in range(total_pages):
            page_number = i + 1
            aspect_ratio = self._page_aspect_ratio(i)
            frame = _PreviewPage(page_number, aspect_ratio=aspect_ratio)
            height = round(width * frame.aspect_ratio)
            frame.setFixedSize(width, height)
            self._render_page_into_frame(frame, i, width)
            self.preview_layout.addWidget(frame, alignment=Qt.AlignHCenter)
            self._preview_pages[page_number] = frame
            self._tick_loading("Đang tạo ảnh xem trước", page_number, total_pages)

        self._update_zoom_buttons_state()

    def _on_thumb_clicked(self, page_number: int) -> None:
        self._current_page = page_number
        self._refresh_page_view()
        # Đang so sánh Xem thử: chuyển sang so sánh trang vừa chọn
        if self._compare_active:
            self._refresh_compare()

    def _refresh_page_view(self) -> None:
        for thumb in self._preview_thumbs:
            thumb.set_current(thumb.page_number == self._current_page)
        if 0 <= self._current_page - 1 < len(self._preview_thumbs):
            current_thumb = self._preview_thumbs[self._current_page - 1]
            self.thumb_scroll.ensureWidgetVisible(current_thumb, 0, 20)

        current_frame = self._preview_pages.get(self._current_page)
        if current_frame is not None:
            self.preview_scroll_b.ensureWidgetVisible(current_frame, 0, 0)

    # ------------------------------------------------------------------
    # Dynamic Zooming (Cột B)
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

        for page_number, frame in self._preview_pages.items():
            new_height = round(new_width * frame.aspect_ratio)
            frame.setFixedSize(new_width, new_height)
            self._render_page_into_frame(frame, page_number - 1, new_width)

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
        # Đang so sánh Xem thử (100% cố định): khóa zoom
        has_pages = bool(self._preview_pages) and not self._compare_active
        self.zoom_in_btn.setEnabled(has_pages and self._zoom_level < _ZOOM_MAX - 1e-6)
        self.zoom_out_btn.setEnabled(has_pages and self._zoom_level > _ZOOM_MIN + 1e-6)

    def _update_zoom_percent_label(self) -> None:
        self.zoom_percent_label.setText(f"{round(self._zoom_level * 100)}%")

    def _on_preview_viewport_resized(self) -> None:
        # Đang dựng file mới: bỏ qua, _on_file_selected sẽ áp lại độ rộng khi dựng xong
        if self._is_loading:
            return
        if self._preview_pages:
            self._apply_preview_zoom()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_width_applied and self._preview_pages:
            self._initial_width_applied = True
            self._current_preview_width = None
            self._apply_preview_zoom()

    # ------------------------------------------------------------------
    # Thông báo Trạng thái
    # ------------------------------------------------------------------
    def _show_size_card(self, before: int, after: int, percent: float, ok: bool) -> None:
        """Khu kết quả: dung lượng trước -> sau và % giảm."""
        self.result_size_label.setText(f"{_format_size(before)}  →  {_format_size(after)}")
        if ok:
            self.result_percent_label.setStyleSheet(
                f"color: {COLOR_SUCCESS}; font-size: 13px; font-weight: 700; background: transparent; border: none;"
            )
            self.result_percent_label.setText(f"Giảm {percent:.0f}%")
        else:
            self.result_percent_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; font-weight: 700; background: transparent; border: none;"
            )
            self.result_percent_label.setText("Không giảm được")
        self.result_card.show()

    def _show_loading(self, message: str) -> None:
        # Thông báo trạng thái đang tải/đang nén (màu chữ phụ, không dùng popup)
        self._is_loading = True
        self.result_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"⏳ {message}")
        self.result_label.show()

    def _tick_loading(self, stage: str, done: int, total: int) -> None:
        # Cập nhật tiến độ x/N rồi cho Qt vẽ lại; không làm gì nếu không đang tải file mới
        # (VD: đổi zoom cũng gọi các hàm render nhưng không cần thông báo).
        if not self._is_loading:
            return
        self._show_loading(f"{stage}… {done}/{total}")
        QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)

    def _show_success(self, message: str) -> None:
        self._is_loading = False
        self.result_label.setStyleSheet(f"color: {COLOR_SUCCESS}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"✓ {message}")
        self.result_label.show()

    def _show_info(self, message: str) -> None:
        self._is_loading = False
        self.result_label.setStyleSheet(f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"ℹ {message}")
        self.result_label.show()

    def _show_error(self, message: str) -> None:
        self._is_loading = False
        self.result_label.setStyleSheet(f"color: {COLOR_ERROR}; font-size: 12px; font-weight: 500;")
        self.result_label.setText(f"✕ {message}")
        self.result_label.show()

    def _hide_result(self) -> None:
        self._is_loading = False
        self.result_label.hide()
        self.result_card.hide()
        self.retry_button.hide()