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

# =============================================================================
# 6. Bảo vệ PDF (Protection) — CHỈ BỔ SUNG, không sửa mục 1-5 phía trên.
#    Xem 07_dac_ta_chot_bao_ve_va_watermark.md mục 2.
# =============================================================================

class WrongPasswordError(Exception):
    """Mật khẩu nhập vào không đúng khi thử authenticate() để gỡ bảo vệ."""


_ALL_PERMISSION_BITS = (
    fitz.PDF_PERM_PRINT | fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_COPY
    | fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM | fitz.PDF_PERM_ACCESSIBILITY
    | fitz.PDF_PERM_ASSEMBLE | fitz.PDF_PERM_PRINT_HQ
)
"""Gộp toàn bộ 8 cờ quyền hạn chuẩn của PyMuPDF — dùng làm mặt nạ so sánh để phát hiện
'file có giới hạn quyền hay không', KHÔNG so sánh trực tiếp doc.permissions với -1: đã
kiểm chứng thực tế PyMuPDF trả về permissions = -4 (không phải -1) cho 1 file hoàn toàn
không hề được bảo vệ (do 2 bit thấp nhất trong permission luôn dự trữ = 0 theo chuẩn
PDF), nên phải AND với mặt nạ này rồi so khớp thay vì tin vào 1 giá trị "đầy đủ" cố định."""


@dataclass
class ProtectionStatus:
    """Trạng thái bảo vệ của 1 file — widget Bảo vệ dùng để quyết định luồng gỡ mật khẩu
    (xem 07_...md mục 2.5): cần hỏi mật khẩu, hay chỉ cần hỏi xác nhận, hay không có gì để gỡ.

    LƯU Ý QUAN TRỌNG (đã kiểm chứng thực tế, khác trực giác ban đầu): khi file chỉ có
    Owner Password và User Password để trống, `fitz.open()` tự động authenticate thành
    công bằng chuỗi rỗng NGAY LÚC MỞ — khiến `doc.is_encrypted` lập tức trả về False dù
    file thực sự có giới hạn quyền. Vì vậy KHÔNG dùng `is_encrypted` để phát hiện trường
    hợp owner-only — phải dùng `has_permission_restriction` (dựa trên bitmask
    `doc.permissions`) như dưới đây."""
    needs_password: bool               # True: file có User Password, bắt buộc nhập đúng mới đọc được
    has_permission_restriction: bool   # True: có giới hạn quyền (Owner Password) dù mở tự do được
    is_protected: bool                 # needs_password OR has_permission_restriction — tiện UI kiểm tra nhanh


def calculate_password_strength(password: str) -> int:
    """Heuristic thuần Python (không phụ thuộc PyMuPDF) để UI vẽ thanh đỏ-vàng-xanh
    'Độ mạnh mật khẩu' (07_...md mục 2.2). Trả điểm 0-100, chỉ mang tính gợi ý trực quan,
    không phải phép đo entropy thực sự."""
    if not password:
        return 0
    score = min(len(password) * 6, 40)  # độ dài đóng góp tối đa 40 điểm
    if any(c.islower() for c in password):
        score += 15
    if any(c.isupper() for c in password):
        score += 15
    if any(c.isdigit() for c in password):
        score += 15
    if any(not c.isalnum() for c in password):
        score += 15
    return min(score, 100)


def build_protection_permissions(cam_in: bool, cam_chinh_sua: bool, cam_sao_chep: bool) -> int:
    """Tính bitmask cho tham số `permissions=` của fitz — đúng ánh xạ đã chốt ở
    07_...md mục 2.3. LƯU Ý NGHĨA THAM SỐ: giá trị nhận vào đúng theo checkbox trên UI
    (True = đang tick = đang CẤM hành động đó), không phải 'có cho phép hay không'.

    fitz.PDF_PERM_ACCESSIBILITY luôn được set, không phụ thuộc checkbox nào (quyền dành
    cho phần mềm đọc màn hình hỗ trợ người khiếm thị)."""
    perm = fitz.PDF_PERM_ACCESSIBILITY
    if not cam_in:
        perm |= fitz.PDF_PERM_PRINT
    if not cam_chinh_sua:
        perm |= fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM
    if not cam_sao_chep:
        perm |= fitz.PDF_PERM_COPY
    return perm


