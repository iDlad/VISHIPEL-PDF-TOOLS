"""
Vishipel PDF Tools — src/pdf_core.py

Lõi xử lý PDF bằng PyMuPDF (fitz). Toàn bộ nội dung trong file này THUẦN LOGIC,
không import PySide6, để có thể tự test độc lập bằng script trước khi gắn vào UI
(xem 04_kien_truc_module_va_flow.md, 05_lo_trinh_phat_trien.md — Giai đoạn 2).

Nguyên tắc: widget UI không bao giờ tự xử lý PDF — chỉ gọi hàm/class ở đây.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import fitz  # PyMuPDF


# =============================================================================
# 1. Exception dùng chung (Nhóm A)
# =============================================================================

class CorruptedFileError(Exception):
    """File PDF hỏng hoặc không mở được (bao gồm cả trường hợp không tìm thấy file)."""


class PasswordProtectedError(Exception):
    """File PDF có mật khẩu (needs_pass = True) — bản đầu không hỗ trợ nhập mật khẩu để mở."""


class FileLockedError(Exception):
    """Không ghi được file kết quả — thường do file đang bị khóa bởi chương trình khác."""


# =============================================================================
# 2. Class dùng chung (Nhóm A)
# =============================================================================

class PDFDocument:
    """Bọc fitz.Document — mở 1 file, validate hỏng/mật khẩu ngay lúc mở.

    Dùng như context manager để luôn đóng file đúng lúc, tránh giữ handle thừa
    gây khóa file trên Windows:

        with PDFDocument(path) as doc:
            n = doc.page_count
    """

    def __init__(self, path: str) -> None:
        self.path = path
        try:
            self._doc = fitz.open(path)
        except Exception as exc:  # bắt mọi lỗi mở file: hỏng, không tồn tại, sai định dạng...
            raise CorruptedFileError(f"Không thể mở file: {path}") from exc

        if self._doc.needs_pass:
            self._doc.close()
            raise PasswordProtectedError(f"File yêu cầu mật khẩu: {path}")

    def __enter__(self) -> "PDFDocument":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    @property
    def raw(self) -> fitz.Document:
        """Trả về fitz.Document gốc — dùng nội bộ bởi PageRenderer/PageEditSession/InsertSession."""
        return self._doc

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def get_page_size(self, page_index: int) -> Tuple[float, float]:
        rect = self._doc[page_index].rect
        return (rect.width, rect.height)


@dataclass
class PageInfo:
    """Metadata 1 trang để UI vẽ lưới thumbnail. Không có hành vi xử lý."""
    source_index: int
    width: float
    height: float
    rotation: int


def get_page_count(path: str) -> int:
    """Trả về tổng số trang của file — hàm tiện ích ngắn cho các chỗ chỉ cần mỗi số trang."""
    with PDFDocument(path) as doc:
        return doc.page_count


def list_page_infos(path: str) -> List[PageInfo]:
    """Trả về danh sách PageInfo cho toàn bộ trang — dùng để widget dựng lưới thumbnail ban đầu."""
    infos: List[PageInfo] = []
    with PDFDocument(path) as doc:
        for i in range(doc.page_count):
            page = doc.raw[i]
            rect = page.rect
            infos.append(PageInfo(source_index=i, width=rect.width, height=rect.height,
                                   rotation=page.rotation))
    return infos


class PageRenderer:
    """Render ảnh trang thành PNG bytes, có cache nội bộ để không render lại khi người
    dùng bấm qua lại nhiều lần (VD click đi click lại giữa các thumbnail)."""

    def __init__(self) -> None:
        self._cache: Dict[Tuple[str, int, int, int], bytes] = {}

    def render_thumbnail(self, path: str, page_index: int, max_width: int = 160,
                          pending_rotation: int = 0) -> bytes:
        """Ảnh nhỏ cho lưới thumbnail (Cột A)."""
        return self._render(path, page_index, max_width, pending_rotation)

    def render_page_detail(self, path: str, page_index: int, target_width: int = 760,
                            pending_rotation: int = 0) -> bytes:
        """Ảnh lớn cho khu vực Preview (Cột B)."""
        return self._render(path, page_index, target_width, pending_rotation)

    def _render(self, path: str, page_index: int, target_width: int,
                pending_rotation: int) -> bytes:
        key = (path, page_index, target_width, pending_rotation)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        with PDFDocument(path) as doc:
            page = doc.raw[page_index]
            if pending_rotation:
                # pending_rotation: góc xoay TẠM đang chỉnh trong phiên Edit, chưa ghi ra file.
                # Áp tạm vào page để render đúng preview, không ảnh hưởng file gốc trên đĩa
                # vì object doc này chỉ tồn tại trong khối "with" và không được save().
                page.set_rotation((page.rotation + pending_rotation) % 360)

            rect = page.rect
            zoom = target_width / rect.width if rect.width else 1.0
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            data = pixmap.tobytes("png")

        self._cache[key] = data
        return data

    def clear_cache(self, path: Optional[str] = None) -> None:
        """Xóa cache — gọi khi nội dung file thật sự đổi (VD sau khi InsertSession chèn xong)."""
        if path is None:
            self._cache.clear()
        else:
            self._cache = {k: v for k, v in self._cache.items() if k[0] != path}


# =============================================================================
# 3. Hàm tiện ích ghi file dùng chung nội bộ module
# =============================================================================

def _safe_save(doc: fitz.Document, output_path: str) -> None:
    """Ghi file, chuyển mọi lỗi ghi (file đang bị khóa, đường dẫn không hợp lệ, thư mục
    không tồn tại...) thành FileLockedError để widget xử lý thống nhất theo 1 luồng lỗi."""
    try:
        doc.save(output_path)
    except Exception as exc:
        raise FileLockedError(f"Không thể ghi file (có thể đang bị khóa): {output_path}") from exc


def _extract_pages_and_save(source_doc: fitz.Document, start: int, end: int,
                             output_dir: str, sequence_number: int) -> str:
    """Trích trang [start, end] (inclusive, 0-based) từ source_doc, lưu thành 1 file mới.
    Dùng chung bởi split_by_fixed_count và split_by_flags.

    Tên file: PDF_Split_<số thứ tự 2 chữ số> (VD: PDF_Split_01.pdf, PDF_Split_02.pdf...),
    đánh số theo đúng thứ tự file được tạo ra, bắt đầu từ 01."""
    new_doc = fitz.open()
    try:
        new_doc.insert_pdf(source_doc, from_page=start, to_page=end)
        output_path = os.path.join(output_dir, f"PDF_Split_{sequence_number:02d}.pdf")
        _safe_save(new_doc, output_path)
    finally:
        new_doc.close()
    return output_path


# =============================================================================
# 4. Hàm riêng theo tính năng — không có trạng thái, gọi 1 lần là xong
# =============================================================================

def split_by_fixed_count(path: str, pages_per_file: int, output_dir: str,
                          base_name: str) -> List[str]:
    """Tách file gốc thành nhiều file, mỗi file đúng `pages_per_file` trang,
    trang lẻ dồn vào file cuối cùng (VD: 10 trang, N=3 → các file 3-3-3-1 trang).

    Ghi chú: `base_name` giữ trong chữ ký hàm để không đổi kiến trúc đã chốt, nhưng
    KHÔNG dùng để đặt tên file nữa — tên file kết quả luôn theo mẫu PDF_Split_<STT>
    (xem _extract_pages_and_save)."""
    if pages_per_file < 1:
        raise ValueError("pages_per_file phải >= 1")

    output_paths: List[str] = []
    with PDFDocument(path) as doc:
        total = doc.page_count
        start = 0
        sequence_number = 1
        while start < total:
            end = min(start + pages_per_file, total) - 1
            output_paths.append(
                _extract_pages_and_save(doc.raw, start, end, output_dir, sequence_number)
            )
            start = end + 1
            sequence_number += 1
    return output_paths


def split_by_flags(path: str, flag_positions: List[int], output_dir: str,
                    base_name: str) -> List[str]:
    """Tách file theo danh sách vị trí đặt cờ. flag_positions là index trang (0-based)
    ngay trước mỗi điểm ngắt — VD file 10 trang, đặt cờ giữa trang 3 và trang 4 → giá trị 3.

    Ghi chú: `base_name` giữ trong chữ ký hàm để không đổi kiến trúc đã chốt, nhưng
    KHÔNG dùng để đặt tên file nữa — tên file kết quả luôn theo mẫu PDF_Split_<STT>
    (xem _extract_pages_and_save)."""
    if not flag_positions:
        raise ValueError("Cần ít nhất 1 cờ để tách theo chế độ này")

    with PDFDocument(path) as doc:
        total = doc.page_count
        boundaries = sorted(set(flag_positions))
        for b in boundaries:
            if not (0 <= b < total - 1):
                raise ValueError(f"Vị trí cờ không hợp lệ: {b} (file có {total} trang)")

        segments: List[Tuple[int, int]] = []
        start = 0
        for b in boundaries:
            segments.append((start, b))
            start = b + 1
        segments.append((start, total - 1))

        output_paths = [
            _extract_pages_and_save(doc.raw, seg_start, seg_end, output_dir, sequence_number)
            for sequence_number, (seg_start, seg_end) in enumerate(segments, start=1)
        ]
    return output_paths


def merge_pdfs(paths_in_order: List[str], output_path: str) -> str:
    """Gộp nhiều file PDF theo đúng thứ tự trong danh sách."""
    if len(paths_in_order) < 2:
        raise ValueError("Cần ít nhất 2 file để gộp")

    merged = fitz.open()
    opened_docs: List[PDFDocument] = []
    try:
        for p in paths_in_order:
            pdoc = PDFDocument(p)  # validate hỏng/mật khẩu ngay tại đây
            opened_docs.append(pdoc)
            merged.insert_pdf(pdoc.raw)
        _safe_save(merged, output_path)
    finally:
        merged.close()
        for d in opened_docs:
            d.close()
    return output_path


def rotate_page_angle(current_rotation: int, direction: str) -> int:
    """Tính góc xoay mới thuần túy (không đụng file). direction = 'left' | 'right',
    mỗi lần ±90°, luôn trả về giá trị chuẩn hóa trong {0, 90, 180, 270}."""
    if direction not in ("left", "right"):
        raise ValueError("direction phải là 'left' hoặc 'right'")
    delta = -90 if direction == "left" else 90
    return (current_rotation + delta) % 360


# =============================================================================
# 5. Class trạng thái riêng theo tính năng (Nhóm B)
# =============================================================================

class PageEditSession:
    """Giữ trạng thái chỉnh sửa 1 file trong bộ nhớ cho tính năng Edit: thứ tự trang hiện
    tại, góc xoay tạm từng trang, tập hợp trang đang đánh dấu xóa.

    KHÔNG ghi file ở bất kỳ method nào trừ apply() — đúng nguyên tắc "gộp mọi thao tác
    thành 1 lần ghi file duy nhất khi bấm Áp dụng".
    """

    def __init__(self, path: str) -> None:
        self.path = path
        with PDFDocument(path) as doc:
            total = doc.page_count

        self._original_count = total
        self._order: List[int] = list(range(total))
        self._rotations: Dict[int, int] = {i: 0 for i in range(total)}
        self._marked: Set[int] = set()

    @property
    def page_order(self) -> List[int]:
        """Thứ tự hiển thị hiện tại (danh sách index gốc)."""
        return list(self._order)

    def reorder(self, new_order: List[int]) -> None:
        """Cập nhật thứ tự trang sau khi kéo-thả. new_order phải là hoán vị của
        thứ tự đang hiển thị hiện tại (không được thêm/bớt phần tử qua đường này)."""
        if sorted(new_order) != sorted(self._order):
            raise ValueError("new_order phải là hoán vị của thứ tự trang đang hiển thị")
        self._order = list(new_order)

    def rotate(self, page_id: int, direction: str) -> None:
        """Xoay trái/phải 90° — cộng dồn vào góc xoay tạm của trang, chưa ghi file."""
        current = self._rotations.get(page_id, 0)
        self._rotations[page_id] = rotate_page_angle(current, direction)

    def toggle_mark(self, page_id: int) -> None:
        """Đánh dấu / bỏ đánh dấu 1 trang (hiển thị viền đỏ trên thumbnail)."""
        if page_id in self._marked:
            self._marked.discard(page_id)
        else:
            self._marked.add(page_id)

    def is_marked(self, page_id: int) -> bool:
        return page_id in self._marked

    def delete_marked(self) -> None:
        """Xóa các trang đang đánh dấu khỏi danh sách hiển thị — chỉ trong bộ nhớ,
        chưa ghi ra file (phím Delete gọi hàm này)."""
        self._order = [i for i in self._order if i not in self._marked]
        self._marked.clear()

    def get_pending_rotation(self, page_id: int) -> int:
        """Góc xoay tạm hiện tại của 1 trang — PageRenderer dùng để render đúng preview."""
        return self._rotations.get(page_id, 0)

    def apply(self, output_path: str) -> str:
        """Ghi file thật 1 lần duy nhất: áp dụng thứ tự mới + góc xoay tạm, bỏ các trang
        đã xóa khỏi danh sách hiển thị."""
        new_doc = fitz.open()
        try:
            with PDFDocument(self.path) as doc:
                for source_index in self._order:
                    new_doc.insert_pdf(doc.raw, from_page=source_index, to_page=source_index)
                    rotation_delta = self._rotations.get(source_index, 0)
                    if rotation_delta:
                        new_page = new_doc[-1]
                        new_page.set_rotation((new_page.rotation + rotation_delta) % 360)
            _safe_save(new_doc, output_path)
        finally:
            new_doc.close()
        return output_path

    def reset(self) -> None:
        """Hủy toàn bộ thay đổi tạm, quay về trạng thái file gốc."""
        self._order = list(range(self._original_count))
        self._rotations = {i: 0 for i in range(self._original_count)}
        self._marked.clear()


class InsertSession:
    """Giữ 1 bản làm việc (working copy, trong bộ nhớ) của file B — được chèn dần qua
    nhiều lượt trước khi lưu thật. File A chỉ đọc, không bao giờ bị thay đổi.

    Mỗi lượt chèn chỉ 1 trang từ A (đã chốt đơn giản hóa — xem 02_dac_ta_tinh_nang.md mục 4).
    """

    def __init__(self, path_a: str, path_b: str) -> None:
        # Validate file A trước (hỏng/mật khẩu) — không giữ mở lâu, chỉ mở lại khi cần chèn.
        with PDFDocument(path_a):
            pass
        self.path_a = path_a

        try:
            self._working_b = fitz.open(path_b)
        except Exception as exc:
            raise CorruptedFileError(f"Không thể mở file: {path_b}") from exc
        if self._working_b.needs_pass:
            self._working_b.close()
            raise PasswordProtectedError(f"File yêu cầu mật khẩu: {path_b}")

        self._marked_page_a: Optional[int] = None
        self._selected_position_b: Optional[int] = None

    @property
    def working_page_count(self) -> int:
        """Số trang hiện tại của bản làm việc B (thay đổi sau mỗi lần chèn)."""
        return self._working_b.page_count

    @property
    def working_document(self) -> fitz.Document:
        """Expose bản làm việc B — PageRenderer dùng để render trực tiếp từ đây (không phải
        từ file path_b gốc trên đĩa) để Cột B luôn hiển thị đúng bản mới nhất sau khi chèn."""
        return self._working_b

    def mark_page_a(self, page_index: int) -> None:
        """Đánh dấu 1 trang ở A cho lượt chèn hiện tại — đánh dấu trang mới sẽ tự
        thay thế đánh dấu cũ nếu có (chỉ 1 trang tại 1 thời điểm)."""
        self._marked_page_a = page_index

    def unmark_page_a(self) -> None:
        self._marked_page_a = None

    def select_insert_position_b(self, page_index: int) -> None:
        """Chọn vị trí chèn ở B — chèn vào ngay sau trang có index này.
        Dùng -1 để chèn vào đầu file B."""
        self._selected_position_b = page_index

    def has_pending_mark(self) -> bool:
        """True nếu đang có trang ở A được đánh dấu mà CHƯA bấm Chèn."""
        return self._marked_page_a is not None

    def perform_insert(self) -> None:
        """Chèn trang đang đánh dấu ở A vào working copy của B, ngay sau vị trí đã chọn.
        Sau khi xong: tự động bỏ đánh dấu ở A, sẵn sàng cho lượt kế tiếp."""
        if self._marked_page_a is None:
            raise ValueError("Chưa đánh dấu trang nào ở file A để chèn")
        if self._selected_position_b is None:
            raise ValueError("Chưa chọn vị trí chèn ở file B")

        with PDFDocument(self.path_a) as doc_a:
            self._working_b.insert_pdf(
                doc_a.raw,
                from_page=self._marked_page_a,
                to_page=self._marked_page_a,
                start_at=self._selected_position_b + 1,
            )
        self.unmark_page_a()

    def save(self, output_path: str) -> str:
        """Ghi working copy hiện tại của B ra đĩa. Không lưu file A."""
        if self.has_pending_mark():
            raise ValueError(
                "Chưa thực hiện chèn, vui lòng bỏ đánh dấu hoặc thực hiện xong thao tác chèn"
            )
        _safe_save(self._working_b, output_path)
        return output_path

    def close(self) -> None:
        """Đóng working copy — widget gọi khi rời màn hình hoặc bấm Clear."""
        if self._working_b is not None:
            self._working_b.close()
            self._working_b = None