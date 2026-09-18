"""
Giao diện tính năng Chèn Watermark (WatermarkFeatureWidget) — Vishipel PDF Tools.

Đã fix các vấn đề:
1. Chỉnh màu chữ trong bảng chọn màu QColorDialog thành màu đen rõ nét.
2. Bỏ khung bao ngoài cho giao diện Text (Text, Font size, Color nằm ngoài khung).
3. Bỏ khung bao ngoài cho giao diện Image (tách riêng phần chọn ảnh & Scale).
4. Bỏ 2 nút mũi tên lên/xuống ở các ô nhập %, chỉ giữ lại ô nhập số thuần túy.
5. Bỏ nền xám mặc định còn sót lại ở 2 trang con của config_stack (Text/Image) —
   QWidget trần trước đó không có stylesheet riêng nên bị dính theme nền xám của app;
   đã ép transparent tường minh cho config_stack, text_config_widget, image_config_widget,
   đồng thời nới margin/spacing để bù lại khoảng thở sau khi bỏ khung.
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional

import qtawesome as qta
from PySide6.QtCore import Qt, Signal, QSize, QPoint, QRectF
from PySide6.QtGui import (
    QDragEnterEvent,
    QDropEvent,
    QColor,
    QPainter,
    QFont,
    QPen,
    QBrush,
    QPixmap,
)
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
    QLineEdit,
    QComboBox,
    QSlider,
    QSpinBox,
    QColorDialog,
    QStackedWidget,
    QButtonGroup,
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

_LABEL_STYLE = f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 700; background: transparent; border: none;"

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


class _WatermarkPreviewPage(QFrame):
    """Trang xem trước vẽ mô phỏng Watermark động trực tiếp."""

    def __init__(self, page_number: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.page_number = page_number
        self.aspect_ratio = _PREVIEW_PAGE_HEIGHT_DEFAULT / _PREVIEW_PAGE_WIDTH_FALLBACK

        self.wm_type = "Text"
        self.wm_text = "CONFIDENTIAL"
        self.wm_font_size = 36
        self.wm_color = QColor("#B91C1C")
        self.wm_image_path: Optional[str] = None
        self.wm_scale = 75
        self.wm_opacity = 50
        self.wm_rotation = 45
        self.wm_layer = "Over Content"

        self.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1px solid {COLOR_BORDER}; border-radius: 6px; }}"
        )

    def update_watermark_config(
        self,
        wm_type: str,
        text: str,
        font_size: int,
        color: QColor,
        image_path: Optional[str],
        scale: int,
        opacity: int,
        rotation: int,
        layer: str,
    ) -> None:
        self.wm_type = wm_type
        self.wm_text = text
        self.wm_font_size = font_size
        self.wm_color = color
        self.wm_image_path = image_path
        self.wm_scale = scale
        self.wm_opacity = opacity
        self.wm_rotation = rotation
        self.wm_layer = layer
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        w = self.width()
        h = self.height()

        painter.setPen(QPen(QColor(COLOR_TEXT_SECONDARY)))
        painter.setFont(QFont("Segoe UI", 12, QFont.Bold))
        painter.drawText(QRectF(12, 12, 40, 24), Qt.AlignLeft | Qt.AlignVCenter, str(self.page_number))

        if self.wm_layer == "Under Content":
            self._draw_watermark(painter, w, h)
            self._draw_dummy_content(painter, w, h)
        else:
            self._draw_dummy_content(painter, w, h)
            self._draw_watermark(painter, w, h)

    def _draw_dummy_content(self, painter: QPainter, w: int, h: int) -> None:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor("#E2E8F0")))
        margin = 30
        line_height = 10
        spacing = 14
        curr_y = 60
        while curr_y < h - 40:
            line_w = w - (margin * 2) if (curr_y % 3 != 0) else (w - margin * 2) * 0.65
            painter.drawRoundedRect(QRectF(margin, curr_y, line_w, line_height), 3, 3)
            curr_y += line_height + spacing

    def _draw_watermark(self, painter: QPainter, w: int, h: int) -> None:
        painter.save()

        alpha = max(0, min(255, round((self.wm_opacity / 100.0) * 255)))
        center_x = w / 2.0
        center_y = h / 2.0

        painter.translate(center_x, center_y)
        painter.rotate(-self.wm_rotation)

        if self.wm_type == "Text":
            if self.wm_text.strip():
                color = QColor(self.wm_color)
                color.setAlpha(alpha)
                painter.setPen(QPen(color))

                scaled_font_size = max(10, round(self.wm_font_size * (w / _PREVIEW_PAGE_WIDTH_FALLBACK)))
                font = QFont("Segoe UI", scaled_font_size, QFont.Bold)
                painter.setFont(font)

                rect = QRectF(-w, -h / 2, w * 2, h)
                painter.drawText(rect, Qt.AlignCenter, self.wm_text)

        elif self.wm_type == "Image":
            pixmap = None
            if self.wm_image_path:
                pixmap = QPixmap(self.wm_image_path)

            if pixmap is None or pixmap.isNull():
                pixmap = qta.icon("mdi6.watermark", color="#FA9005").pixmap(QSize(120, 120))

            scale_factor = (self.wm_scale / 100.0) * (w / _PREVIEW_PAGE_WIDTH_FALLBACK)
            target_w = pixmap.width() * scale_factor
            target_h = pixmap.height() * scale_factor

            painter.setOpacity(self.wm_opacity / 100.0)
            target_rect = QRectF(-target_w / 2.0, -target_h / 2.0, target_w, target_h)
            painter.drawPixmap(target_rect.toRect(), pixmap)

        painter.restore()


# ----------------------------------------------------------------------
# Widget Chính (WatermarkFeatureWidget)
# ----------------------------------------------------------------------
class WatermarkFeatureWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._current_file_path: Optional[str] = None
        self._current_total_pages = 0
        self._current_page = 0
        self._preview_thumbs: List[_PreviewThumb] = []
        self._preview_pages: Dict[int, _WatermarkPreviewPage] = {}

        self._zoom_level: float = _ZOOM_DEFAULT
        self._current_preview_width: Optional[int] = None
        self._initial_width_applied = False

        self._watermark_image_path: Optional[str] = None
        self._selected_color = QColor("#B91C1C")

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

        # --- A2: Watermark Configuration Card ---
        config_card = QFrame()
        config_card.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1.5px solid {COLOR_BORDER}; border-radius: 14px; }}"
        )
        config_layout = QVBoxLayout(config_card)
        config_layout.setContentsMargins(18, 16, 18, 16)
        config_layout.setSpacing(14)

        card_title = QLabel("Watermark Configuration")
        card_title.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 15px; font-weight: 700; "
            "background: transparent; border: none;"
        )
        config_layout.addWidget(card_title)

        # Watermark Type Selection
        type_label = QLabel("Watermark Type")
        type_label.setStyleSheet(_LABEL_STYLE)
        config_layout.addWidget(type_label)

        self.type_segmented = _SegmentedControl(["Text", "Image"])
        self.type_segmented.selection_changed.connect(self._on_type_changed)
        config_layout.addWidget(self.type_segmented)

        # --- Stacked Widget cho phần cấu hình chi tiết (Text / Image) ---
        self.config_stack = QStackedWidget()
        self.config_stack.setStyleSheet(
            "QStackedWidget { background: transparent; border: none; }"
        )

        # === PAGE 1: TEXT CONFIG (không khung bao quanh, tiêu đề nằm ngoài) ===
        text_config_widget = QWidget()
        text_config_widget.setStyleSheet(
            "QWidget { background: transparent; border: none; }"
        )
        text_config_layout = QVBoxLayout(text_config_widget)
        text_config_layout.setContentsMargins(0, 10, 0, 4)
        text_config_layout.setSpacing(14)

        text_input_label = QLabel("Text")
        text_input_label.setStyleSheet(_LABEL_STYLE)
        text_config_layout.addWidget(text_input_label)

        self.text_input = QLineEdit("CONFIDENTIAL")
        self.text_input.setFixedHeight(CONTROL_HEIGHT)
        self.text_input.setStyleSheet(
            f"""
            QLineEdit {{
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                padding: 0 12px;
                font-size: 13px;
                color: {COLOR_TEXT_PRIMARY};
            }}
            QLineEdit:focus {{
                border-color: {COLOR_ACCENT};
            }}
            """
        )
        self.text_input.textChanged.connect(self._sync_preview)
        text_config_layout.addWidget(self.text_input)

        font_color_row = QHBoxLayout()
        font_color_row.setSpacing(10)

        # Font Size Dropdown
        font_col = QVBoxLayout()
        font_col.setSpacing(4)
        font_lbl = QLabel("Font size")
        font_lbl.setStyleSheet(_LABEL_STYLE)
        self.font_combo = QComboBox()
        self.font_combo.setFixedHeight(CONTROL_HEIGHT)
        self.font_combo.addItems(["18 pt", "24 pt", "36 pt", "48 pt", "60 pt", "72 pt"])
        self.font_combo.setCurrentText("36 pt")
        self.font_combo.setStyleSheet(
            f"""
            QComboBox {{
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                padding: 0 10px;
                font-size: 13px;
                color: {COLOR_TEXT_PRIMARY};
                font-weight: 600;
            }}
            QComboBox QAbstractItemView {{
                color: {COLOR_TEXT_PRIMARY};
                background-color: white;
                selection-background-color: {COLOR_ACCENT_LIGHT};
                selection-color: {COLOR_TEXT_PRIMARY};
            }}
            """
        )
        self.font_combo.currentTextChanged.connect(self._sync_preview)
        font_col.addWidget(font_lbl)
        font_col.addWidget(self.font_combo)

        # Color Picker
        color_col = QVBoxLayout()
        color_col.setSpacing(4)
        color_lbl = QLabel("Color")
        color_lbl.setStyleSheet(_LABEL_STYLE)
        self.color_btn = QPushButton()
        self.color_btn.setFixedHeight(CONTROL_HEIGHT)
        self.color_btn.setCursor(Qt.PointingHandCursor)
        self._update_color_btn_style()
        self.color_btn.clicked.connect(self._open_color_dialog)
        color_col.addWidget(color_lbl)
        color_col.addWidget(self.color_btn)

        font_color_row.addLayout(font_col, 1)
        font_color_row.addLayout(color_col, 1)
        text_config_layout.addLayout(font_color_row)

        self.config_stack.addWidget(text_config_widget)

        # === PAGE 2: IMAGE CONFIG (thẻ chọn ảnh & Scale tách riêng, không khung gộp) ===
        image_config_widget = QWidget()
        image_config_widget.setStyleSheet(
            "QWidget { background: transparent; border: none; }"
        )
        image_config_layout = QVBoxLayout(image_config_widget)
        image_config_layout.setContentsMargins(0, 10, 0, 4)
        image_config_layout.setSpacing(14)

        # Thẻ Dropzone Chọn Ảnh
        self.img_card = QFrame()
        self.img_card.setStyleSheet(
            f"QFrame {{ background-color: white; border: 1.5px dashed {COLOR_BORDER_STRONG}; border-radius: 10px; }}"
        )
        img_card_layout = QHBoxLayout(self.img_card)
        img_card_layout.setContentsMargins(12, 8, 12, 8)
        img_card_layout.setSpacing(10)

        img_icon = QLabel()
        img_icon.setPixmap(qta.icon("mdi6.image-outline", color=COLOR_ACCENT).pixmap(QSize(28, 28)))
        img_icon.setStyleSheet("background: transparent; border: none;")
        img_card_layout.addWidget(img_icon)

        img_text_col = QVBoxLayout()
        img_text_col.setSpacing(1)
        self.img_name_lbl = QLabel("Tải ảnh làm watermark (PNG, JPG)")
        self.img_name_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_PRIMARY}; font-size: 13px; font-weight: 600; background: transparent; border: none;"
        )
        self.img_sub_lbl = QLabel("Chưa chọn file ảnh")
        self.img_sub_lbl.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: 12px; background: transparent; border: none;"
        )
        img_text_col.addWidget(self.img_name_lbl)
        img_text_col.addWidget(self.img_sub_lbl)
        img_card_layout.addLayout(img_text_col, 1)

        self.change_img_btn = QPushButton("Chọn ảnh")
        self.change_img_btn.setCursor(Qt.PointingHandCursor)
        self.change_img_btn.setFixedHeight(32)
        self.change_img_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: white;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_STRONG};
                border-radius: 6px;
                font-size: 12px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{ background-color: #F3F4F6; }}
            """
        )
        self.change_img_btn.clicked.connect(self._select_watermark_image)
        img_card_layout.addWidget(self.change_img_btn)

        image_config_layout.addWidget(self.img_card)

        # Scale Control (Tách nằm riêng ngoài khung)
        scale_lbl = QLabel("Kích thước Logo (Scale)")
        scale_lbl.setStyleSheet(_LABEL_STYLE)
        image_config_layout.addWidget(scale_lbl)

        scale_row = QHBoxLayout()
        scale_row.setSpacing(10)
        self.scale_slider = QSlider(Qt.Horizontal)
        self.scale_slider.setRange(10, 200)
        self.scale_slider.setValue(75)
        self.scale_slider.setStyleSheet(self._slider_qss())

        self.scale_spin = QSpinBox()
        self.scale_spin.setRange(10, 200)
        self.scale_spin.setValue(75)
        self.scale_spin.setSuffix("%")
        self.scale_spin.setFixedHeight(CONTROL_HEIGHT)
        self.scale_spin.setFixedWidth(70)
        self.scale_spin.setAlignment(Qt.AlignCenter)
        self.scale_spin.setStyleSheet(self._spinbox_qss())

        self.scale_slider.valueChanged.connect(self.scale_spin.setValue)
        self.scale_spin.valueChanged.connect(self.scale_slider.setValue)
        self.scale_spin.valueChanged.connect(self._sync_preview)

        scale_row.addWidget(self.scale_slider, 1)
        scale_row.addWidget(self.scale_spin)
        image_config_layout.addLayout(scale_row)

        self.config_stack.addWidget(image_config_widget)
        config_layout.addWidget(self.config_stack)

        # === THÔNG SỐ CHUNG (Opacity, Angle, Layer) ===
        # Opacity
        opacity_lbl = QLabel("Opacity")
        opacity_lbl.setStyleSheet(_LABEL_STYLE)
        config_layout.addWidget(opacity_lbl)

        opacity_row = QHBoxLayout()
        opacity_row.setSpacing(10)
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(5, 100)
        self.opacity_slider.setValue(50)
        self.opacity_slider.setStyleSheet(self._slider_qss())

        self.opacity_spin = QSpinBox()
        self.opacity_spin.setRange(5, 100)
        self.opacity_spin.setValue(50)
        self.opacity_spin.setSuffix("%")
        self.opacity_spin.setFixedHeight(CONTROL_HEIGHT)
        self.opacity_spin.setFixedWidth(70)
        self.opacity_spin.setAlignment(Qt.AlignCenter)
        self.opacity_spin.setStyleSheet(self._spinbox_qss())

        self.opacity_slider.valueChanged.connect(self.opacity_spin.setValue)
        self.opacity_spin.valueChanged.connect(self.opacity_slider.setValue)
        self.opacity_spin.valueChanged.connect(self._sync_preview)

        opacity_row.addWidget(self.opacity_slider, 1)
        opacity_row.addWidget(self.opacity_spin)
        config_layout.addLayout(opacity_row)

        # Rotation Angle
        angle_lbl = QLabel("Góc xoay (Rotation angle)")
        angle_lbl.setStyleSheet(_LABEL_STYLE)
        config_layout.addWidget(angle_lbl)

        angle_row = QHBoxLayout()
        angle_row.setSpacing(10)
        self.angle_slider = QSlider(Qt.Horizontal)
        self.angle_slider.setRange(0, 360)
        self.angle_slider.setValue(45)
        self.angle_slider.setStyleSheet(self._slider_qss())

        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(0, 360)
        self.angle_spin.setValue(45)
        self.angle_spin.setSuffix("°")
        self.angle_spin.setFixedHeight(CONTROL_HEIGHT)
        self.angle_spin.setFixedWidth(70)
        self.angle_spin.setAlignment(Qt.AlignCenter)
        self.angle_spin.setStyleSheet(self._spinbox_qss())

        self.angle_slider.valueChanged.connect(self.angle_spin.setValue)
        self.angle_spin.valueChanged.connect(self.angle_slider.setValue)
        self.angle_spin.valueChanged.connect(self._sync_preview)

        angle_row.addWidget(self.angle_slider, 1)
        angle_row.addWidget(self.angle_spin)
        config_layout.addLayout(angle_row)

        # Layer
        layer_lbl = QLabel("Layer")
        layer_lbl.setStyleSheet(_LABEL_STYLE)
        config_layout.addWidget(layer_lbl)

        self.layer_segmented = _SegmentedControl(["Over Content", "Under Content"])
        self.layer_segmented.selection_changed.connect(self._sync_preview)
        config_layout.addWidget(self.layer_segmented)

        config_card_scroll = QScrollArea()
        config_card_scroll.setWidgetResizable(True)
        config_card_scroll.setFrameShape(QFrame.NoFrame)
        config_card_scroll.setStyleSheet(f"background: transparent; {_SCROLLBAR_QSS}")
        config_card_scroll.setWidget(config_card)
        column_a.addWidget(config_card_scroll, 1)

        # --- A3: Hàng nút bấm hành động cuối màn hình ---
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

        self.apply_button = QPushButton(" Chèn Watermark")
        self.apply_button.setIcon(qta.icon("mdi6.watermark", color="white"))
        self.apply_button.setCursor(Qt.PointingHandCursor)
        self.apply_button.setFixedHeight(CONTROL_HEIGHT)
        self.apply_button.setMinimumWidth(160)
        self.apply_button.setStyleSheet(
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
        self.apply_button.clicked.connect(self._on_apply_clicked)
        bottom_row.addWidget(self.apply_button)

        bottom_row.addStretch()
        column_a.addLayout(bottom_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet("font-size: 12px;")
        self.result_label.hide()
        column_a.addWidget(self.result_label)

        # ================= CỘT B (60%) — Preview =================
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

        body_row.addWidget(self.preview_scroll_b, 1)

        preview_card_layout.addLayout(body_row, 1)
        column_b.addWidget(preview_card, 1)

        column_a_widget = QWidget()
        column_a_widget.setLayout(column_a)
        column_b_widget = QWidget()
        column_b_widget.setLayout(column_b)

        root_layout.addWidget(column_a_widget, 40)
        root_layout.addWidget(column_b_widget, 60)

        # Load file mặc định
        self._on_file_selected("Tai lieu 02.pdf")

    # ------------------------------------------------------------------
    # QSS Helpers
    # ------------------------------------------------------------------
    def _slider_qss(self) -> str:
        return f"""
            QSlider::groove:horizontal {{
                height: 6px;
                background: #E2E8F0;
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {COLOR_ACCENT};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: white;
                border: 2px solid {COLOR_ACCENT};
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
        """

    def _spinbox_qss(self) -> str:
        # Bỏ hoàn toàn 2 nút mũi tên tăng giảm (width: 0px), hiển thị số căn giữa màu đen rõ ràng
        return f"""
            QSpinBox {{
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
                padding: 0px;
                font-size: 13px;
                font-weight: 700;
                color: {COLOR_TEXT_PRIMARY};
                background-color: white;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{
                width: 0px;
                border: none;
                background: transparent;
            }}
        """

    def _update_color_btn_style(self) -> None:
        self.color_btn.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {self._selected_color.name()};
                border: 1.5px solid {COLOR_BORDER_STRONG};
                border-radius: {CORNER_RADIUS}px;
            }}
            """
        )

    # ------------------------------------------------------------------
    # Xử lý sự kiện điều khiển
    # ------------------------------------------------------------------
    def _on_type_changed(self, index: int) -> None:
        self.config_stack.setCurrentIndex(index)
        if index == 0:  # Text
            self.angle_slider.setValue(45)
            self.opacity_slider.setValue(50)
            self.apply_button.setText(" Chèn Watermark")
        else:  # Image
            self.angle_slider.setValue(0)
            self.opacity_slider.setValue(30)
            self.apply_button.setText(" Chèn Watermark Ảnh")
        self._sync_preview()

    def _open_color_dialog(self) -> None:
        dialog = QColorDialog(self._selected_color, self)
        dialog.setWindowTitle("Chọn màu Watermark")
        # Ép stylesheet cho QColorDialog để toàn bộ màu chữ hiển thị rõ màu đen
        dialog.setStyleSheet(
            """
            QColorDialog {
                background-color: white;
            }
            QColorDialog QLabel, QColorDialog QSpinBox, QColorDialog QLineEdit, QColorDialog QPushButton {
                color: #111827 !important;
            }
            QColorDialog QPushButton {
                background-color: #F3F4F6;
                border: 1px solid #D1D5DB;
                border-radius: 6px;
                padding: 4px 12px;
                min-width: 60px;
            }
            QColorDialog QPushButton:hover {
                background-color: #E5E7EB;
            }
            """
        )
        if dialog.exec():
            color = dialog.selectedColor()
            if color.isValid():
                self._selected_color = color
                self._update_color_btn_style()
                self._sync_preview()

    def _select_watermark_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Chọn ảnh Watermark", "", "Image Files (*.png *.jpg *.jpeg)"
        )
        if path:
            self._watermark_image_path = path
            name = path.replace("\\", "/").split("/")[-1]
            self.img_name_lbl.setText(name)
            self.img_sub_lbl.setText("Đã chọn ảnh")
            self.change_img_btn.setText("Đổi ảnh")
            self._sync_preview()

    def _on_file_selected(self, path: str) -> None:
        self._current_file_path = path
        name = path.replace("\\", "/").split("/")[-1]
        mock_pages = 4
        self._load_preview(name, mock_pages)
        self._hide_result()

    def _on_clear_clicked(self) -> None:
        self._current_file_path = None
        self.text_input.setText("CONFIDENTIAL")
        self.font_combo.setCurrentText("36 pt")
        self._selected_color = QColor("#B91C1C")
        self._update_color_btn_style()

        self._watermark_image_path = None
        self.img_name_lbl.setText("Tải ảnh làm watermark (PNG, JPG)")
        self.img_sub_lbl.setText("Chưa chọn file ảnh")
        self.change_img_btn.setText("Chọn ảnh")

        self.scale_slider.setValue(75)
        self.opacity_slider.setValue(50)
        self.angle_slider.setValue(45)
        self.type_segmented.set_current_index(0)
        self.layer_segmented.set_current_index(0)

        self._show_empty_preview()
        self._hide_result()

    def _on_apply_clicked(self) -> None:
        if not self._current_file_path:
            self._show_error("Vui lòng chọn file PDF trước khi thực hiện.")
            return

        wm_type = "Text" if self.type_segmented.current_index() == 0 else "Image"
        if wm_type == "Image" and not self._watermark_image_path:
            self._show_error("Vui lòng chọn file ảnh làm Watermark.")
            return

        self._show_success(
            f"[Demo giao diện] Đã chèn Watermark ({wm_type}) vào file thành công!"
        )

    # ------------------------------------------------------------------
    # Xử lý Preview (Cột B)
    # ------------------------------------------------------------------
    def _sync_preview(self) -> None:
        wm_type = "Text" if self.type_segmented.current_index() == 0 else "Image"
        try:
            font_size = int(self.font_combo.currentText().replace("pt", "").strip())
        except ValueError:
            font_size = 36

        layer = "Over Content" if self.layer_segmented.current_index() == 0 else "Under Content"

        for page in self._preview_pages.values():
            page.update_watermark_config(
                wm_type=wm_type,
                text=self.text_input.text(),
                font_size=font_size,
                color=self._selected_color,
                image_path=self._watermark_image_path,
                scale=self.scale_spin.value(),
                opacity=self.opacity_spin.value(),
                rotation=self.angle_spin.value(),
                layer=layer,
            )

    def _load_preview(self, name: str, pages: int) -> None:
        self._current_total_pages = pages
        self._current_page = 1 if pages > 0 else 0
        self.preview_title.setText(f"Xem trước: {name}")
        self._build_preview_thumbs(pages)
        self._build_preview_pages(pages)
        self._refresh_page_view()
        self._sync_preview()

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
            frame = _WatermarkPreviewPage(page_number)
            height = round(width * frame.aspect_ratio)
            frame.setFixedSize(width, height)
            self.preview_layout.addWidget(frame, alignment=Qt.AlignHCenter)
            self._preview_pages[page_number] = frame

        self._update_zoom_buttons_state()

    def _on_thumb_clicked(self, page_number: int) -> None:
        self._current_page = page_number
        self._refresh_page_view()

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
        if not self._initial_width_applied and self._preview_pages:
            self._initial_width_applied = True
            self._current_preview_width = None
            self._apply_preview_zoom()

    # ------------------------------------------------------------------
    # Thông báo Trạng thái
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