def protect_pdf(path: str, output_path: str, password: str,
                 cam_in: bool = False, cam_chinh_sua: bool = False,
                 cam_sao_chep: bool = False) -> str:
    """Đặt mật khẩu (AES-256, cố định — 07_...md mục 2.1) + permission cho 1 file PDF,
    xuất ra file MỚI, không ghi đè file gốc. Dùng CHUNG 1 `password` cho cả user_pw và
    owner_pw (đã chốt 07_...md mục 2.2 — không tăng thêm bảo mật nếu tách 2 ô riêng).

    File nguồn phải là file KHÔNG có mật khẩu sẵn (đi qua PDFDocument như mọi tính năng
    khác — nếu cần bảo vệ lại 1 file đã có mật khẩu, phải Gỡ mật khẩu trước)."""
    if not password:
        raise ValueError("Mật khẩu không được để trống")

    permissions = build_protection_permissions(cam_in, cam_chinh_sua, cam_sao_chep)
    with PDFDocument(path) as doc:
        try:
            doc.raw.save(
                output_path,
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=password,
                owner_pw=password,
                permissions=permissions,
            )
        except Exception as exc:
            raise FileLockedError(
                f"Không thể ghi file (có thể đang bị khóa): {output_path}"
            ) from exc
    return output_path


def get_protection_status(path: str) -> ProtectionStatus:
    """Kiểm tra 1 file có đang được bảo vệ không, và có cần nhập mật khẩu mở hay không.

    CỐ TÌNH mở bằng `fitz.open()` trực tiếp thay vì qua PDFDocument — vì PDFDocument
    luôn raise PasswordProtectedError ngay khi needs_pass=True (đúng thiết kế bắt buộc
    cho Tách/Gộp/Edit/Chèn). Riêng Bảo vệ/Gỡ mật khẩu cần tự mở được file có mật khẩu
    nên phải tự quản lý việc mở file ở đây, không tái sử dụng PDFDocument."""
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise CorruptedFileError(f"Không thể mở file: {path}") from exc
    try:
        needs_password = doc.needs_pass
        has_permission_restriction = (
            not needs_password and (doc.permissions & _ALL_PERMISSION_BITS) != _ALL_PERMISSION_BITS
        )
        return ProtectionStatus(
            needs_password=needs_password,
            has_permission_restriction=has_permission_restriction,
            is_protected=needs_password or has_permission_restriction,
        )
    finally:
        doc.close()


def remove_password(path: str, output_path: str, password: Optional[str] = None) -> str:
    """Gỡ mật khẩu + mọi permission, xuất file MỚI hoàn toàn không còn mã hoá
    (07_...md mục 2.5). KHÔNG ghi đè file gốc.

    - File cần User Password (needs_pass=True): bắt buộc truyền đúng `password` —
      sai sẽ raise WrongPasswordError để widget báo lỗi ngay tại ô nhập.
    - File chỉ có Owner Password (needs_pass=False nhưng is_encrypted=True): không cần
      `password` — widget phải tự hỏi xác nhận người dùng TRƯỚC KHI gọi hàm này (xem
      get_protection_status để widget biết khi nào cần hỏi gì).
    - File không hề được mã hoá: vẫn xuất ra bản sao bình thường, không lỗi.
    """
    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise CorruptedFileError(f"Không thể mở file: {path}") from exc

    try:
        if doc.needs_pass:
            if not password or not doc.authenticate(password):
                raise WrongPasswordError("Mật khẩu không đúng")
        try:
            doc.save(output_path, encryption=fitz.PDF_ENCRYPT_NONE)
        except Exception as exc:
            raise FileLockedError(
                f"Không thể ghi file (có thể đang bị khóa): {output_path}"
            ) from exc
    finally:
        doc.close()
    return output_path


