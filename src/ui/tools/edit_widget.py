"""
Giao diện tính năng Edit File — bố cục theo khuôn mẫu split_widget.py, đã bổ sung đầy đủ
cơ chế "Move" (sắp xếp lại trang) theo đặc tả 02_dac_ta_tinh_nang.md mục 3.

Bố cục 2 cột (A ~55% - B ~45%):
- Cột A: A1 khối chọn file (chỉ 1 file) + A3 khung chứa tiêu đề, vạch đích "đầu file"
  (luôn hiển thị, chỉ có tác dụng khi đang Move) và lưới thumbnail 3 cột.
- Chuột phải vào 1 trang (không có lượt Move nào đang chạy, chưa bị đánh dấu Xóa):
  menu "Xoay trái 90° / Xoay phải 90° / Move".
- Bấm "Move" → trang đó chuyển trạng thái "cut" (mờ xám, giống Cut file Windows); mọi
  thumbnail khác + vạch đầu file chuyển menu chuột phải còn "Move đến đây" / "Hủy Move".
  Click trái 1 thumbnail khác (hoặc vạch đầu file) để đặt "vạch đỏ" (đích chèn) + xem
  preview; chuột phải ĐÚNG vị trí đang giữ vạch đỏ → "Move đến đây" để xác nhận
  (2 bước tách biệt, KHÔNG gộp — bắt buộc phải click trái xác định vị trí trước).
- Trang đã đánh dấu Xóa không được chọn làm nguồn Move (menu ẩn mục "Move").
- Mỗi lượt Move chỉ áp dụng đúng 1 trang; mỗi lần Move hoàn tất sẽ đăng ký 1 bước riêng
  vào undo_manager (khi được nối thật).
- Hàng thao tác dưới cùng: Nhãn "Xóa" + checkbox (bị disable trong lúc đang Move) → Undo
  → Clear → Lưu File.
- Cột B: khung preview cuộn liên tục nhiều trang, re-render lại theo đúng thứ tự mới sau
  mỗi lần Move. Bổ sung Zoom In/Out (±15%, 50%-200%, mặc định 100% = vừa khít khung, đồng
  bộ với split_widget.py/merge_widget.py) + pan chuột trái khi đã zoom to hơn khung. Chiều
  rộng trang được tính lại đúng 1 lần lúc cửa sổ hiển thị thật (showEvent) để tránh lỗi
  khoảng trắng lớn 2 bên do khung mock dựng quá sớm lúc __init__.

LƯU Ý: đây vẫn là bước dựng UI + trạng thái trong bộ nhớ (mock, dùng _MOCK_PAGE_COUNT trang
giả) — Move/Xoay/Xóa chưa gọi pdf_core.py / undo_manager.py thật, xem các TODO trong file.
Số LỚN ở giữa mỗi thumbnail là "nội dung" mock (original_id) — CỐ ĐỊNH, không đổi khi Move,
mô phỏng đúng hành vi của bản thật (mỗi thumbnail luôn hiển thị ảnh render của đúng trang gốc).
Badge nhỏ "#..." ở góc trên mới là vị trí hiển thị hiện tại, được đánh lại liên tục 1..N sau
mỗi lần Move — nhờ tách 2 khái niệm này, khi kiểm thử sẽ thấy rõ trang nào đã di chuyển tới
đâu (VD: move trang nội dung "5" về đầu file → số lớn "5" xuất hiện ở ô đầu tiên, badge "#1").
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
    QGridLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QMenu,
    QScrollArea,
    QFrame,
    QFileDialog,
    QGraphicsOpacityEffect,
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
_MOCK_PAGE_COUNT = 11
_GRID_COLUMNS = 3
_THUMB_SIZE = 128

# Tỉ lệ khung hình của khung trang mock (Cột B) — chiều rộng thực tế giờ co giãn theo
# khung hiển thị + hệ số zoom (xem _compute_preview_width()), không còn cố định 340px.
_PREVIEW_PAGE_WIDTH_FALLBACK = 340
_PREVIEW_PAGE_HEIGHT_DEFAULT = 460

# Zoom Cột B: mỗi lần bấm Zoom In/Out ±15%, giới hạn 50%-200%.
# Mặc định 100% = chiều rộng "vừa khít khung hiển thị" hiện tại — đồng bộ với
# split_widget.py / merge_widget.py.
_ZOOM_MIN = 0.5
_ZOOM_MAX = 2.0
_ZOOM_STEP = 0.15
_ZOOM_DEFAULT = 1.0

# Lề trái/phải giữa nội dung preview và biên khung Cột B.
_PREVIEW_SIDE_MARGIN = 12
_PREVIEW_MIN_PAGE_WIDTH = 220

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


# ----------------------------------------------------------------------
# A3 — 1 ô trong lưới thumbnail: thumbnail giấy + trạng thái đánh dấu xóa / cut / đích Move.
# Khi chế độ "Xóa" bật, chuột phải sẽ toggle đánh dấu xóa thay vì mở menu.
# ----------------------------------------------------------------------
class _EditPageThumbnail(QWidget):
    clicked = Signal(object)  # emit(self) — chọn trang xem preview / chọn vị trí đích khi đang Move
    rotate_requested = Signal(object, str)  # emit(self, "left" | "right")
    move_requested = Signal(object)  # emit(self) — self muốn trở thành nguồn Move ("cut")
    move_confirm_requested = Signal(object)  # emit(self) — self đang giữ vạch đỏ, xác nhận "Move đến đây"
    move_cancel_requested = Signal()  # hủy Move giữa chừng (không cần biết bấm từ thumbnail nào)

    def __init__(self, original_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.original_id = original_id  # "nội dung" trang — CỐ ĐỊNH, không đổi khi Move (mock cho
        # render_page_thumbnail() thật sau này: mỗi thumbnail luôn hiển thị đúng trang gốc của nó).
        self.page_number = original_id  # vị trí hiển thị hiện tại (1..N) — cập nhật mỗi khi Move
        self.is_selected = False
        self.is_flagged = False  # đang được đánh dấu để xóa
        self.delete_mode = False
        self.is_cut = False  # đang là nguồn của 1 lượt Move ("cắt" — mờ xám kiểu Cut Windows)
        self.is_move_target = False  # đang giữ "vạch đỏ" — vị trí sẽ chèn trang cut vào ngay sau nó
        self._move_active = False  # có 1 lượt Move (không nhất thiết của chính trang này) đang chạy
        # TODO Giai đoạn 2/3: rotation hiện chỉ là badge hiển thị tạm; khi có
        # render_page_thumbnail() thật từ pdf_core.py, thay bằng xoay ảnh PNG thật.
        self.rotation = 0
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

        # Badge vị trí hiện tại (góc trên) — đây là phần ĐƯỢC đánh số lại 1..N sau mỗi lần Move.
        self.position_badge = QLabel(f"#{self.page_number}")
        self.position_badge.setAlignment(Qt.AlignCenter)
        self.position_badge.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 10px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(self.position_badge)

        # Số lớn = nội dung mock của trang (original_id) — KHÔNG đổi khi Move, để có thể quan
        # sát trực quan trang nào đã di chuyển tới đâu (giống cách bản thật sẽ hiển thị).
        self.number_label = QLabel(str(original_id))
        self.number_label.setAlignment(Qt.AlignCenter)
        self.number_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 26px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(self.number_label, stretch=1)

        # Nhãn chỉ hiện khi trang này đang giữ "vạch đỏ" (đích sẽ chèn trang cut vào ngay sau nó).
        self.move_target_label = QLabel("▼ Chèn vào đây")
        self.move_target_label.setAlignment(Qt.AlignCenter)
        self.move_target_label.setStyleSheet(
            f"color: {COLOR_ERROR}; font-size: 10px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        self.move_target_label.hide()
        card_layout.addWidget(self.move_target_label)

        # Badge góc xoay — chỉ hiện chữ khi trang đã bị xoay (VD "90°", "270°").
        self.rotation_badge = QLabel("")
        self.rotation_badge.setAlignment(Qt.AlignCenter)
        self.rotation_badge.setStyleSheet(
            f"color: {COLOR_ACCENT}; font-size: 11px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        card_layout.addWidget(self.rotation_badge)

        row_layout.addWidget(self.card)

    def _apply_card_style(self) -> None:
        # Thứ tự ưu tiên hiển thị khi nhiều trạng thái "lý thuyết" trùng nhau:
        # đang cut > đang là đích Move > đã đánh dấu xóa > đang chọn (preview) > bình thường.
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

    def reset_flag(self) -> None:
        self.set_flagged(False)

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
        # Chỉ cập nhật vị trí hiển thị (badge góc trên) — KHÔNG đổi number_label (đó là
        # original_id, đại diện nội dung trang thật, cố định vĩnh viễn qua các lần Move).
        self.page_number = number
        self.position_badge.setText(f"#{number}")

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
            self.clicked.emit(self)

    def contextMenuEvent(self, event) -> None:
        if self.delete_mode:
            # Chế độ Xóa: chuột phải toggle đánh dấu trực tiếp, không mở menu.
            self.set_flagged(not self.is_flagged)
            event.accept()
            return

        if self.is_flagged:
            # Trang đã đánh dấu Xóa (từ trước, lúc checkbox đang bật) — chuột phải không còn
            # tác dụng gì nữa (không Xoay, không Move/Move đến đây/Hủy Move) cho tới khi được
            # bỏ đánh dấu (bật lại checkbox "Xóa" rồi chuột phải toggle như trên).
            event.ignore()
            return

        menu = QMenu(self)
        menu.setStyleSheet(_CONTEXT_MENU_QSS)

        if self._move_active:
            # Đang có 1 lượt Move chạy trong toàn bộ lưới (không nhất thiết là chính trang này).
            if self.is_cut:
                # Đây chính là trang nguồn đang "cut" — chỉ cho phép Hủy Move.
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
            # Chỉ cho xác nhận đúng tại thumbnail đang giữ vạch đỏ (bắt buộc đã click trái chọn trước).
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

        # Chế độ bình thường: không có lượt Move nào đang chạy, trang chưa bị đánh dấu Xóa.
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


# ----------------------------------------------------------------------
# Vạch đích "đầu file" — vị trí đặc biệt để Move 1 trang về trước trang 1.
# Luôn hiển thị cố định phía trên lưới thumbnail (đơn giản hóa hiển thị theo yêu cầu —
# không cần canh chính xác ngay trên thumbnail #1); chỉ có tác dụng bấm khi đang Move.
# ----------------------------------------------------------------------
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
    """Giao diện tính năng Edit File — UI/mock, chưa nối xử lý PDF thật."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._selected_file_path: Optional[str] = None
        self._thumbnails: List[_EditPageThumbnail] = []
        self._preview_frames: List[QFrame] = []

        # --- Trạng thái của 1 lượt Move đang chạy (None nếu không có lượt nào) ---
        self._move_source_thumb: Optional[_EditPageThumbnail] = None
        self._move_target_after: Optional[int] = None  # 0 = đầu file; k = ngay sau vị trí k
        self._move_target_thumb: Optional[_EditPageThumbnail] = None
        self._move_target_is_head: bool = False

        # --- Zoom Cột B ---
        self._zoom_level: float = _ZOOM_DEFAULT
        self._current_preview_width: Optional[int] = None
        # Khung mock được dựng ngay trong __init__ (trước khi cửa sổ hiển thị xong),
        # lúc đó viewport().width() đọc được còn sai (quá nhỏ) — cần tính lại đúng 1
        # lần khi widget thật sự hiển thị (xem showEvent()).
        self._initial_width_applied = False

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

        # --- Khung bao toàn bộ khu vực A3 (Header tiêu đề + vạch đầu file + Lưới Thumbnail) ---
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

        # Vạch đích "đầu file" — luôn hiển thị, chỉ có tác dụng bấm/chuột phải khi đang Move.
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

        # --- Hàng dưới cùng: 4 nhóm chia đều theo toàn bộ chiều ngang ---
        # [Xóa + checkbox] — [Undo] — [Clear] — [Lưu File]
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(0)
        bottom_row.setContentsMargins(0, 0, 0, 0)

        # Nhóm 1: Xóa + checkbox (Đồng bộ style khung như Undo/Clear)
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

        # Icon thùng rác
        delete_icon = QLabel()
        delete_icon.setPixmap(
            qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY).pixmap(16, 16)
        )
        delete_icon.setStyleSheet("background: transparent; border: none;")
        delete_group_layout.addWidget(delete_icon)

        # Nhãn "Xóa"
        delete_label = QLabel("Xóa")
        delete_label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        delete_label.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        delete_group_layout.addWidget(delete_label)

        # Giãn cách riêng giữa nhãn "Xóa" và checkbox (tách biệt với spacing
        # chung 6px giữa icon-nhãn, để không ảnh hưởng các cặp widget khác).
        delete_group_layout.addSpacing(16)

        # Checkbox
        self.delete_checkbox = _CheckToggle()
        delete_group_layout.addWidget(self.delete_checkbox)

        self.delete_checkbox.toggled.connect(self._on_delete_mode_toggled)
        bottom_row.addWidget(delete_group, stretch=1)

        # Nhóm 2: Undo
        undo_group = QWidget()
        undo_group_layout = QHBoxLayout(undo_group)
        undo_group_layout.setContentsMargins(0, 0, 0, 0)
        undo_group_layout.setAlignment(Qt.AlignCenter)

        self.undo_button = QPushButton(" Undo")
        self.undo_button.setIcon(
            qta.icon("mdi6.undo-variant", color=COLOR_TEXT_PRIMARY)
        )
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
        self.undo_button.clicked.connect(self._on_undo_clicked)
        undo_group_layout.addWidget(self.undo_button)
        bottom_row.addWidget(undo_group, stretch=1)

        # Nhóm 3: Clear
        clear_group = QWidget()
        clear_group_layout = QHBoxLayout(clear_group)
        clear_group_layout.setContentsMargins(0, 0, 0, 0)
        clear_group_layout.setAlignment(Qt.AlignCenter)

        self.clear_button = QPushButton("Clear")
        self.clear_button.setIcon(
            qta.icon("mdi6.trash-can-outline", color=COLOR_TEXT_PRIMARY)
        )
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
        clear_group_layout.addWidget(self.clear_button)
        bottom_row.addWidget(clear_group, stretch=1)

        # Nhóm 4: Lưu File
        save_group = QWidget()
        save_group_layout = QHBoxLayout(save_group)
        save_group_layout.setContentsMargins(0, 0, 0, 0)
        save_group_layout.setAlignment(Qt.AlignCenter)

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
        save_group_layout.addWidget(self.save_button)
        bottom_row.addWidget(save_group, stretch=1)

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

        # Cụm Zoom Out / % / Zoom In — canh phải cùng hàng tiêu đề (title đã chiếm
        # stretch=1 ở trên nên các widget thêm sau tự động dồn sang phải).
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

        # Khung Preview cuộn dọc — dùng _PannablePreviewScrollArea để hỗ trợ kéo
        # bằng chuột trái (pan) và báo khi kích thước khung đổi (responsive fit-width).
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
        self._update_zoom_buttons_state()
        self._update_zoom_percent_label()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Lần hiển thị đầu tiên: cửa sổ đã có kích thước thật, tính lại chiều rộng
        # trang cho khớp khung Cột B thật sự (sửa lỗi khoảng trắng lớn 2 bên do
        # khung mock bị dựng quá sớm lúc __init__, khi viewport còn chưa có size đúng).
        if not self._initial_width_applied and self._preview_frames:
            self._initial_width_applied = True
            self._current_preview_width = None
            self._apply_preview_zoom()

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
            thumb.move_requested.connect(self._on_move_requested)
            thumb.move_confirm_requested.connect(self._on_move_confirm_requested)
            thumb.move_cancel_requested.connect(self._on_move_cancel_requested)
            self.thumb_grid.addWidget(thumb, row, col)
            self._thumbnails.append(thumb)

    # ------------------------------------------------------------------
    # Xây các trang Preview giả — xếp dọc liên tục để cuộn (Cột B)
    # ------------------------------------------------------------------
    def _build_mock_preview_pages(self, layout: QVBoxLayout) -> None:
        width = self._compute_preview_width()
        self._current_preview_width = width
        aspect_ratio = _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK
        height = round(width * aspect_ratio)

        for i in range(_MOCK_PAGE_COUNT):
            original_id = i + 1
            page_frame = QFrame()
            page_frame.setFixedSize(width, height)
            page_frame.setStyleSheet(
                f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
            )
            page_layout = QVBoxLayout(page_frame)
            page_layout.setAlignment(Qt.AlignCenter)

            # Số lớn = nội dung mock của trang (original_id) — CỐ ĐỊNH, không đổi khi Move.
            number_label = QLabel(str(original_id))
            number_label.setAlignment(Qt.AlignCenter)
            number_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 48px; font-weight: 700; "
                "background: transparent; border: none;"
            )
            page_layout.addWidget(number_label)

            # Nhãn vị trí hiện tại — ĐƯỢC cập nhật mỗi khi Move re-render Cột B theo thứ tự mới.
            position_label = QLabel(f"Vị trí #{original_id}")
            position_label.setAlignment(Qt.AlignCenter)
            position_label.setStyleSheet(
                f"color: {COLOR_TEXT_SECONDARY}; font-size: 13px; font-weight: 600; "
                "background: transparent; border: none;"
            )
            page_layout.addWidget(position_label)
            page_frame._position_label = position_label

            layout.addWidget(page_frame, alignment=Qt.AlignHCenter)
            self._preview_frames.append(page_frame)

        self._update_zoom_buttons_state()

    # ------------------------------------------------------------------
    # Zoom + Pan cho khu vực Xem trước (Cột B) — đồng bộ với split_widget.py
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

        aspect_ratio = _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK
        new_height = round(new_width * aspect_ratio)
        for frame in self._preview_frames:
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
        has_pages = bool(self._preview_frames)
        self.zoom_in_btn.setEnabled(has_pages and self._zoom_level < _ZOOM_MAX - 1e-6)
        self.zoom_out_btn.setEnabled(has_pages and self._zoom_level > _ZOOM_MIN + 1e-6)

    def _update_zoom_percent_label(self) -> None:
        self.zoom_percent_label.setText(f"{round(self._zoom_level * 100)}%")

    def _on_preview_viewport_resized(self) -> None:
        if self._preview_frames:
            self._apply_preview_zoom()

    # ------------------------------------------------------------------
    # Sự kiện — Chọn file / Xóa / Chọn trang / Xoay
    # ------------------------------------------------------------------
    def _on_file_selected(self, path: str) -> None:
        self._selected_file_path = path
        self.delete_checkbox.setChecked(False)
        self.delete_checkbox.setEnabled(True)
        self._force_reset_move_state()
        self._reset_mock_content()
        self._select_page(1)
        self._hide_result()

    def _on_delete_mode_toggled(self, checked: bool) -> None:
        # Chỉ chuyển trạng thái tương tác. Các trang đã đánh dấu phải được giữ nguyên
        # để người dùng có thể tắt Xóa và tiếp tục xoay trang trước khi lưu.
        if self._move_source_thumb is not None:
            # An toàn: checkbox bị disable trong lúc đang Move nên nhánh này không nên xảy ra.
            return
        for thumb in self._thumbnails:
            thumb.set_delete_mode(checked)

    def _on_thumbnail_clicked(self, thumb: _EditPageThumbnail) -> None:
        if self._move_source_thumb is not None:
            if thumb is self._move_source_thumb or thumb.is_flagged:
                # Không thể chọn chính trang đang cut, hoặc 1 trang đã đánh dấu Xóa, làm đích
                # (trang đã đánh dấu Xóa không còn phản hồi chuột phải nên không thể xác nhận).
                return
            self._set_move_target(thumb)
            return
        # Chuột trái ở chế độ bình thường: chỉ dùng để chọn trang xem preview.
        self._select_page(thumb.page_number)

    def _on_rotate_requested(self, thumb: _EditPageThumbnail, direction: str) -> None:
        # TODO Giai đoạn 2/3: gọi pdf_core.rotate_page() + undo_manager.register() thật.
        thumb.apply_rotation(direction)
        huong = "trái" if direction == "left" else "phải"
        self._show_success(
            f"[Demo giao diện] Đã xoay {huong} 90° trang {thumb.page_number} — chưa xử lý PDF thật."
        )

    # ------------------------------------------------------------------
    # Sự kiện — Cơ chế Move (sắp xếp lại trang)
    # ------------------------------------------------------------------
    def _on_move_requested(self, thumb: _EditPageThumbnail) -> None:
        if self._move_source_thumb is not None or thumb.is_flagged:
            # An toàn: không mở lượt Move mới khi đang có lượt khác chạy, hoặc trang đã đánh dấu xóa.
            return
        self._move_source_thumb = thumb
        self._move_target_after = None
        self._move_target_thumb = None
        self._move_target_is_head = False
        thumb.set_cut(True)
        self.delete_checkbox.setEnabled(False)
        for t in self._thumbnails:
            t.set_move_mode_active(True)
        self.head_marker.set_move_mode_active(True)
        self._show_success(
            f"[Demo giao diện] Đang di chuyển trang {thumb.page_number} — click trái chọn vị trí chèn "
            '(hoặc vạch đầu file), sau đó chuột phải ĐÚNG vị trí đó và chọn "Move đến đây" để xác nhận.'
        )

    def _on_head_marker_clicked(self) -> None:
        if self._move_source_thumb is None:
            return
        self._set_move_target(None)

    def _set_move_target(self, thumb: Optional[_EditPageThumbnail]) -> None:
        # Bỏ highlight vạch đỏ ở vị trí cũ (nếu có) trước khi đặt vị trí mới.
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
        # Bắt buộc xác nhận đúng tại vị trí đang giữ vạch đỏ (không gộp bước chọn vị trí và xác nhận).
        if thumb is None:
            if not self._move_target_is_head:
                return
        elif thumb is not self._move_target_thumb:
            return
        self._execute_move()

    def _on_head_marker_confirm(self) -> None:
        self._on_move_confirm_requested(None)

    def _execute_move(self) -> None:
        source = self._move_source_thumb
        target_after = self._move_target_after
        old_pos = source.page_number
        n = len(self._thumbnails)

        # Tính hoán vị vị trí mới: bỏ vị trí cũ ra khỏi dãy 1..N rồi chèn lại ngay sau target_after
        # (0 = đầu file). Sau vòng lặp, positions[i] = vị trí CŨ của trang sẽ nằm ở vị trí MỚI i+1.
        positions = [p for p in range(1, n + 1) if p != old_pos]
        insert_at = 0 if target_after == 0 else positions.index(target_after) + 1
        positions.insert(insert_at, old_pos)

        self._thumbnails = [self._thumbnails[p - 1] for p in positions]
        self._preview_frames = [self._preview_frames[p - 1] for p in positions]

        new_position = positions.index(old_pos) + 1
        self._renumber_and_relayout()
        self._end_move()
        self._select_page(new_position)
        self._show_success(
            f"[Demo giao diện] Đã move trang tới vị trí {new_position} — chưa nối undo_manager.py / "
            "pdf_core.reorder_pages() thật."
        )
        # TODO Giai đoạn 2/3: undo_manager.register("move", {...}) lưu lại vị trí cũ để Undo trả về đúng
        # chỗ; khi bấm "Áp dụng"/"Lưu File", thứ tự cuối cùng của self._thumbnails chính là new_order
        # truyền cho pdf_core.reorder_pages().

    def _on_move_cancel_requested(self) -> None:
        if self._move_source_thumb is None:
            return
        self._end_move()
        self._show_success("[Demo giao diện] Đã hủy Move.")

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

    def _force_reset_move_state(self) -> None:
        # Dùng khi Clear/đổi file: các thumbnail cũ sắp bị deleteLater() nên chỉ cần xóa biến
        # trạng thái, không cần gọi set_cut/set_move_target lên các widget sắp bị hủy.
        self._move_source_thumb = None
        self._move_target_after = None
        self._move_target_thumb = None
        self._move_target_is_head = False
        self.head_marker.set_target(False)
        self.head_marker.set_move_mode_active(False)
        self.delete_checkbox.setEnabled(True)

    def _renumber_and_relayout(self) -> None:
        # Đánh lại số thứ tự liên tục 1..N theo vị trí mới (không giữ số trang gốc),
        # rồi dựng lại lưới Cột A và ngăn xếp cuộn Cột B theo đúng thứ tự đó.
        for idx, thumb in enumerate(self._thumbnails):
            thumb.set_page_number(idx + 1)

        while self.thumb_grid.count():
            self.thumb_grid.takeAt(0)  # chỉ gỡ khỏi layout, KHÔNG hủy widget — giữ nguyên trạng thái
        for idx, thumb in enumerate(self._thumbnails):
            row, col = divmod(idx, _GRID_COLUMNS)
            self.thumb_grid.addWidget(thumb, row, col)

        preview_layout = self.preview_scroll_b.widget().layout()
        while preview_layout.count():
            preview_layout.takeAt(0)
        for idx, frame in enumerate(self._preview_frames):
            preview_layout.addWidget(frame, alignment=Qt.AlignHCenter)
            frame._position_label.setText(f"Vị trí #{idx + 1}")

    def _reset_mock_content(self) -> None:
        # Gỡ và hủy toàn bộ thumbnail + trang preview cũ, dựng lại từ đầu — dùng khi Clear
        # hoặc chọn file mới, để tránh giữ lại thứ tự/trạng thái Move của phiên trước.
        for thumb in self._thumbnails:
            self.thumb_grid.removeWidget(thumb)
            thumb.setParent(None)
            thumb.deleteLater()
        self._thumbnails = []

        preview_layout = self.preview_scroll_b.widget().layout()
        for frame in self._preview_frames:
            preview_layout.removeWidget(frame)
            frame.setParent(None)
            frame.deleteLater()
        self._preview_frames = []

        self._build_mock_grid()
        self._build_mock_preview_pages(preview_layout)

    # ------------------------------------------------------------------
    # Sự kiện — Undo / Clear / Lưu File
    # ------------------------------------------------------------------
    def _on_undo_clicked(self) -> None:
        # TODO Giai đoạn 2/3: nối với undo_manager.py thật (hoàn tác Move/Xoay/Xóa) — hiện là mock.
        self._show_success("[Demo giao diện] Nút Undo — chưa nối undo_manager.py thật.")

    def _on_clear_clicked(self) -> None:
        self._selected_file_path = None
        self.delete_checkbox.setChecked(False)
        self._force_reset_move_state()
        self._zoom_level = _ZOOM_DEFAULT
        self._reset_mock_content()
        self._update_zoom_percent_label()
        self._select_page(1)
        self._hide_result()

    def _select_page(self, page_number: int) -> None:
        for thumb in self._thumbnails:
            thumb.set_selected(thumb.page_number == page_number)
        if 1 <= page_number <= len(self._preview_frames):
            target = self._preview_frames[page_number - 1]
            self.preview_scroll_b.ensureWidgetVisible(target, 0, 0)

    def _on_save_clicked(self) -> None:
        if not self._selected_file_path:
            self._show_error("Vui lòng chọn file PDF trước khi lưu.")
            return
        if self._move_source_thumb is not None:
            self._show_error(
                "Đang có 1 trang ở trạng thái Move dở dang, vui lòng hoàn tất hoặc Hủy Move trước khi lưu."
            )
            return

        flagged = [t.page_number for t in self._thumbnails if t.is_flagged]
        rotated = {t.page_number: t.rotation for t in self._thumbnails if t.rotation}

        # TODO Giai đoạn 2/3: gọi tuần tự pdf_core (reorder_pages theo thứ tự self._thumbnails
        # hiện tại, rotate_page, delete_pages) theo lịch sử undo_manager rồi ghi 1 file
        # <tenfilegoc>_edited.pdf duy nhất.
        self._show_success(
            f"[Demo giao diện] Sẽ lưu file mới theo đúng thứ tự hiện tại trên lưới — xóa trang: "
            f"{flagged or 'không có'}, xoay trang: {rotated or 'không có'} — chưa xử lý PDF thật."
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