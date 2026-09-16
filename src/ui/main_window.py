"""
Cửa sổ chính của Vishipel PDF Tools — ghép Sidebar (trái) và khung nội dung
(phải), dùng SlidingStackedWidget để chuyển đổi giữa màn hình chào và 5 trang tính
năng với hiệu ứng trượt từ trên xuống.
"""
from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout

from src.ui.sidebar import Sidebar, FEATURES
from src.ui.placeholder_widget import PlaceholderFeatureWidget
from src.ui.welcome_screen import WelcomeScreen
from src.ui.vishipel_theme import COLOR_CONTENT_BG

from src.ui.animation_helper import SlidingStackedWidget  

from src.ui.tools.split_widget import SplitFeatureWidget
from src.ui.tools.merge_widget import MergeFeatureWidget
from src.ui.tools.edit_widget import EditFeatureWidget


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