# =============================================================================
# 7. Chèn Watermark — CHỈ BỔ SUNG, không sửa mục 1-5 phía trên.
#    Xem 07_dac_ta_chot_bao_ve_va_watermark.md mục 1.
# =============================================================================

SEGOE_UI_FONT_PATH = r"C:\Windows\Fonts\segoeui.ttf"
"""Font cố định cho watermark chữ — đã chốt 07_...md mục 1.1. Có sẵn trên mọi máy
Windows, hỗ trợ đầy đủ dấu tiếng Việt, không cần đóng gói/redistribute riêng."""

_watermark_font_cache: Dict[str, "fitz.Font"] = {}


class FontNotFoundError(Exception):
    """Không nạp được font dùng cho watermark chữ (đường dẫn fontfile không tồn tại/hỏng)."""


def _get_watermark_font(fontfile: str = SEGOE_UI_FONT_PATH) -> "fitz.Font":
    """Nạp font 1 lần rồi cache lại — dùng `fitz.Font` (không dùng hàm rời
    `fitz.get_text_length`, vì hàm này từng đổi tên/behavior giữa các bản PyMuPDF khác
    nhau — `fitz.Font.text_length()` ổn định hơn và dùng được thẳng cho TextWriter)."""
    cached = _watermark_font_cache.get(fontfile)
    if cached is not None:
        return cached
    try:
        font = fitz.Font(fontfile=fontfile)
    except Exception as exc:
        raise FontNotFoundError(f"Không nạp được font: {fontfile}") from exc
    _watermark_font_cache[fontfile] = font
    return font


@dataclass
class TextWatermarkConfig:
    """Cấu hình watermark dạng chữ — 1-1 với các control ở Cột A của watermark_widget.py."""
    text: str
    font_size: int
    color_rgb: Tuple[float, float, float]  # mỗi giá trị 0.0-1.0 (chuẩn màu của PyMuPDF)
    opacity: float          # 0.0 - 1.0
    rotation: float         # độ, 0-360 tuỳ ý (không giới hạn bội số 90)
    layer_over: bool        # True = Foreground (đè lên nội dung), False = Background (nằm dưới)
    fontfile: str = SEGOE_UI_FONT_PATH  # cố định Segoe UI theo 07_...md — không cho UI đổi


@dataclass
class ImageWatermarkConfig:
    """Cấu hình watermark dạng ảnh — 1-1 với các control ở Cột A của watermark_widget.py."""
    image_path: str
    scale_percent: float    # % so với kích thước gốc của ảnh
    opacity: float          # 0.0 - 1.0
    rotation: float         # độ, 0-360 tuỳ ý
    layer_over: bool


def _tile_positions(page_width: float, page_height: float,
                     item_width: float, item_height: float) -> List[Tuple[float, float]]:
    """Tính toạ độ (x, y) góc trên-trái cho từng bản lặp watermark phủ toàn trang
    (Tiling — 07_...md mục 1.3, chốt là chế độ vị trí DUY NHẤT, không có option khác).

    Khoảng đệm giữa các bản lặp = 50% kích thước watermark đã render, hệ thống tự tính,
    không cho người dùng chỉnh. Lưới bắt đầu lệch âm 1 nửa kích thước watermark để các
    bản lặp phủ đều luôn cả phần sát mép trang, không để trống viền trắng quanh mép."""
    if item_width <= 0 or item_height <= 0:
        return []
    padding = max(item_width, item_height) * 0.5
    step_x = item_width + padding
    step_y = item_height + padding

    positions: List[Tuple[float, float]] = []
    y = -item_height / 2
    while y < page_height:
        x = -item_width / 2
        while x < page_width:
            positions.append((x, y))
            x += step_x
        y += step_y
    return positions


