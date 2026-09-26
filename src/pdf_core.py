"""
/src/pdf_core.py
"""
from __future__ import annotations

import os
import secrets
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
        except Exception as exc:  
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
    
        return self._doc

    @property
    def page_count(self) -> int:
        return self._doc.page_count

    def get_page_size(self, page_index: int) -> Tuple[float, float]:
        rect = self._doc[page_index].rect
        return (rect.width, rect.height)


@dataclass
class PageInfo:

    source_index: int
    width: float
    height: float
    rotation: int


def get_page_count(path: str) -> int:
   
    with PDFDocument(path) as doc:
        return doc.page_count


def list_page_infos(path: str) -> List[PageInfo]:
    infos: List[PageInfo] = []
    with PDFDocument(path) as doc:
        for i in range(doc.page_count):
            page = doc.raw[i]
            rect = page.rect
            infos.append(PageInfo(source_index=i, width=rect.width, height=rect.height,
                                   rotation=page.rotation))
    return infos


class PageRenderer:

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

    try:
        doc.save(output_path)
    except Exception as exc:
        raise FileLockedError(f"Không thể ghi file (có thể đang bị khóa): {output_path}") from exc


def _extract_pages_and_save(source_doc: fitz.Document, start: int, end: int,
                             output_dir: str, sequence_number: int) -> str:

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
            pdoc = PDFDocument(p)  
            opened_docs.append(pdoc)
            merged.insert_pdf(pdoc.raw)
        _safe_save(merged, output_path)
    finally:
        merged.close()
        for d in opened_docs:
            d.close()
    return output_path


def rotate_page_angle(current_rotation: int, direction: str) -> int:

    if direction not in ("left", "right"):
        raise ValueError("direction phải là 'left' hoặc 'right'")
    delta = -90 if direction == "left" else 90
    return (current_rotation + delta) % 360


# =============================================================================
# 5. Class trạng thái riêng theo tính năng (Nhóm B)
# =============================================================================

class PageEditSession:

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

        self._order = [i for i in self._order if i not in self._marked]
        self._marked.clear()

    def get_pending_rotation(self, page_id: int) -> int:
        return self._rotations.get(page_id, 0)

    def apply(self, output_path: str) -> str:

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

    # ------------------------------------------------------------------
    def snapshot(self) -> dict:

        return {
            "order": list(self._order),
            "rotations": dict(self._rotations),
            "marked": set(self._marked),
        }

    def restore(self, snapshot: dict) -> None:

        self._order = list(snapshot["order"])
        self._rotations = dict(snapshot["rotations"])
        self._marked = set(snapshot["marked"])


class InsertSession:

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
        return self._working_b

    def mark_page_a(self, page_index: int) -> None:

        self._marked_page_a = page_index

    def unmark_page_a(self) -> None:
        self._marked_page_a = None

    def select_insert_position_b(self, page_index: int) -> None:

        self._selected_position_b = page_index

    def has_pending_mark(self) -> bool:

        return self._marked_page_a is not None

    def perform_insert(self) -> None:

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
# 6. Bảo vệ PDF (Protection) 
# =============================================================================

class WrongPasswordError(Exception):
    """Mật khẩu nhập vào không đúng khi thử authenticate() để gỡ bảo vệ."""


_ALL_PERMISSION_BITS = (
    fitz.PDF_PERM_PRINT | fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_COPY
    | fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM | fitz.PDF_PERM_ACCESSIBILITY
    | fitz.PDF_PERM_ASSEMBLE | fitz.PDF_PERM_PRINT_HQ
)

@dataclass
class ProtectionStatus:
    needs_password: bool               # True: file có User Password, bắt buộc nhập đúng mới đọc được
    has_permission_restriction: bool   # True: có giới hạn quyền (Owner Password) dù mở tự do được
    is_protected: bool                 # needs_password OR has_permission_restriction — tiện UI kiểm tra nhanh


def calculate_password_strength(password: str) -> int:

    if not password:
        return 0
    score = min(len(password) * 6, 40)  
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

    perm = fitz.PDF_PERM_ACCESSIBILITY
    if not cam_in:
        perm |= fitz.PDF_PERM_PRINT
    if not cam_chinh_sua:
        perm |= fitz.PDF_PERM_MODIFY | fitz.PDF_PERM_ANNOTATE | fitz.PDF_PERM_FORM
    if not cam_sao_chep:
        perm |= fitz.PDF_PERM_COPY
    return perm


def _generate_owner_secret() -> str:

    return secrets.token_hex(16)


