"""
Vishipel PDF Tools — src/undo_logic.py

Undo RIÊNG cho tính năng Chèn file (Insert) — KHÔNG dùng chung với `undo_manager.py`
(class `UndoManager` ở đó dành cho Edit — sắp xếp/xoay/xóa trang, xem
04_kien_truc_module_va_flow.md mục 2). Tách file riêng vì 2 lý do:

1. `undo_manager.py` tại thời điểm viết file này chỉ mới có đặc tả chữ ký hàm
   (register/undo/redo/clear), CHƯA có code thật để kiểm tra — tái dùng mà đoán
   sai hành vi bên trong rất dễ gây lỗi khó phát hiện.
2. Bản chất 2 loại Undo khác nhau: Edit gộp nhiều thao tác (Move/Xoay/Xóa) áp dụng
   1 lần lúc bấm "Áp dụng" (chưa ghi gì vào tài liệu cho tới lúc đó); còn Chèn file
   ghi thẳng từng lượt vào `InsertSession.working_document` ngay khi bấm "Chèn" —
   nên Undo ở đây chỉ cần biết "vừa chèn bao nhiêu trang, bắt đầu ở đâu" rồi gọi
   thẳng `fitz.Document.delete_page()` để lùi lại, không cần áp dụng lại toàn bộ
   một chuỗi thao tác như Edit.

Nếu sau này có `undo_manager.py` thật và muốn hợp nhất, class này có thể thay thế
bằng cách gọi `undo_manager.register("insert", {...})` — nhưng việc đó cần xác nhận
lại với đại ca trước vì đụng tới file dùng chung cho Edit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import fitz  # PyMuPDF


@dataclass
class InsertUndoEntry:
    """1 lượt Chèn đã thực hiện — đủ thông tin để hoàn tác đúng lượt đó."""
    start_index: int   # vị trí (0-based) của trang ĐẦU TIÊN được chèn vào working_document
    page_count: int     # số trang đã chèn trong lượt này (hiện tại Insert luôn chèn
                         # đúng 1 trang mỗi lượt — giữ trường này tổng quát để không phải
                         # đổi kiến trúc nếu sau này hỗ trợ chèn nhiều trang liên tục 1 lượt)


class InsertUndoManager:
    """Stack LIFO các lượt Chèn — dùng riêng bởi `insert_widget.py`.

    KHÔNG đăng ký/tương tác gì với `undo_manager.py` của Edit — 2 lịch sử hoàn toàn
    độc lập, đúng theo phạm vi tính năng Chèn file."""

    def __init__(self) -> None:
        self._stack: List[InsertUndoEntry] = []

    def register(self, start_index: int, page_count: int = 1) -> None:
        """Gọi NGAY SAU khi `InsertSession.perform_insert()` chạy thành công,
        với đúng vị trí (0-based) trang vừa được chèn vào."""
        self._stack.append(InsertUndoEntry(start_index=start_index, page_count=page_count))

    def can_undo(self) -> bool:
        return bool(self._stack)

    def undo(self, working_document: fitz.Document) -> bool:
        """Xoá đúng (các) trang vừa chèn ở lượt gần nhất khỏi `working_document`
        (đối tượng `InsertSession.working_document` — vẫn đang ở trong bộ nhớ, chưa
        ghi ra đĩa). Trả về True nếu có 1 lượt được hoàn tác, False nếu không còn gì
        trong lịch sử để hoàn tác (widget nên vô hiệu hoá mục Undo khi `can_undo()`
        trả về False thay vì dựa vào giá trị trả về này)."""
        if not self._stack:
            return False
        entry = self._stack.pop()
        for _ in range(entry.page_count):
            working_document.delete_page(entry.start_index)
        return True

    def clear(self) -> None:
        """Xoá toàn bộ lịch sử Undo — gọi khi tạo lại `InsertSession` (đổi File A/B)
        hoặc khi bấm Clear, vì lịch sử cũ không còn khớp với working_document mới."""
        self._stack.clear()