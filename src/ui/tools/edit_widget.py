"""
/src/ui/tools/edit_widget.py
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QPixmap, QDesktopServices
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
    QDialog,
    QGraphicsOpacityEffect,
)

from src import pdf_core
from src.undo_manager import UndoManager
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

_GRID_COLUMNS = 3
_THUMB_SIZE = 128
_THUMB_IMAGE_MAX = _THUMB_SIZE - 34  

# Zoom Cột B: mỗi lần bấm Zoom In/Out ±15%, giới hạn 50%-200%.
_ZOOM_MIN = 0.5
_ZOOM_MAX = 2.0
_ZOOM_STEP = 0.15
_ZOOM_DEFAULT = 1.0

_PREVIEW_SIDE_MARGIN = 12
_PREVIEW_MIN_PAGE_WIDTH = 220

_CHECKBOX_SIZE = 22
_CHECKBOX_RADIUS = round(CORNER_RADIUS * _CHECKBOX_SIZE / CONTROL_HEIGHT)

_DROPZONE_ICON_BOX = 56

_WARNING_COLOR = "#F59E0B"


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
    QMenu::item:disabled {{
        color: {COLOR_TEXT_SECONDARY};
    }}
"""


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


def _action_button_style() -> str:
    """Style dùng chung cho Undo/Redo/Clear/"Đổi tên khác"/"Hủy" (nút phụ, nền trắng viền xám)."""
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
        QPushButton:disabled {{ color: {COLOR_TEXT_SECONDARY}; border-color: {COLOR_BORDER}; }}
        """


def _primary_button_style() -> str:
    """Style nút hành động chính màu Accent — dùng cho "Lưu File" và nút "Ghi đè"."""
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
        QPushButton:hover {{ background-color: #E28104; }}
        QPushButton:pressed {{ background-color: #C87203; }}
        """


