"""
SlidingStackedWidget
--------------------
Helper xử lý hiệu ứng chuyển trang cho QStackedWidget.

Đặc điểm:
- Hiệu ứng trượt dọc từ trên xuống.
- Animation nhanh, phù hợp desktop UI.
- Có thể ngắt animation đang chạy ngay lập tức.
- Hỗ trợ click liên tục: A -> B -> C -> D...
- Không phụ thuộc vào currentIndex() trong lúc animation.
- Quản lý rõ ràng trạng thái trang hiện tại và trang đích.
"""

from __future__ import annotations

from PySide6.QtCore import (
    QEasingCurve,
    QParallelAnimationGroup,
    QRect,
    QPropertyAnimation,
)
from PySide6.QtWidgets import QStackedWidget, QWidget


class SlidingStackedWidget(QStackedWidget):
    """
    QStackedWidget với hiệu ứng slide dọc.

    Luồng chuyển trang:

        Current
           ↓
        Target

    Khi người dùng click trang mới trong lúc animation đang chạy,
    animation hiện tại sẽ được dừng ngay lập tức và chuyển sang target mới.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        duration: int = 500,
    ) -> None:
        super().__init__(parent)

        # ---------------------------------------------------------
        # Animation configuration
        # ---------------------------------------------------------
        self.animation_duration = duration

        self._easing_curve = QEasingCurve.OutCubic

        # ---------------------------------------------------------
        # Animation state
        # ---------------------------------------------------------
        self._anim_group: QParallelAnimationGroup | None = None

        # Widget đang thực sự được xem là trang hiện tại.
        self._current_widget: QWidget | None = None

        # Widget đang được chuyển tới.
        self._target_widget: QWidget | None = None

        # Index mục tiêu.
        self._target_index: int | None = None

        # Hai widget đang tham gia animation.
        self._animating_from: QWidget | None = None
        self._animating_to: QWidget | None = None

    # =============================================================
    # Public API
    # =============================================================

    def slide_to_index(self, new_index: int) -> None:
        """
        Chuyển sang trang new_index bằng hiệu ứng slide.

        Có thể gọi liên tục:

            slide_to_index(1)
            slide_to_index(2)
            slide_to_index(3)

        Animation hiện tại sẽ được dừng ngay và chuyển sang target mới.
        """

        # ---------------------------------------------------------
        # Validate index
        # ---------------------------------------------------------
        if not 0 <= new_index < self.count():
            return

        # ---------------------------------------------------------
        # Khởi tạo current widget nếu chưa có
        # ---------------------------------------------------------
        if self._current_widget is None:
            self._current_widget = self.currentWidget()

        current_widget = self._current_widget

        if current_widget is None:
            self.setCurrentIndex(new_index)
            self._current_widget = self.currentWidget()
            return

        target_widget = self.widget(new_index)

        # ---------------------------------------------------------
        # Nếu click đúng trang đang hiển thị
        # ---------------------------------------------------------
        if target_widget is current_widget and self._anim_group is None:
            return

        # ---------------------------------------------------------
        # Nếu đang animation và click lại đúng target hiện tại
        # ---------------------------------------------------------
        if (
            self._anim_group is not None
            and self._anim_group.state() == QParallelAnimationGroup.Running
            and target_widget is self._target_widget
        ):
            return

        # ---------------------------------------------------------
        # Dừng animation hiện tại nếu có
        # ---------------------------------------------------------
        self._stop_current_animation()

        # ---------------------------------------------------------
        # Cập nhật target
        # ---------------------------------------------------------
        self._target_index = new_index
        self._target_widget = target_widget

        self._animating_from = current_widget
        self._animating_to = target_widget

        # ---------------------------------------------------------
        # Kích thước vùng hiển thị
        # ---------------------------------------------------------
        width = self.width()
        height = self.height()

        # Nếu widget chưa có kích thước hợp lệ,
        # chuyển trang trực tiếp.
        if width <= 0 or height <= 0:
            self._finish_without_animation(new_index)
            return

        # ---------------------------------------------------------
        # Đảm bảo target nằm trong cùng vùng layout
        # ---------------------------------------------------------
        start_rect = QRect(0, -height, width, height)
        end_rect = QRect(0, 0, width, height)

        current_rect = QRect(0, 0, width, height)
        current_end_rect = QRect(0, height, width, height)

        # ---------------------------------------------------------
        # Chuẩn bị target
        # ---------------------------------------------------------
        target_widget.setGeometry(start_rect)
        target_widget.show()
        target_widget.raise_()

        # ---------------------------------------------------------
        # Animation current widget
        # ---------------------------------------------------------
        anim_current = QPropertyAnimation(
            current_widget,
            b"geometry",
            self,
        )

        anim_current.setDuration(self.animation_duration)
        anim_current.setStartValue(current_widget.geometry())
        anim_current.setEndValue(current_end_rect)
        anim_current.setEasingCurve(self._easing_curve)

        # ---------------------------------------------------------
        # Animation target widget
        # ---------------------------------------------------------
        anim_target = QPropertyAnimation(
            target_widget,
            b"geometry",
            self,
        )

        anim_target.setDuration(self.animation_duration)
        anim_target.setStartValue(start_rect)
        anim_target.setEndValue(end_rect)
        anim_target.setEasingCurve(self._easing_curve)

        # ---------------------------------------------------------
        # Chạy song song
        # ---------------------------------------------------------
        self._anim_group = QParallelAnimationGroup(self)

        self._anim_group.addAnimation(anim_current)
        self._anim_group.addAnimation(anim_target)

        self._anim_group.finished.connect(self._on_animation_finished)

        self._anim_group.start()

    # =============================================================
    # Animation control
    # =============================================================

    def _stop_current_animation(self) -> None:
        """
        Dừng animation hiện tại ngay lập tức.

        Sau khi dừng, widget đang được xem là current sẽ được
        đưa về trạng thái chuẩn trước khi bắt đầu animation mới.
        """

        if self._anim_group is None:
            return

        if self._anim_group.state() == QParallelAnimationGroup.Running:
            self._anim_group.stop()

        # ---------------------------------------------------------
        # Xác định widget nào phải giữ lại
        # ---------------------------------------------------------
        current_widget = self._current_widget

        from_widget = self._animating_from
        to_widget = self._animating_to

        # ---------------------------------------------------------
        # Reset widget hiện tại
        # ---------------------------------------------------------
        if current_widget is not None:
            current_widget.setGeometry(
                0,
                0,
                self.width(),
                self.height(),
            )
            current_widget.show()
            current_widget.raise_()

        # ---------------------------------------------------------
        # Widget cũ tham gia animation nhưng không phải current
        # ---------------------------------------------------------
        if from_widget is not None and from_widget is not current_widget:
            from_widget.hide()
            from_widget.setGeometry(
                0,
                0,
                self.width(),
                self.height(),
            )

        # ---------------------------------------------------------
        # Target cũ cũng bị hủy
        # ---------------------------------------------------------
        if to_widget is not None and to_widget is not current_widget:
            to_widget.hide()
            to_widget.setGeometry(
                0,
                0,
                self.width(),
                self.height(),
            )

        # ---------------------------------------------------------
        # Xóa trạng thái animation
        # ---------------------------------------------------------
        self._anim_group.deleteLater()
        self._anim_group = None

        self._animating_from = None
        self._animating_to = None

    # =============================================================
    # Animation finished
    # =============================================================

    def _on_animation_finished(self) -> None:
        """
        Hoàn tất chuyển trang.
        """

        target_index = self._target_index
        target_widget = self._target_widget

        if target_index is None or target_widget is None:
            self._clear_animation_state()
            return

        # ---------------------------------------------------------
        # Cập nhật QStackedWidget
        # ---------------------------------------------------------
        self.setCurrentIndex(target_index)

        # ---------------------------------------------------------
        # Đưa target về trạng thái chuẩn
        # ---------------------------------------------------------
        target_widget.setGeometry(
            0,
            0,
            self.width(),
            self.height(),
        )
        target_widget.show()
        target_widget.raise_()

        # ---------------------------------------------------------
        # Widget cũ
        # ---------------------------------------------------------
        old_widget = self._current_widget

        if old_widget is not None and old_widget is not target_widget:
            old_widget.hide()
            old_widget.setGeometry(
                0,
                0,
                self.width(),
                self.height(),
            )

        # ---------------------------------------------------------
        # Cập nhật logical current
        # ---------------------------------------------------------
        self._current_widget = target_widget

        # ---------------------------------------------------------
        # Clear animation state
        # ---------------------------------------------------------
        self._clear_animation_state()

    # =============================================================
    # Direct transition
    # =============================================================

    def _finish_without_animation(self, new_index: int) -> None:
        """
        Chuyển trang trực tiếp khi không thể chạy animation.
        """

        self.setCurrentIndex(new_index)

        widget = self.currentWidget()

        if widget is not None:
            widget.setGeometry(
                0,
                0,
                self.width(),
                self.height(),
            )
            widget.show()
            widget.raise_()

        self._current_widget = widget

        self._clear_animation_state()

    # =============================================================
    # State cleanup
    # =============================================================

    def _clear_animation_state(self) -> None:
        """
        Xóa toàn bộ trạng thái animation.
        """

        self._target_index = None
        self._target_widget = None
        self._animating_from = None
        self._animating_to = None

        if self._anim_group is not None:
            self._anim_group.deleteLater()
            self._anim_group = None

    # =============================================================
    # QStackedWidget integration
    # =============================================================

    def setCurrentIndex(self, index: int) -> None:
        """
        Override để đồng bộ _current_widget khi code bên ngoài
        gọi setCurrentIndex() trực tiếp.
        """

        super().setCurrentIndex(index)

        # Không ghi đè trạng thái logical trong lúc animation.
        if self._anim_group is None:
            self._current_widget = self.currentWidget()

    def resizeEvent(self, event) -> None:
        """
        Giữ widget hiện tại đúng kích thước khi cửa sổ thay đổi.
        """

        super().resizeEvent(event)

        width = self.width()
        height = self.height()

        # Khi không animation, chỉ cần resize current widget.
        if self._anim_group is None:
            current = self.currentWidget()

            if current is not None:
                current.setGeometry(
                    0,
                    0,
                    width,
                    height,
                )

        else:
            # Trong animation không ép geometry của hai widget,
            # tránh phá animation đang chạy.
            pass

