"""
Vishipel PDF Tools — src/undo_manager.py

Undo/Redo RIÊNG cho tính năng Edit (Move / Xoay / Xóa trang) — độc lập hoàn toàn với
`src/undo_logic.py` (`InsertUndoManager`, dành riêng cho Chèn file). 2 file KHÔNG import/
gọi gì tới nhau.

LÝ DO không tái dùng `InsertUndoManager` (đã kiểm tra kỹ trước khi viết file này):
1. `InsertUndoManager` chỉ biết đúng 1 dạng thao tác: "vừa chèn N trang bắt đầu từ vị
   trí X" → hoàn tác bằng cách gọi thẳng `fitz.Document.delete_page()` N lần. Đây là
   Undo 1 CHIỀU (không có Redo), vì Chèn file không cần Redo theo đặc tả.
2. Edit có 3 loại thao tác bản chất khác nhau — Move (đổi thứ tự), Xoay (đổi góc),
   Xóa (LOẠI HẲN phần tử khỏi danh sách hiển thị — mất thông tin, không thể suy ngược
   an toàn chỉ từ 1 diff nhỏ). Không thể ép 3 loại này vào model "xóa N trang từ vị
   trí X" của Insert.
3. Đặc tả Edit (02_dac_ta_tinh_nang.md mục 3) yêu cầu rõ cả Undo VÀ Redo.

CÁCH TRIỂN KHAI: dựa trên SNAPSHOT toàn bộ trạng thái của `PageEditSession` (order,
rotations, marked — xem `PageEditSession.snapshot()`/`restore()` trong pdf_core.py mục
5), không lưu diff riêng từng loại thao tác. Lý do chọn snapshot thay vì diff: dữ liệu
quản lý bởi PageEditSession rất nhỏ gọn (1 list int, 1 dict int→int, 1 set int) nên chi
phí copy toàn bộ không đáng kể, đổi lại loại bỏ hẳn rủi ro tính sai chiều ngược cho 3
loại thao tác khác nhau — đặc biệt thao tác Xóa vốn dĩ không thể suy ngược an toàn nếu
chỉ lưu diff.

Giữ đúng tinh thần interface đã phác ở 04_kien_truc_module_va_flow.md mục 2
(register/undo/redo/clear) — chỉ khác PHẦN TRIỂN KHAI bên trong và có mở rộng thêm
tham số cần thiết cho cơ chế 2 chiều (Undo/Redo) vì tại thời điểm phác thảo đó, class
này chưa có code thật.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


class UndoManager:
    """Stack Undo/Redo dùng riêng bởi `edit_widget.py`.

    Mỗi lần 1 thao tác Move/Xoay/Xóa HOÀN TẤT, widget gọi `register(action_type,
    before_snapshot, after_snapshot)` — trong đó `before`/`after` là kết quả của
    `PageEditSession.snapshot()` chụp NGAY TRƯỚC và NGAY SAU khi thao tác đó chạy.
    `undo()`/`redo()` trả về đúng snapshot cần áp lại (qua `PageEditSession.restore()`),
    widget tự chịu trách nhiệm vẽ lại UI theo snapshot đó."""

    def __init__(self) -> None:
        self._undo_stack: List[Dict[str, Any]] = []
        self._redo_stack: List[Dict[str, Any]] = []

    @staticmethod
    def _clone_snapshot(snapshot: dict) -> dict:
        # Copy nông đủ dùng: value trong "order" là int, "rotations" là dict int->int,
        # "marked" là set int — toàn bộ đều immutable ở cấp phần tử nên copy 1 lớp là an toàn.
        return {
            "order": list(snapshot["order"]),
            "rotations": dict(snapshot["rotations"]),
            "marked": set(snapshot["marked"]),
        }

    def register(self, action_type: str, before_snapshot: dict, after_snapshot: dict) -> None:
        """Gọi ngay sau khi 1 thao tác (Move/Xoay/Xóa) hoàn tất trên PageEditSession.

        - before_snapshot: PageEditSession.snapshot() chụp NGAY TRƯỚC khi thao tác chạy
          (dùng để Undo — trả trạng thái về đúng lúc này).
        - after_snapshot: PageEditSession.snapshot() chụp NGAY SAU khi thao tác chạy
          (dùng để Redo — áp lại đúng kết quả thao tác này).
        `action_type` chỉ mang tính mô tả (hiển thị thông báo/log), không ảnh hưởng
        logic Undo/Redo bên trong.

        Thực hiện 1 thao tác MỚI sau khi đã Undo sẽ xoá sạch mọi khả năng Redo cũ —
        đúng hành vi chuẩn của mọi trình soạn thảo (nhánh Redo cũ không còn hợp lệ vì
        trạng thái hiện tại đã rẽ sang 1 nhánh khác)."""
        self._undo_stack.append({
            "action_type": action_type,
            "before": self._clone_snapshot(before_snapshot),
            "after": self._clone_snapshot(after_snapshot),
        })
        self._redo_stack.clear()

    def undo(self) -> Optional[dict]:
        """Lùi 1 bước — trả về snapshot ("before" của thao tác gần nhất) để widget áp
        lại vào PageEditSession + vẽ lại UI. Trả về None nếu không còn gì để Undo."""
        if not self._undo_stack:
            return None
        entry = self._undo_stack.pop()
        self._redo_stack.append(entry)
        return self._clone_snapshot(entry["before"])

    def redo(self) -> Optional[dict]:
        """Tiến 1 bước — trả về snapshot ("after" của thao tác vừa Undo) để áp lại.
        Trả về None nếu không còn gì để Redo."""
        if not self._redo_stack:
            return None
        entry = self._redo_stack.pop()
        self._undo_stack.append(entry)
        return self._clone_snapshot(entry["after"])

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def clear(self) -> None:
        """Xoá toàn bộ lịch sử Undo/Redo — gọi khi mở file mới, bấm Clear, hoặc sau khi
        Lưu file (Áp dụng) thành công."""
        self._undo_stack.clear()
        self._redo_stack.clear()