# ----------------------------------------------------------------------
# Hộp thoại trùng tên khi Lưu File 
# ----------------------------------------------------------------------
class _OverwriteConfirmDialog(QDialog):
    ACTION_OVERWRITE = "overwrite"
    ACTION_RENAME = "rename"
    ACTION_CANCEL = "cancel"

    def __init__(self, filename: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trùng tên file")
        self.setModal(True)
        self.setFixedWidth(420)
        self.result_action: str = self.ACTION_CANCEL
        self.setStyleSheet("QDialog { background-color: white; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(22)

        message_row = QHBoxLayout()
        message_row.setSpacing(14)

        icon_label = QLabel()
        icon_label.setPixmap(qta.icon("mdi6.alert", color=_WARNING_COLOR).pixmap(30, 30))
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
        message_row.addWidget(text_label, stretch=1)
        root.addLayout(message_row)

        button_row = QHBoxLayout()
        button_row.setSpacing(10)

        overwrite_btn = QPushButton("Ghi đè")
        overwrite_btn.setCursor(Qt.PointingHandCursor)
        overwrite_btn.setFixedHeight(CONTROL_HEIGHT)
        overwrite_btn.setStyleSheet(_primary_button_style())
        overwrite_btn.clicked.connect(self._on_overwrite)
        button_row.addWidget(overwrite_btn, stretch=1)

        rename_btn = QPushButton("Đổi tên khác")
        rename_btn.setCursor(Qt.PointingHandCursor)
        rename_btn.setFixedHeight(CONTROL_HEIGHT)
        rename_btn.setStyleSheet(_action_button_style())
        rename_btn.clicked.connect(self._on_rename)
        button_row.addWidget(rename_btn, stretch=1)

        cancel_btn = QPushButton("Hủy")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(CONTROL_HEIGHT)
        cancel_btn.setStyleSheet(_action_button_style())
        cancel_btn.clicked.connect(self._on_cancel)
        button_row.addWidget(cancel_btn, stretch=1)

        root.addLayout(button_row)

    def _on_overwrite(self) -> None:
        self.result_action = self.ACTION_OVERWRITE
        self.accept()

    def _on_rename(self) -> None:
        self.result_action = self.ACTION_RENAME
        self.accept()

    def _on_cancel(self) -> None:
        self.result_action = self.ACTION_CANCEL
        self.reject()

    @classmethod
    def ask(cls, parent: QWidget, filename: str) -> str:
        dialog = cls(filename, parent)
        dialog.exec()
        return dialog.result_action


# ----------------------------------------------------------------------
# A3 — 1 ô trong lưới thumbnail
# ----------------------------------------------------------------------
class _EditPageThumbnail(QWidget):
    clicked = Signal(object)
    rotate_requested = Signal(object, str)
    move_requested = Signal(object)
    move_confirm_requested = Signal(object)
    move_cancel_requested = Signal()
    mark_toggled = Signal(object)

    def __init__(self, original_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.original_id = original_id
        self.page_number = original_id + 1
        self.is_selected = False
        self.is_flagged = False
        self.delete_mode = False
        self.is_cut = False
        self.is_move_target = False
        self._move_active = False
        self.setCursor(Qt.PointingHandCursor)

        row_layout = QHBoxLayout(self)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(4)

        self.card = QFrame()
        self.card.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._opacity_effect = QGraphicsOpacityEffect(self.card)
        self._opacity_effect.setOpacity(1.0)
        self.card.setGraphicsEffect(self._opacity_effect)
        self._apply_card_style()

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 4)
        card_layout.setSpacing(0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background: transparent; border: none;")
        card_layout.addWidget(self.image_label, stretch=1)

        self.move_target_label = QLabel("▼ Chèn vào đây")
        self.move_target_label.setAlignment(Qt.AlignCenter)
        self.move_target_label.setStyleSheet(
            f"color: {COLOR_ERROR}; font-size: 10px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        self.move_target_label.hide()
        card_layout.addWidget(self.move_target_label)

        self.rotation_badge = QLabel("")
        self.rotation_badge.setAlignment(Qt.AlignCenter)
        self.rotation_badge.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-size: 11px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(self.rotation_badge)

        row_layout.addWidget(self.card)

        # Badge vị trí hiện tại — CHỈ hiển thị số (đã bỏ ký tự "#" theo yêu cầu).
        self.position_badge = QLabel(str(self.page_number), self.card)
        self.position_badge.setAlignment(Qt.AlignCenter)
        self.position_badge.setStyleSheet(
            "background-color: rgba(15, 23, 42, 0.78); color: white; "
            "font-size: 11px; font-weight: 700; border-radius: 8px; padding: 2px 6px;"
        )
        self.position_badge.adjustSize()
        self.position_badge.move(6, 6)
        self.position_badge.raise_()

    def _apply_card_style(self) -> None:
        if self.is_cut:
            border = f"2px dashed {COLOR_BORDER_STRONG}"
            background = "#F3F4F6"
        elif self.is_move_target:
            border = f"2.5px solid {COLOR_ERROR}"
            background = "#FDECEC"
        elif self.is_flagged:
            border = f"2px solid {COLOR_ERROR}"
            background = "#FDECEC"
        elif self.is_selected:
            border = f"2px solid {COLOR_ACCENT}"
            background = COLOR_ACCENT_LIGHT
        else:
            border = f"1px solid {COLOR_BORDER}"
            background = "white"
        self.card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {background};
                border: {border};
                border-radius: {CORNER_RADIUS}px;
            }}
            QFrame:hover {{
                border: 2px solid {COLOR_ACCENT};
                background-color: {COLOR_ACCENT_LIGHT};
            }}
            """
        )
        self._opacity_effect.setOpacity(0.4 if self.is_cut else 1.0)

    def set_selected(self, selected: bool) -> None:
        self.is_selected = selected
        self._apply_card_style()

    def set_flagged(self, flagged: bool) -> None:
        self.is_flagged = flagged
        self._apply_card_style()

    def set_delete_mode(self, enabled: bool) -> None:
        self.delete_mode = enabled

    def set_cut(self, is_cut: bool) -> None:
        self.is_cut = is_cut
        self._apply_card_style()

    def set_move_target(self, is_target: bool) -> None:
        self.is_move_target = is_target
        self.move_target_label.setVisible(is_target)
        self._apply_card_style()

    def set_move_mode_active(self, active: bool) -> None:
        self._move_active = active

    def set_page_number(self, number: int) -> None:
        self.page_number = number
        self.position_badge.setText(str(number))
        self.position_badge.adjustSize()
        self.position_badge.raise_()

    def set_image(self, png_bytes: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(png_bytes)
        if pixmap.isNull():
            return
        scaled = pixmap.scaled(
            _THUMB_IMAGE_MAX, _THUMB_IMAGE_MAX, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
        self.image_label.setPixmap(scaled)

    def set_rotation_badge(self, degrees: int) -> None:
        self.rotation_badge.setText(f"{degrees}°" if degrees else "")

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self)

    def contextMenuEvent(self, event) -> None:
        if self.delete_mode:
            self.set_flagged(not self.is_flagged)
            self.mark_toggled.emit(self)
            event.accept()
            return

        if self.is_flagged:
            event.ignore()
            return

        menu = QMenu(self)
        menu.setStyleSheet(_CONTEXT_MENU_QSS)

        if self._move_active:
            if self.is_cut:
                cancel_action = menu.addAction(
                    qta.icon("mdi6.close-thick", color=COLOR_ERROR), "Hủy Move"
                )
                chosen = menu.exec(event.globalPos())
                if chosen == cancel_action:
                    self.move_cancel_requested.emit()
                return

            confirm_action = menu.addAction(
                qta.icon("mdi6.check-bold", color=COLOR_ACCENT), "Move đến đây"
            )
            confirm_action.setEnabled(self.is_move_target)
            cancel_action = menu.addAction(
                qta.icon("mdi6.close-thick", color=COLOR_ERROR), "Hủy Move"
            )
            chosen = menu.exec(event.globalPos())
            if chosen == confirm_action:
                self.move_confirm_requested.emit(self)
            elif chosen == cancel_action:
                self.move_cancel_requested.emit()
            return

        rotate_left_action = menu.addAction(
            qta.icon("mdi6.rotate-left", color=COLOR_TEXT_PRIMARY), "Xoay trái 90°"
        )
        rotate_right_action = menu.addAction(
            qta.icon("mdi6.rotate-right", color=COLOR_TEXT_PRIMARY), "Xoay phải 90°"
        )
        menu.addSeparator()
        move_action = menu.addAction(
            qta.icon("mdi6.cursor-move", color=COLOR_ACCENT), "Move"
        )
        chosen = menu.exec(event.globalPos())
        if chosen == rotate_left_action:
            self.rotate_requested.emit(self, "left")
        elif chosen == rotate_right_action:
            self.rotate_requested.emit(self, "right")
        elif chosen == move_action:
            self.move_requested.emit(self)


class _MoveHeadMarker(QFrame):
    clicked = Signal()
    confirm_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.is_target = False
        self._move_active = False
        self.setFixedHeight(8)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_style()

    def _apply_style(self) -> None:
        color = COLOR_ERROR if self.is_target else COLOR_BORDER_STRONG
        self.setStyleSheet(f"QFrame {{ background-color: {color}; border-radius: 4px; }}")

    def set_target(self, is_target: bool) -> None:
        self.is_target = is_target
        self._apply_style()

    def set_move_mode_active(self, active: bool) -> None:
        self._move_active = active

    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if self._move_active and event.button() == Qt.LeftButton:
            self.clicked.emit()

    def contextMenuEvent(self, event) -> None:
        if not self._move_active:
            event.ignore()
            return
        menu = QMenu(self)
        menu.setStyleSheet(_CONTEXT_MENU_QSS)
        confirm_action = menu.addAction(
            qta.icon("mdi6.check-bold", color=COLOR_ACCENT), "Move đến đây"
        )
        confirm_action.setEnabled(self.is_target)
        cancel_action = menu.addAction(
            qta.icon("mdi6.close-thick", color=COLOR_ERROR), "Hủy Move"
        )
        chosen = menu.exec(event.globalPos())
        if chosen == confirm_action:
            self.confirm_requested.emit()
        elif chosen == cancel_action:
            self.cancel_requested.emit()


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


class EditFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFocusPolicy(Qt.StrongFocus)

        self._selected_file_path: Optional[str] = None
        self._session: Optional[pdf_core.PageEditSession] = None
        self._renderer = pdf_core.PageRenderer()
        self._undo = UndoManager()

        self._thumbnails: List[_EditPageThumbnail] = []
        self._preview_frames: List[QFrame] = []
        self._thumb_by_id: Dict[int, _EditPageThumbnail] = {}
        self._frame_by_id: Dict[int, QFrame] = {}

        self._move_source_thumb: Optional[_EditPageThumbnail] = None
        self._move_target_after: Optional[int] = None
        self._move_target_thumb: Optional[_EditPageThumbnail] = None
        self._move_target_is_head: bool = False

        self._zoom_level: float = _ZOOM_DEFAULT
        self._current_preview_width: Optional[int] = None
        self._initial_width_applied = False

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(28, 24, 28, 24)
        root_layout.setSpacing(20)

        # ================= CỘT A (~55%) =================
        column_a = QVBoxLayout()
        column_a.setSpacing(14)

        self.drop_zone = _DropZone()
        self.drop_zone.file_selected.connect(self._on_file_selected)
        column_a.addWidget(self.drop_zone)

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

        a3_header = QWidget()
        a3_header_layout = QHBoxLayout(a3_header)
        a3_header_layout.setContentsMargins(16, 12, 16, 12)
        a3_header_layout.setSpacing(8)

        a3_icon = QLabel()
        a3_icon.setPixmap(qta.icon("mdi6.file-document-edit-outline", color="black").pixmap(QSize(18, 18)))
        a3_icon.setStyleSheet("background: transparent; border: none;")
        a3_header_layout.addWidget(a3_icon)

        self.a3_title_label = QLabel('File được chọn: ""')
        self.a3_title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        a3_header_layout.addWidget(self.a3_title_label, stretch=1)
        a3_box_layout.addWidget(a3_header)

        head_marker_wrap = QWidget()
        head_marker_wrap.setStyleSheet("background: transparent;")
        head_marker_layout = QHBoxLayout(head_marker_wrap)
        head_marker_layout.setContentsMargins(28, 6, 28, 0)
        self.head_marker = _MoveHeadMarker()
        self.head_marker.setToolTip(
            "Vị trí đầu file — trong lúc đang Move, bấm vào đây để chọn đích là đầu file"
        )
        self.head_marker.clicked.connect(self._on_head_marker_clicked)
        self.head_marker.confirm_requested.connect(self._on_head_marker_confirm)
        self.head_marker.cancel_requested.connect(self._on_move_cancel_requested)
        head_marker_layout.addWidget(self.head_marker)
        a3_box_layout.addWidget(head_marker_wrap)

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

        self.thumb_grid.setAlignment(Qt.AlignTop)

# --- BỔ SUNG CẤU HÌNH CỐ ĐỊNH 3 CỘT ---
        for c in range(_GRID_COLUMNS):
            self.thumb_grid.setColumnStretch(c, 1)
        # ----------------------------------------
        #         
        self.preview_scroll.setWidget(grid_container)
        a3_box_layout.addWidget(self.preview_scroll, stretch=1)

        column_a.addWidget(a3_container, stretch=1)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(0)
        bottom_row.setContentsMargins(0, 0, 0, 0)

        delete_group = QWidget()
        delete_group.setFixedHeight(CONTROL_HEIGHT)
        delete_group.setStyleSheet(
            f"""
            QWidget {{
                background-color: white;
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
            }}
            """
        )
        delete_group_layout = QHBoxLayout(delete_group)
        delete_group_layout.setContentsMargins(12, 0, 12, 0)
        delete_group_layout.setSpacing(6)
        delete_group_layout.setAlignment(Qt.AlignCenter)

        delete_icon = QLabel()
        delete_icon.setPixmap(
            qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY).pixmap(16, 16)
        )
        delete_icon.setStyleSheet("background: transparent; border: none;")
        delete_group_layout.addWidget(delete_icon)

        delete_label = QLabel("Xóa")
        delete_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        delete_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        delete_group_layout.addWidget(delete_label)
        delete_group_layout.addSpacing(16)

        self.delete_checkbox = _CheckToggle()
        delete_group_layout.addWidget(self.delete_checkbox)
        self.delete_checkbox.toggled.connect(self._on_delete_mode_toggled)
        bottom_row.addWidget(delete_group, stretch=1)

        undo_group = QWidget()
        undo_group_layout = QHBoxLayout(undo_group)
        undo_group_layout.setContentsMargins(0, 0, 0, 0)
        undo_group_layout.setSpacing(8)
        undo_group_layout.setAlignment(Qt.AlignCenter)

        self.undo_button = QPushButton(" Undo")
        self.undo_button.setIcon(qta.icon("mdi6.undo-variant", color=COLOR_TEXT_PRIMARY))
        self.undo_button.setCursor(Qt.PointingHandCursor)
        self.undo_button.setFixedHeight(CONTROL_HEIGHT)
        self.undo_button.setMinimumWidth(96)
        self.undo_button.setStyleSheet(_action_button_style())
        self.undo_button.clicked.connect(self._on_undo_clicked)
        undo_group_layout.addWidget(self.undo_button)

        self.redo_button = QPushButton(" Redo")
        self.redo_button.setIcon(qta.icon("mdi6.redo-variant", color=COLOR_TEXT_PRIMARY))
        self.redo_button.setCursor(Qt.PointingHandCursor)
        self.redo_button.setFixedHeight(CONTROL_HEIGHT)
        self.redo_button.setMinimumWidth(96)
        self.redo_button.setStyleSheet(_action_button_style())
        self.redo_button.clicked.connect(self._on_redo_clicked)
        undo_group_layout.addWidget(self.redo_button)

        bottom_row.addWidget(undo_group, stretch=2)

        clear_group = QWidget()
        clear_group_layout = QHBoxLayout(clear_group)
        clear_group_layout.setContentsMargins(0, 0, 0, 0)
        clear_group_layout.setAlignment(Qt.AlignCenter)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setIcon(qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY))
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setFixedHeight(CONTROL_HEIGHT)
        self.clear_button.setMinimumWidth(85)
        self.clear_button.setStyleSheet(_action_button_style())
        self.clear_button.clicked.connect(self._on_clear_clicked)
        clear_group_layout.addWidget(self.clear_button)
        bottom_row.addWidget(clear_group, stretch=1)

        save_group = QWidget()
        save_group_layout = QHBoxLayout(save_group)
        save_group_layout.setContentsMargins(0, 0, 0, 0)
        save_group_layout.setAlignment(Qt.AlignCenter)

        self.save_button = QPushButton(" Lưu File")
        self.save_button.setIcon(qta.icon("mdi6.content-save-outline", color="white"))
        self.save_button.setCursor(Qt.PointingHandCursor)
        self.save_button.setFixedHeight(CONTROL_HEIGHT)
        self.save_button.setMinimumWidth(120)
        self.save_button.setStyleSheet(_primary_button_style())
        self.save_button.clicked.connect(self._on_save_clicked)
        save_group_layout.addWidget(self.save_button)
        bottom_row.addWidget(save_group, stretch=1)

        column_a.addLayout(bottom_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        column_a.addWidget(self.result_label)

        # ================= CỘT B (~45%) =================
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

        self.preview_title_label = QLabel('Xem trước: ""')
        self.preview_title_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 14px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        b_header_layout.addWidget(self.preview_title_label, stretch=1)

        self.zoom_out_btn = QToolButton()
        self.zoom_out_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_out_btn.setIcon(qta.icon("mdi6.magnify-minus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_out_btn.setIconSize(QSize(16, 16))
        self.zoom_out_btn.setFixedSize(26, 26)
        self.zoom_out_btn.setStyleSheet(_zoom_button_style())
        self.zoom_out_btn.setToolTip("Thu nhỏ (-15%)")
        self.zoom_out_btn.clicked.connect(self._on_zoom_out_clicked)
        b_header_layout.addWidget(self.zoom_out_btn)

        self.zoom_percent_label = QLabel(f"{round(_ZOOM_DEFAULT * 100)}%")
        self.zoom_percent_label.setAlignment(Qt.AlignCenter)
        self.zoom_percent_label.setFixedWidth(42)
        self.zoom_percent_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        b_header_layout.addWidget(self.zoom_percent_label)

        self.zoom_in_btn = QToolButton()
        self.zoom_in_btn.setCursor(Qt.PointingHandCursor)
        self.zoom_in_btn.setIcon(qta.icon("mdi6.magnify-plus-outline", color=COLOR_TEXT_PRIMARY))
        self.zoom_in_btn.setIconSize(QSize(16, 16))
        self.zoom_in_btn.setFixedSize(26, 26)
        self.zoom_in_btn.setStyleSheet(_zoom_button_style())
        self.zoom_in_btn.setToolTip("Phóng to (+15%)")
        self.zoom_in_btn.clicked.connect(self._on_zoom_in_clicked)
        b_header_layout.addWidget(self.zoom_in_btn)

        preview_box_layout.addWidget(b_header)

        self.preview_scroll_b = _PannablePreviewScrollArea()
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
        self.preview_scroll_b.viewport_resized.connect(self._on_preview_viewport_resized)

        preview_container = QWidget()
        preview_container.setStyleSheet("background: transparent;")
        preview_layout = QVBoxLayout(preview_container)
        preview_layout.setContentsMargins(_PREVIEW_SIDE_MARGIN, 12, _PREVIEW_SIDE_MARGIN, 12)
        preview_layout.setSpacing(16)
        preview_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.preview_scroll_b.setWidget(preview_container)

        preview_box_layout.addWidget(self.preview_scroll_b, stretch=1)
        column_b.addWidget(preview_box_container, stretch=1)

        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, stretch=55)
        root_layout.addWidget(column_b_widget, stretch=45)

        self._update_zoom_buttons_state()
        self._update_zoom_percent_label()
        self._update_undo_redo_buttons()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._initial_width_applied and self._preview_frames:
            self._initial_width_applied = True
            self._current_preview_width = None
            self._apply_preview_zoom()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete and self.delete_checkbox.isChecked():
            self._on_delete_key_pressed_from_ui()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------
    def _build_grid_from_session(self) -> None:
        order = self._session.page_order
        for idx, source_index in enumerate(order):
            row, col = divmod(idx, _GRID_COLUMNS)
            thumb = _EditPageThumbnail(source_index)
            thumb.set_page_number(idx + 1)
            thumb.clicked.connect(self._on_thumbnail_clicked)
            thumb.rotate_requested.connect(self._on_rotate_requested)
            thumb.move_requested.connect(self._on_move_requested)
            thumb.move_confirm_requested.connect(self._on_move_confirm_requested)
            thumb.move_cancel_requested.connect(self._on_move_cancel_requested)
            thumb.mark_toggled.connect(self._on_mark_toggled)
            self.thumb_grid.addWidget(thumb, row, col, alignment=Qt.AlignCenter)
            self._thumbnails.append(thumb)
            self._thumb_by_id[source_index] = thumb
        self._refresh_all_thumb_images()

    def _create_preview_frame(self, source_index: int) -> QFrame:
        frame = QFrame()
        frame.original_id = source_index
        frame.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignCenter)

        image_label = QLabel()
        image_label.setAlignment(Qt.AlignCenter)
        image_label.setStyleSheet("background: transparent; border: none;")
        layout.addWidget(image_label)
        frame.image_label = image_label

        position_label = QLabel("")
        position_label.setAlignment(Qt.AlignCenter)
        position_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; font-weight: 600; "
            "background: transparent; border: none;"
        )
        layout.addWidget(position_label)
        frame._position_label = position_label
        return frame

    def _build_preview_from_session(self, layout: QVBoxLayout) -> None:
        self._current_preview_width = self._compute_preview_width()
        order = self._session.page_order
        for source_index in order:
            frame = self._create_preview_frame(source_index)
            layout.addWidget(frame, alignment=Qt.AlignHCenter)
            self._preview_frames.append(frame)
            self._frame_by_id[source_index] = frame
        self._refresh_all_frame_images()
        for idx, frame in enumerate(self._preview_frames):
            frame._position_label.setText(f"Vị trí #{idx + 1}")

    def _clear_grid_widgets(self) -> None:
        for thumb in self._thumb_by_id.values():
            self.thumb_grid.removeWidget(thumb)
            thumb.setParent(None)
            thumb.deleteLater()
        self._thumb_by_id = {}
        self._thumbnails = []

        preview_layout = self.preview_scroll_b.widget().layout()
        for frame in self._frame_by_id.values():
            preview_layout.removeWidget(frame)
            frame.setParent(None)
            frame.deleteLater()
        self._frame_by_id = {}
        self._preview_frames = []

    # ------------------------------------------------------------------
    def _refresh_thumb_image(self, thumb: _EditPageThumbnail) -> None:
        if self._session is None or not self._selected_file_path:
            return
        rotation = self._session.get_pending_rotation(thumb.original_id)
        data = self._renderer.render_thumbnail(
            self._selected_file_path, thumb.original_id, max_width=_THUMB_SIZE, pending_rotation=rotation
        )
        thumb.set_image(data)
        thumb.set_rotation_badge(rotation)

    def _refresh_all_thumb_images(self) -> None:
        for thumb in self._thumb_by_id.values():
            self._refresh_thumb_image(thumb)

    def _refresh_frame_image(self, frame: QFrame) -> None:
        if self._session is None or not self._selected_file_path:
            return
        rotation = self._session.get_pending_rotation(frame.original_id)
        width = self._current_preview_width or self._fit_base_width()
        data = self._renderer.render_page_detail(
            self._selected_file_path, frame.original_id, target_width=width, pending_rotation=rotation
        )
        pixmap = QPixmap()
        pixmap.loadFromData(data)
        frame.image_label.setPixmap(pixmap)

    def _refresh_all_frame_images(self) -> None:
        for frame in self._frame_by_id.values():
            self._refresh_frame_image(frame)

    # ------------------------------------------------------------------
    def _fit_base_width(self) -> int:
        viewport_width = self.preview_scroll_b.viewport().width()
        usable = viewport_width - (_PREVIEW_SIDE_MARGIN * 2)
        return max(_PREVIEW_MIN_PAGE_WIDTH, usable)

    def _compute_preview_width(self) -> int:
        base_width = self._fit_base_width()
        return max(_PREVIEW_MIN_PAGE_WIDTH, round(base_width * self._zoom_level))

    def _apply_preview_zoom(self) -> None:
        if not self._preview_frames:
            self._update_zoom_buttons_state()
            self._update_zoom_percent_label()
            return

        new_width = self._compute_preview_width()
        if new_width == self._current_preview_width:
            self._update_zoom_buttons_state()
            self._update_zoom_percent_label()
            return
        self._current_preview_width = new_width
        self._refresh_all_frame_images()

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
        has_pages = bool(self._preview_frames)
        self.zoom_in_btn.setEnabled(has_pages and self._zoom_level < _ZOOM_MAX - 1e-6)
        self.zoom_out_btn.setEnabled(has_pages and self._zoom_level > _ZOOM_MIN + 1e-6)

    def _update_zoom_percent_label(self) -> None:
        self.zoom_percent_label.setText(f"{round(self._zoom_level * 100)}%")

    def _on_preview_viewport_resized(self) -> None:
        if self._preview_frames:
            self._apply_preview_zoom()

    # ------------------------------------------------------------------
    def _update_undo_redo_buttons(self) -> None:
        has_session = self._session is not None
        no_move_running = self._move_source_thumb is None
        self.undo_button.setEnabled(has_session and no_move_running and self._undo.can_undo())
        self.redo_button.setEnabled(has_session and no_move_running and self._undo.can_redo())

    def _apply_snapshot_to_ui(self, snapshot: dict) -> None:
        if self._session is None:
            return
        self._session.restore(snapshot)

        order = snapshot["order"]
        self._thumbnails = [self._thumb_by_id[i] for i in order]
        self._preview_frames = [self._frame_by_id[i] for i in order]

        marked = snapshot["marked"]
        for source_index, thumb in self._thumb_by_id.items():
            thumb.set_flagged(source_index in marked)

        self._renumber_and_relayout()
        self._refresh_all_thumb_images()
        self._refresh_all_frame_images()
        self._select_page(1 if self._thumbnails else None)

    # ------------------------------------------------------------------
    def _on_file_selected(self, path: str) -> None:
        try:
            session = pdf_core.PageEditSession(path)
        except pdf_core.PasswordProtectedError:
            self._show_error("File có mật khẩu — bản đầu chưa hỗ trợ mở file có mật khẩu.")
            return
        except pdf_core.CorruptedFileError:
            self._show_error(f"Không thể đọc file, file có thể bị hỏng: {os.path.basename(path)}")
            return

        if not session.page_order:
            self._show_error("File PDF không có trang nào.")
            return

        self._selected_file_path = path
        self._renderer.clear_cache(path)
        self._session = session
        self._undo = UndoManager()

        self.delete_checkbox.setChecked(False)
        self.delete_checkbox.setEnabled(True)
        self._force_reset_move_state()
        self._clear_grid_widgets()

        self._build_grid_from_session()
        preview_layout = self.preview_scroll_b.widget().layout()
        self._build_preview_from_session(preview_layout)

        self.a3_title_label.setText(f'File được chọn: "{os.path.basename(path)}"')
        self.preview_title_label.setText(f'Xem trước: "{os.path.basename(path)}"')

        self._update_undo_redo_buttons()
        self._select_page(1)
        self._hide_result()
        self.setFocus()

    def _on_delete_mode_toggled(self, checked: bool) -> None:
        if self._move_source_thumb is not None:
            return
        for thumb in self._thumbnails:
            thumb.set_delete_mode(checked)
        if checked:
            self.setFocus()

    def _on_mark_toggled(self, thumb: _EditPageThumbnail) -> None:
        if self._session is None:
            return
        self._session.toggle_mark(thumb.original_id)

    def _on_thumbnail_clicked(self, thumb: _EditPageThumbnail) -> None:
        if self._move_source_thumb is not None:
            if thumb is self._move_source_thumb or thumb.is_flagged:
                return
            self._set_move_target(thumb)
            return
        self._select_page(thumb.page_number)

    def _on_rotate_requested(self, thumb: _EditPageThumbnail, direction: str) -> None:
        if self._session is None:
            return
        before = self._session.snapshot()
        self._session.rotate(thumb.original_id, direction)
        after = self._session.snapshot()
        self._undo.register("rotate", before, after)
        self._update_undo_redo_buttons()

        self._refresh_thumb_image(thumb)
        frame = self._frame_by_id.get(thumb.original_id)
        if frame is not None:
            self._refresh_frame_image(frame)

        huong = "trái" if direction == "left" else "phải"
        self._show_success(f"Đã xoay {huong} 90° trang #{thumb.page_number}.")

    # ------------------------------------------------------------------
    def _on_move_requested(self, thumb: _EditPageThumbnail) -> None:
        if self._move_source_thumb is not None or thumb.is_flagged:
            return
        self._move_source_thumb = thumb
        self._move_target_after = None
        self._move_target_thumb = None
        self._move_target_is_head = False
        thumb.set_cut(True)
        self.delete_checkbox.setEnabled(False)
        self.undo_button.setEnabled(False)
        self.redo_button.setEnabled(False)
        for t in self._thumbnails:
            t.set_move_mode_active(True)
        self.head_marker.set_move_mode_active(True)
        self._show_success(
            f"Đang di chuyển trang #{thumb.page_number} — click trái chọn vị trí chèn "
            '(hoặc vạch đầu file), sau đó chuột phải ĐÚNG vị trí đó và chọn "Move đến đây" để xác nhận.'
        )

    def _on_head_marker_clicked(self) -> None:
        if self._move_source_thumb is None:
            return
        self._set_move_target(None)

    def _set_move_target(self, thumb: Optional[_EditPageThumbnail]) -> None:
        if self._move_target_thumb is not None:
            self._move_target_thumb.set_move_target(False)
        if self._move_target_is_head:
            self.head_marker.set_target(False)

        if thumb is None:
            self._move_target_after = 0
            self._move_target_thumb = None
            self._move_target_is_head = True
            self.head_marker.set_target(True)
        else:
            self._move_target_after = thumb.page_number
            self._move_target_thumb = thumb
            self._move_target_is_head = False
            thumb.set_move_target(True)
            self._select_page(thumb.page_number)

    def _on_move_confirm_requested(self, thumb: Optional[_EditPageThumbnail]) -> None:
        if self._move_source_thumb is None or self._move_target_after is None:
            return
        if thumb is None:
            if not self._move_target_is_head:
                return
        elif thumb is not self._move_target_thumb:
            return
        self._execute_move()

    def _on_head_marker_confirm(self) -> None:
        self._on_move_confirm_requested(None)

    def _execute_move(self) -> None:
        if self._session is None:
            return
        before = self._session.snapshot()

        source = self._move_source_thumb
        target_after = self._move_target_after
        old_pos = source.page_number
        n = len(self._thumbnails)

        positions = [p for p in range(1, n + 1) if p != old_pos]
        insert_at = 0 if target_after == 0 else positions.index(target_after) + 1
        positions.insert(insert_at, old_pos)

        self._thumbnails = [self._thumbnails[p - 1] for p in positions]
        self._preview_frames = [self._preview_frames[p - 1] for p in positions]

        new_order = [t.original_id for t in self._thumbnails]
        self._session.reorder(new_order)
        after = self._session.snapshot()
        self._undo.register("move", before, after)
        self._update_undo_redo_buttons()

        new_position = positions.index(old_pos) + 1
        self._renumber_and_relayout()
        self._end_move()
        self._select_page(new_position)
        self._show_success(f"Đã move trang tới vị trí {new_position}.")

    def _on_move_cancel_requested(self) -> None:
        if self._move_source_thumb is None:
            return
        self._end_move()
        self._show_success("Đã hủy Move.")

    def _end_move(self) -> None:
        if self._move_source_thumb is not None:
            self._move_source_thumb.set_cut(False)
        if self._move_target_thumb is not None:
            self._move_target_thumb.set_move_target(False)
        if self._move_target_is_head:
            self.head_marker.set_target(False)
        self._move_source_thumb = None
        self._move_target_after = None
        self._move_target_thumb = None
        self._move_target_is_head = False
        for t in self._thumbnails:
            t.set_move_mode_active(False)
        self.head_marker.set_move_mode_active(False)
        self.delete_checkbox.setEnabled(True)
        self._update_undo_redo_buttons()

    def _force_reset_move_state(self) -> None:
        self._move_source_thumb = None
        self._move_target_after = None
        self._move_target_thumb = None
        self._move_target_is_head = False
        self.head_marker.set_target(False)
        self.head_marker.set_move_mode_active(False)
        self.delete_checkbox.setEnabled(True)
        self._update_undo_redo_buttons()

    def _renumber_and_relayout(self) -> None:
        for idx, thumb in enumerate(self._thumbnails):
            thumb.set_page_number(idx + 1)
            thumb.show()

        while self.thumb_grid.count():
            self.thumb_grid.takeAt(0)
        for idx, thumb in enumerate(self._thumbnails):
            row, col = divmod(idx, _GRID_COLUMNS)
            self.thumb_grid.addWidget(thumb, row, col)

        # Đặt rowStretch cho hàng tiếp theo sau hàng cuối cùng để thu hút khoảng trống thừa bên dưới
        last_row = (len(self._thumbnails) - 1) // _GRID_COLUMNS + 1 if self._thumbnails else 0
        self.thumb_grid.setRowStretch(last_row, 1)

        preview_layout = self.preview_scroll_b.widget().layout()
        while preview_layout.count():
            preview_layout.takeAt(0)
        for idx, frame in enumerate(self._preview_frames):
            frame.show()
            preview_layout.addWidget(frame, alignment=Qt.AlignHCenter)
            frame._position_label.setText(f"Vị trí #{idx + 1}")

    # ------------------------------------------------------------------
    def _delete_marked_pages(self) -> bool:
        if self._session is None:
            return False
        marked_thumbs = [t for t in self._thumbnails if t.is_flagged]
        if not marked_thumbs:
            return False

        before = self._session.snapshot()
        self._session.delete_marked()
        after = self._session.snapshot()
        self._undo.register("delete", before, after)
        self._update_undo_redo_buttons()

        marked_ids = {t.original_id for t in marked_thumbs}
        self._thumbnails = [t for t in self._thumbnails if t.original_id not in marked_ids]
        self._preview_frames = [f for f in self._preview_frames if f.original_id not in marked_ids]

        preview_layout = self.preview_scroll_b.widget().layout()
        for t in marked_thumbs:
            t.set_flagged(False)
            self.thumb_grid.removeWidget(t)
            t.hide()
            frame = self._frame_by_id.get(t.original_id)
            if frame is not None:
                preview_layout.removeWidget(frame)
                frame.hide()

        self._renumber_and_relayout()
        self._select_page(1 if self._thumbnails else None)
        self._show_success(f"Đã xóa {len(marked_thumbs)} trang khỏi lưới (chưa ghi ra file).")
        return True

    def _on_delete_key_pressed_from_ui(self) -> None:
        if not self._delete_marked_pages():
            self._show_error(
                "Chưa đánh dấu trang nào để xóa (chuột phải vào trang muốn xóa khi đang bật chế độ Xóa)."
            )

    # ------------------------------------------------------------------
    def _on_undo_clicked(self) -> None:
        if self._session is None:
            return
        snapshot = self._undo.undo()
        if snapshot is None:
            self._show_error("Không còn thao tác nào để Undo.")
            return
        self._apply_snapshot_to_ui(snapshot)
        self._update_undo_redo_buttons()
        self._show_success("Đã Undo thao tác gần nhất.")

    def _on_redo_clicked(self) -> None:
        if self._session is None:
            return
        snapshot = self._undo.redo()
        if snapshot is None:
            self._show_error("Không còn thao tác nào để Redo.")
            return
        self._apply_snapshot_to_ui(snapshot)
        self._update_undo_redo_buttons()
        self._show_success("Đã Redo thao tác vừa Undo.")

    def _on_clear_clicked(self) -> None:
        self._selected_file_path = None
        self._session = None
        self._undo = UndoManager()
        self.delete_checkbox.setChecked(False)
        self._force_reset_move_state()
        self._zoom_level = _ZOOM_DEFAULT
        self._current_preview_width = None
        self._initial_width_applied = False
        self._clear_grid_widgets()
        self._update_zoom_percent_label()
        self._update_undo_redo_buttons()
        self.a3_title_label.setText('File được chọn: ""')
        self.preview_title_label.setText('Xem trước: ""')
        self._hide_result()

    def _select_page(self, page_number: Optional[int]) -> None:
        for thumb in self._thumbnails:
            thumb.set_selected(page_number is not None and thumb.page_number == page_number)
        if page_number and 1 <= page_number <= len(self._preview_frames):
            target = self._preview_frames[page_number - 1]
            self.preview_scroll_b.ensureWidgetVisible(target, 0, 0)

    # ------------------------------------------------------------------
    def _open_containing_folder(self, file_path: str) -> None:
        """Tự động mở thư mục chứa file kết quả sau khi lưu thành công — giống hệt cơ
        chế của Tách file/Chèn file."""
        folder = os.path.dirname(os.path.abspath(file_path)) or "."
        QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def _on_save_clicked(self) -> None:
        if not self._selected_file_path or self._session is None:
            self._show_error("Vui lòng chọn file PDF trước khi lưu.")
            return
        if self._move_source_thumb is not None:
            self._show_error(
                "Đang có 1 trang ở trạng thái Move dở dang, vui lòng hoàn tất hoặc Hủy Move trước khi lưu."
            )
            return

        self._delete_marked_pages()

        if not self._session.page_order:
            self._show_error(
                "Không còn trang nào để lưu — vui lòng Undo lại thao tác Xóa hoặc chọn file khác."
            )
            return

        base_name, _ext = os.path.splitext(os.path.basename(self._selected_file_path))
        default_name = f"{base_name}_edited.pdf"
        default_dir = os.path.dirname(self._selected_file_path)
        default_path = os.path.join(default_dir, default_name) if default_dir else default_name

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Lưu file đã chỉnh sửa",
            default_path,
            "PDF Files (*.pdf)",
            options=QFileDialog.Option.DontConfirmOverwrite,
        )
        if not save_path:
            return
        while os.path.exists(save_path):
            action = _OverwriteConfirmDialog.ask(self, os.path.basename(save_path))
            if action == _OverwriteConfirmDialog.ACTION_OVERWRITE:
                break
            elif action == _OverwriteConfirmDialog.ACTION_RENAME:
                save_path, _ = QFileDialog.getSaveFileName(
                    self,
                    "Lưu file đã chỉnh sửa",
                    save_path,
                    "PDF Files (*.pdf)",
                    options=QFileDialog.Option.DontConfirmOverwrite,
                )
                if not save_path:
                    return
                continue
            else:  # Hủy
                return

        try:
            output_path = self._session.apply(save_path)
        except pdf_core.FileLockedError:
            self._show_error("File đang được sử dụng bởi chương trình khác, vui lòng đóng và thử lại.")
            return
        except (pdf_core.CorruptedFileError, pdf_core.PasswordProtectedError) as exc:
            self._show_error(f"Không thể đọc lại file gốc để lưu: {exc}")
            return

        self._undo.clear()
        self._update_undo_redo_buttons()
        self._show_success(f"Đã lưu file thành công: {output_path}")
        self._open_containing_folder(output_path)

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