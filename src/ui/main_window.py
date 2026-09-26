""" /src/ui/main_window.py """

from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QMessageBox

from src.ui.sidebar import Sidebar, FEATURES
from src.ui.placeholder_widget import PlaceholderFeatureWidget
from src.ui.welcome_screen import WelcomeScreen
from src.ui.vishipel_theme import (
    COLOR_CONTENT_BG,
    COLOR_TEXT_PRIMARY,
    COLOR_BORDER_STRONG,
    COLOR_ACCENT,
    COLOR_ERROR,
)

from src.ui.animation_helper import SlidingStackedWidget  

from src.ui.tools.split_widget import SplitFeatureWidget
from src.ui.tools.merge_widget import MergeFeatureWidget
from src.ui.tools.edit_widget import EditFeatureWidget
from src.ui.tools.insert_widget import InsertFeatureWidget
from src.ui.tools.watermark_widget import WatermarkFeatureWidget
from src.ui.tools.protect_feature_widget import ProtectFeatureWidget
from src.ui.tools.rename_widget import RenameFeatureWidget

from src.logger import clear_log, log_error




class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Vishipel PDF Tools")
        self.resize(1400, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Sidebar (trái) - giữ nguyên, không ảnh hưởng hiệu ứng ---
        self.sidebar = Sidebar()
        self.sidebar.feature_selected.connect(self._on_feature_selected)
        self.sidebar.home_requested.connect(self._on_home_requested)
        self.sidebar.logout_requested.connect(self.close)
        self.sidebar.clear_log_requested.connect(self._on_clear_log_requested)
        root_layout.addWidget(self.sidebar)

        # --- Khung nội dung (phải) - Sử dụng SlidingStackedWidget ---
        self.content_stack = SlidingStackedWidget()
        self.content_stack.setStyleSheet(f"background-color: {COLOR_CONTENT_BG};")
        root_layout.addWidget(self.content_stack, stretch=1)

        # Trang màn hình chào
        self.welcome_page = WelcomeScreen()
        self._welcome_index = self.content_stack.addWidget(self.welcome_page)

        # Các trang tính năng
        self._feature_pages: Dict[str, int] = {}
        for key, label, _icon in FEATURES:
            if key == "split":
                page = SplitFeatureWidget()
            elif key == "merge":
                page = MergeFeatureWidget()
            elif key == "edit":
                page = EditFeatureWidget()
            elif key == "insert":
                page = InsertFeatureWidget()
            elif key == "watermark":
                page = WatermarkFeatureWidget()
            elif key == "protect":
                page = ProtectFeatureWidget()
            elif key == "rename":
                page = RenameFeatureWidget()    
            else:
                page = PlaceholderFeatureWidget(label)
            index = self.content_stack.addWidget(page)
            self._feature_pages[key] = index

        # Mặc định hiển thị màn hình chào
        self.content_stack.setCurrentIndex(self._welcome_index)

    def _on_feature_selected(self, feature_key: str) -> None:
        index = self._feature_pages.get(feature_key)
        if index is not None:
            # Gọi hiệu ứng trượt từ trên xuống thay vì setCurrentIndex trực tiếp
            self.content_stack.slide_to_index(index)

    def _on_home_requested(self) -> None:
        """Bấm nút Home ở sidebar: trượt mượt về màn hình chào."""
        self.content_stack.slide_to_index(self._welcome_index)

    def _on_clear_log_requested(self) -> None:

        confirm_box = self._styled_message_box(
            icon=QMessageBox.Warning,
            title="Xóa log ứng dụng",
            text="Xóa toàn bộ log ứng dụng (bao gồm các file log cũ đã xoay vòng)?\n"
                 "Không thể hoàn tác.",
            buttons=QMessageBox.Yes | QMessageBox.No,
            default_button=QMessageBox.No,
        )
        if confirm_box.exec() != QMessageBox.Yes:
            return

        try:
            clear_log()
        except Exception as exc:  # noqa: BLE001 - lỗi kỹ thuật hiếm gặp, không để crash app
            log_error("Lỗi khi xóa log thủ công từ sidebar.", exc)
            error_box = self._styled_message_box(
                icon=QMessageBox.Critical,
                title="Không thể xóa log",
                text="Đã xảy ra lỗi khi xóa log. Chi tiết đã được ghi vào app.log.",
                buttons=QMessageBox.Ok,
            )
            error_box.exec()
            return

        success_box = self._styled_message_box(
            icon=QMessageBox.Information,
            title="Đã xóa log",
            text="Đã xóa toàn bộ log ứng dụng.",
            buttons=QMessageBox.Ok,
        )
        success_box.exec()

    def _styled_message_box(
        self,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButton,
        default_button: QMessageBox.StandardButton | None = None,
    ) -> QMessageBox:

        box = QMessageBox(self)
        box.setIcon(icon)
        box.setWindowTitle(title)
        box.setText(text)
        box.setStandardButtons(buttons)
        if default_button is not None:
            box.setDefaultButton(default_button)
        box.setStyleSheet(f"""
            QMessageBox {{
                background-color: #FFFFFF;
            }}
            QMessageBox QLabel {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 14px;
            }}
            QPushButton {{
                background-color: #FFFFFF;
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER_STRONG};
                border-radius: 8px;
                padding: 6px 16px;
                min-width: 72px;
            }}
            QPushButton:hover {{
                background-color: #F3F4F6;
            }}
            QPushButton:default {{
                background-color: {COLOR_ACCENT};
                color: #FFFFFF;
                border: 1px solid {COLOR_ACCENT};
            }}
            QPushButton:default:hover {{
                background-color: #E07F00;
            }}
        """)
        if icon == QMessageBox.Critical:
            box.setStyleSheet(box.styleSheet() + f"""
                QMessageBox QLabel {{ color: {COLOR_ERROR}; }}
            """)
        return box