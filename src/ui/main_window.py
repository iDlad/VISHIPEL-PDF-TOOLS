"""
Cửa sổ chính của Vishipel PDF Tools — ghép Sidebar (trái) và khung nội dung
(phải), dùng QStackedWidget để chuyển đổi giữa màn hình chào và 5 trang tính
năng. Mở app lên hiển thị màn hình chào (welcome_screen.py) trước, chưa có
mục nào ở sidebar được chọn sẵn — người dùng bấm 1 mục ở sidebar mới chuyển
sang trang tính năng tương ứng. Bấm nút Home ở cuối sidebar sẽ quay lại màn
hình chào này bất kỳ lúc nào.
"""
from __future__ import annotations

from typing import Dict

from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QStackedWidget

from src.ui.sidebar import Sidebar, FEATURES
from src.ui.placeholder_widget import PlaceholderFeatureWidget
from src.ui.welcome_screen import WelcomeScreen
from src.ui.vishipel_theme import COLOR_CONTENT_BG
from src.ui.tools.split_widget import SplitFeatureWidget


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Vishipel PDF Tools")
        self.resize(1300, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        root_layout = QHBoxLayout(central_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # --- Sidebar (trái) ---
        self.sidebar = Sidebar()
        self.sidebar.feature_selected.connect(self._on_feature_selected)
        self.sidebar.home_requested.connect(self._on_home_requested)
        self.sidebar.logout_requested.connect(self.close)
        root_layout.addWidget(self.sidebar)

        # --- Khung nội dung (phải) ---
        self.content_stack = QStackedWidget()
        self.content_stack.setStyleSheet(f"background-color: {COLOR_CONTENT_BG};")
        root_layout.addWidget(self.content_stack, stretch=1)

        # Trang màn hình chào — hiển thị mặc định khi mở app, trước khi người
        # dùng chọn bất kỳ tính năng nào ở sidebar.
        self.welcome_page = WelcomeScreen()
        self._welcome_index = self.content_stack.addWidget(self.welcome_page)

        # Các trang cho 5 tính năng, theo đúng thứ tự trong sidebar.py.
        # "split" đã có giao diện thật (đang ở giai đoạn UI thuần, xem
        # split_widget.py); các tính năng còn lại vẫn dùng placeholder cho
        # tới khi làm tới lượt (thứ tự Gộp → Chèn → Tách → Edit theo
        # 05_lo_trinh_phat_trien.md — "split" được làm sớm ở đây chỉ để
        # đại ca duyệt giao diện, chưa đúng thứ tự nối logic thật).
        self._feature_pages: Dict[str, int] = {}
        for key, label, _icon in FEATURES:
            if key == "split":
                page = SplitFeatureWidget()
            else:
                page = PlaceholderFeatureWidget(label)
            index = self.content_stack.addWidget(page)
            self._feature_pages[key] = index

        # Mặc định hiển thị màn hình chào — sidebar chưa chọn mục nào (xem sidebar.py).
        self.content_stack.setCurrentIndex(self._welcome_index)

    def _on_feature_selected(self, feature_key: str) -> None:
        index = self._feature_pages.get(feature_key)
        if index is not None:
            self.content_stack.setCurrentIndex(index)

    def _on_home_requested(self) -> None:
        """Bấm nút Home ở sidebar: quay khung nội dung về màn hình chào."""
        self.content_stack.setCurrentIndex(self._welcome_index)