def draw_text_watermark_tiled(page: "fitz.Page", config: TextWatermarkConfig) -> None:
    """Vẽ watermark chữ lặp toàn trang lên 1 page ĐÃ MỞ SẴN — hàm này không tự save,
    apply_watermark_to_pdf() chịu trách nhiệm ghi file 1 lần cho cả tài liệu.

    BẮT BUỘC dùng `fitz.TextWriter` (không dùng `page.insert_text()` đơn giản) vì
    `insert_text()` chỉ nhận `rotate` là bội số 90° — không đáp ứng được slider góc xoay
    0-360° tuỳ ý đã chốt (07_...md mục 1.4.1). Mỗi bản lặp được vẽ bằng 1 TextWriter
    riêng vì tham số `morph` của `write_text()` áp dụng cho TOÀN BỘ nội dung đã append
    vào 1 TextWriter như MỘT phép biến đổi duy nhất quanh MỘT điểm neo — muốn mỗi bản
    lặp tự xoay quanh tâm của chính nó thì phải tách TextWriter riêng cho từng bản."""
    font = _get_watermark_font(config.fontfile)
    text_width = font.text_length(config.text, fontsize=config.font_size)
    text_height = config.font_size * 1.2  # hệ số dòng ước lượng, đủ dùng để tính spacing tiling

    positions = _tile_positions(page.rect.width, page.rect.height, text_width, text_height)
    for (x, y) in positions:
        tw = fitz.TextWriter(page.rect, color=config.color_rgb)
        baseline = fitz.Point(x, y + config.font_size)
        tw.append(baseline, config.text, font=font, fontsize=config.font_size)

        center = fitz.Point(x + text_width / 2, y + text_height / 2)
        morph = (center, fitz.Matrix(1, 1).prerotate(config.rotation))
        tw.write_text(page, opacity=config.opacity, morph=morph, overlay=config.layer_over)


def _apply_opacity_to_pixmap(pixmap: "fitz.Pixmap", opacity: float) -> "fitz.Pixmap":
    """Nhân kênh alpha hiện có với hệ số `opacity` (0.0-1.0). Cần bước này vì
    `page.insert_image()` của PyMuPDF KHÔNG có tham số opacity trực tiếp như
    `TextWriter.write_text()` — muốn slider Opacity của watermark ảnh có tác dụng thì
    phải tự làm mờ ngay trên dữ liệu pixel trước khi chèn.

    LƯU Ý QUAN TRỌNG (đã kiểm chứng thực tế bằng test, khác trực giác ban đầu):
    `pixmap.n` của PyMuPDF đã BAO GỒM SẴN kênh alpha khi `pixmap.alpha=True` (VD ảnh RGB
    có alpha thì `n=4`, không phải `n=3` rồi cộng riêng 1 cho alpha) — nên `stride` giữa
    2 pixel liên tiếp = `pixmap.n`, và alpha luôn là byte CUỐI mỗi pixel, tức offset
    `pixmap.n - 1`, KHÔNG PHẢI `pixmap.n`."""
    if not pixmap.alpha:
        pixmap = fitz.Pixmap(pixmap, 1)
    samples = bytearray(pixmap.samples)
    stride = pixmap.n            # đã bao gồm kênh alpha
    alpha_offset = pixmap.n - 1  # alpha luôn là byte cuối cùng của mỗi pixel
    for i in range(alpha_offset, len(samples), stride):
        samples[i] = int(samples[i] * opacity)
    return fitz.Pixmap(pixmap.colorspace, pixmap.width, pixmap.height, bytes(samples), True)