def protect_pdf(path: str, output_path: str, password: str,
                 cam_in: bool = False, cam_chinh_sua: bool = False,
                 cam_sao_chep: bool = False) -> str:

    if not password:
        raise ValueError("Mật khẩu không được để trống")

    permissions = build_protection_permissions(cam_in, cam_chinh_sua, cam_sao_chep)
    owner_secret = _generate_owner_secret()
    with PDFDocument(path) as doc:
        try:
            doc.raw.save(
                output_path,
                encryption=fitz.PDF_ENCRYPT_AES_256,
                user_pw=password,
                owner_pw=owner_secret,
                permissions=permissions,
            )
        except Exception as exc:
            raise FileLockedError(
                f"Không thể ghi file (có thể đang bị khóa): {output_path}"
            ) from exc
    return output_path


def get_protection_status(path: str) -> ProtectionStatus:

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


# -----------------------------------------------------------------------------
# 6b. Phiên xem trước + Mở khóa (Unlock) 
# -----------------------------------------------------------------------------

class UnlockPreviewSession:

    def __init__(self, path: str) -> None:
        self.path = path
        try:
            self._doc = fitz.open(path)
        except Exception as exc:
            raise CorruptedFileError(f"Không thể mở file: {path}") from exc
        self._needs_password = self._doc.needs_pass

        self._authenticated = not self._needs_password

    @property
    def needs_password(self) -> bool:
        """True nếu file có User Password — bắt buộc authenticate() đúng mới render/lưu được."""
        return self._needs_password

    @property
    def is_ready(self) -> bool:
        """True nếu đã có thể render preview / lưu file (đã authenticate thành công,
        hoặc file thuộc case owner-only không cần mật khẩu)."""
        return self._authenticated

    @property
    def document(self) -> fitz.Document:
        """Expose fitz.Document đang mở — dùng cho render_document_page() (mục 8).
        Chỉ nên gọi khi is_ready = True, gọi sớm hơn sẽ render nội dung còn mã hoá."""
        return self._doc

    def authenticate(self, password: str) -> bool:
        """Thử xác thực User Password. Trả True/False, KHÔNG raise — widget tự quyết
        định thông báo lỗi tại ô nhập (khác remove_password() vốn raise
        WrongPasswordError, vì ở đây là luồng preview trước, chưa ghi file ngay)."""
        if not self._needs_password:
            self._authenticated = True
            return True
        ok = bool(password) and bool(self._doc.authenticate(password))
        self._authenticated = ok
        return ok

    def save_unlocked(self, output_path: str) -> str:
        """Ghi file MỚI hoàn toàn không còn mật khẩu/permission — dùng đúng cơ chế của
        remove_password() (PDF_ENCRYPT_NONE), không ghi đè file gốc."""
        if not self._authenticated:
            raise WrongPasswordError("Chưa xác thực thành công, không thể lưu file")
        try:
            self._doc.save(output_path, encryption=fitz.PDF_ENCRYPT_NONE)
        except Exception as exc:
            raise FileLockedError(
                f"Không thể ghi file (có thể đang bị khóa): {output_path}"
            ) from exc
        return output_path

    def close(self) -> None:
        """Đóng document — widget gọi khi bấm Clear hoặc chọn file khác."""
        if self._doc is not None:
            self._doc.close()
            self._doc = None


# =============================================================================
# 7. Chèn Watermark 
# =============================================================================

SEGOE_UI_FONT_PATH = r"C:\Windows\Fonts\segoeui.ttf"

_watermark_font_cache: Dict[str, "fitz.Font"] = {}


class FontNotFoundError(Exception):
    """Không nạp được font dùng cho watermark chữ (đường dẫn fontfile không tồn tại/hỏng)."""


def _get_watermark_font(fontfile: str = SEGOE_UI_FONT_PATH) -> "fitz.Font":

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
    color_rgb: Tuple[float, float, float]  
    opacity: float         
    rotation: float        
    layer_over: bool        
    fontfile: str = SEGOE_UI_FONT_PATH  


@dataclass
class ImageWatermarkConfig:

    image_path: str
    scale_percent: float    # % so với kích thước gốc của ảnh
    opacity: float          # 0.0 - 1.0
    rotation: float         # độ, 0-360 tuỳ ý
    layer_over: bool