def _rotate_image_to_bytes(image_path: str, rotation_degrees: float,
                            opacity: float) -> Tuple[bytes, float, float]:
    """'Bake' góc xoay tuỳ ý + opacity vào ảnh bằng chính PyMuPDF (không dùng Pillow —
    đúng quy ước dự án). Trả về (PNG bytes đã xử lý, width mới, height mới).

    Kỹ thuật (07_...md mục 1.4.2): dựng 1 trang PDF tạm chỉ chứa ảnh gốc, sau đó render
    lại trang này qua `get_pixmap(matrix=...)` với ma trận đã prerotate — giữ nguyên
    alpha xuyên suốt để nền không bị trắng đè lên."""
    try:
        pixmap_src = fitz.Pixmap(image_path)
    except Exception as exc:
        raise CorruptedFileError(f"Không thể đọc file ảnh: {image_path}") from exc

    if pixmap_src.colorspace is None or pixmap_src.colorspace.n > 3:
        pixmap_src = fitz.Pixmap(fitz.csRGB, pixmap_src)
    pixmap_src = _apply_opacity_to_pixmap(pixmap_src, opacity)

    tmp_doc = fitz.open()
    try:
        tmp_page = tmp_doc.new_page(width=pixmap_src.width, height=pixmap_src.height)
        tmp_page.insert_image(tmp_page.rect, pixmap=pixmap_src, overlay=True)

        rotate_matrix = fitz.Matrix(1, 1).prerotate(rotation_degrees)
        rotated_rect = tmp_page.rect * rotate_matrix
        # Dời gốc toạ độ về (0, 0) để render không bị cắt phần toạ độ âm sau khi xoay
        shift_matrix = rotate_matrix * fitz.Matrix(1, 0, 0, 1, -rotated_rect.x0, -rotated_rect.y0)

        rotated_pixmap = tmp_page.get_pixmap(matrix=shift_matrix, alpha=True)
        data = rotated_pixmap.tobytes("png")
        return data, rotated_pixmap.width, rotated_pixmap.height
    finally:
        tmp_doc.close()


def draw_image_watermark_tiled(page: "fitz.Page", config: ImageWatermarkConfig) -> None:
    """Vẽ watermark ảnh lặp toàn trang lên 1 page ĐÃ MỞ SẴN — hàm này không tự save,
    apply_watermark_to_pdf() chịu trách nhiệm ghi file 1 lần cho cả tài liệu.

    Cũng phải "bake" góc xoay vào ảnh trước (xem _rotate_image_to_bytes) vì
    `page.insert_image()` chỉ nhận `rotate` là bội số 90°, giống hệt lý do với Text."""
    rotated_bytes, base_w, base_h = _rotate_image_to_bytes(
        config.image_path, config.rotation, config.opacity
    )
    scale = config.scale_percent / 100.0
    item_w = base_w * scale
    item_h = base_h * scale

    positions = _tile_positions(page.rect.width, page.rect.height, item_w, item_h)
    for (x, y) in positions:
        rect = fitz.Rect(x, y, x + item_w, y + item_h)
        page.insert_image(rect, stream=rotated_bytes, overlay=config.layer_over)


def apply_watermark_to_pdf(path: str, output_path: str,
                            text_config: Optional[TextWatermarkConfig] = None,
                            image_config: Optional[ImageWatermarkConfig] = None) -> str:
    """Áp watermark (đúng 1 trong 2: Text HOẶC Image, theo mode đang chọn trên UI) lặp
    toàn trang lên MỌI trang của file, xuất ra file MỚI — không ghi đè file gốc (tuân
    theo quy ước chung 02_dac_ta_tinh_nang.md mục 0)."""
    if bool(text_config) == bool(image_config):
        raise ValueError("Phải truyền đúng 1 trong 2: text_config hoặc image_config")

    with PDFDocument(path) as doc:
        for page in doc.raw:
            if text_config is not None:
                draw_text_watermark_tiled(page, text_config)
            else:
                draw_image_watermark_tiled(page, image_config)
        _safe_save(doc.raw, output_path)
    return output_path