def draw_text_watermark_centered(page: "fitz.Page", config: TextWatermarkConfig) -> None:

    font = _get_watermark_font(config.fontfile)
    text_width = font.text_length(config.text, fontsize=config.font_size)
    text_height = config.font_size * 1.2  # hệ số dòng ước lượng, đủ dùng để canh giữa

    center_x = page.rect.width / 2
    center_y = page.rect.height / 2
    x = center_x - text_width / 2
    y = center_y - text_height / 2

    tw = fitz.TextWriter(page.rect, color=config.color_rgb)
    baseline = fitz.Point(x, y + config.font_size)
    tw.append(baseline, config.text, font=font, fontsize=config.font_size)

    center = fitz.Point(center_x, center_y)
    morph = (center, fitz.Matrix(1, 1).prerotate(config.rotation))
    tw.write_text(page, opacity=config.opacity, morph=morph, overlay=config.layer_over)


def _apply_opacity_to_pixmap(pixmap: "fitz.Pixmap", opacity: float) -> "fitz.Pixmap":

    if not pixmap.alpha:
        pixmap = fitz.Pixmap(pixmap, 1)
    samples = bytearray(pixmap.samples)
    stride = pixmap.n            # đã bao gồm kênh alpha
    alpha_offset = pixmap.n - 1  # alpha luôn là byte cuối cùng của mỗi pixel
    alpha_bytes = samples[alpha_offset::stride]
    samples[alpha_offset::stride] = bytes(int(b * opacity) for b in alpha_bytes)
    return fitz.Pixmap(pixmap.colorspace, pixmap.width, pixmap.height, bytes(samples), True)


def _rotate_image_to_pixmap(image_path: str, rotation_degrees: float,
                             opacity: float) -> "fitz.Pixmap":

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

        # ĐẢO DẤU (-rotation_degrees) — xem điểm 1 trong docstring ở trên.
        rotate_matrix = fitz.Matrix(1, 1).prerotate(-rotation_degrees)
        rotated_rect = tmp_page.rect * rotate_matrix
        # Dời gốc toạ độ về (0, 0) để render không bị cắt phần toạ độ âm sau khi xoay
        shift_matrix = rotate_matrix * fitz.Matrix(1, 0, 0, 1, -rotated_rect.x0, -rotated_rect.y0)

        rotated_pixmap = tmp_page.get_pixmap(matrix=shift_matrix, alpha=True)
        return rotated_pixmap
    finally:
        tmp_doc.close()


def draw_image_watermark_centered(page: "fitz.Page", config: ImageWatermarkConfig,
                                   rotated_pixmap: Optional["fitz.Pixmap"] = None) -> None:

    if rotated_pixmap is None:
        rotated_pixmap = _rotate_image_to_pixmap(
            config.image_path, config.rotation, config.opacity
        )
    scale = config.scale_percent / 100.0
    item_w = rotated_pixmap.width * scale
    item_h = rotated_pixmap.height * scale

    center_x = page.rect.width / 2
    center_y = page.rect.height / 2
    rect = fitz.Rect(
        center_x - item_w / 2, center_y - item_h / 2,
        center_x + item_w / 2, center_y + item_h / 2,
    )
    page.insert_image(rect, pixmap=rotated_pixmap, overlay=config.layer_over)


def apply_watermark_to_pdf(path: str, output_path: str,
                            text_config: Optional[TextWatermarkConfig] = None,
                            image_config: Optional[ImageWatermarkConfig] = None) -> str:

    if bool(text_config) == bool(image_config):
        raise ValueError("Phải truyền đúng 1 trong 2: text_config hoặc image_config")

    precomputed_image_pixmap: Optional["fitz.Pixmap"] = None
    if image_config is not None:
        precomputed_image_pixmap = _rotate_image_to_pixmap(
            image_config.image_path, image_config.rotation, image_config.opacity
        )

    with PDFDocument(path) as doc:
        for page in doc.raw:
            if text_config is not None:
                draw_text_watermark_centered(page, text_config)
            else:
                draw_image_watermark_centered(page, image_config, precomputed_image_pixmap)
        _safe_save(doc.raw, output_path)
    return output_path


# =============================================================================
# 8. Hỗ trợ render riêng cho Chèn file (Insert) 
# =============================================================================

def render_document_page(doc: fitz.Document, page_index: int, target_width: int = 160,
                          pending_rotation: int = 0) -> bytes:

    page = doc[page_index]
    if pending_rotation:
        page.set_rotation((page.rotation + pending_rotation) % 360)
    rect = page.rect
    zoom = target_width / rect.width if rect.width else 1.0
    pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pixmap.tobytes("png")


# -----------------------------------------------------------------------------
# 8b. Tiện ích đọc metadata trực tiếp từ 1 fitz.Document
# -----------------------------------------------------------------------------

def get_document_page_count(doc: fitz.Document) -> int:
    return doc.page_count


def get_document_page_size(doc: fitz.Document, page_index: int) -> Tuple[float, float]:
    rect = doc[page_index].rect
    return (rect.width, rect.height)