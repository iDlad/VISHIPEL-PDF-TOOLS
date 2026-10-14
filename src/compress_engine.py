"""
/src/compress_engine.py

Lõi logic tính năng Nén file PDF (Ver2). Thuần logic, KHÔNG phụ thuộc PySide6.

File này HOÀN TOÀN MỚI và độc lập: không sửa dòng nào của pdf_core.py (file dùng chung của
các tính năng khác). Chỉ import lại các class/exception public có sẵn (PDFDocument,
CorruptedFileError, PasswordProtectedError, FileLockedError) để mọi tính năng dùng chung
1 luồng báo lỗi.

Nguyên tắc:
- Luôn nén từ file GỐC (mở chỉ đọc), không bao giờ ghi vào file gốc.
- Chỉ ảnh bị xử lý; chữ vector và lớp chữ ẩn (file scan đã OCR) giữ nguyên.
- Nén TỪNG ẢNH: ảnh nào sau khi nén không nhỏ hơn bản gốc (đủ một biên an toàn) thì GIỮ
  NGUYÊN ảnh gốc -> bước xử lý ảnh không bao giờ làm file phình ra.
- Ảnh 1-bit (fax/CCITT/JBIG2), ảnh có mặt nạ trong suốt, ảnh quá nhỏ: bỏ qua.
- Ghi ra file tạm cạnh file đích, kiểm tra kết quả, đạt mới chuyển vào đúng tên file đích.
  Nhờ vậy lỗi giữa chừng không bao giờ để lại file hỏng hay làm hỏng file đích có sẵn.
- Kết quả có kèm chuỗi chẩn đoán ("diag") để biết vì sao một file nén được ít hoặc không nén được.
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import fitz  # PyMuPDF

from src.pdf_core import (
    CorruptedFileError,
    FileLockedError,
    PasswordProtectedError,
    PDFDocument,
)

__all__ = [
    "CompressError",
    "CorruptedFileError",
    "FileLockedError",
    "PasswordProtectedError",
    "LEVELS",
    "compress_pdf",
    "has_digital_signature",
    "render_compressed_page",
]


class CompressError(Exception):
    """Lỗi nén mà người dùng đọc được (không phải lỗi file hỏng/khóa/mật khẩu):
    kết quả không đạt kiểm tra, PyMuPDF quá cũ, lỗi khi xử lý ảnh..."""


# ----------------------------------------------------------------------
# Tham số các mức nén — GIÁ TRỊ KHỞI ĐIỂM (GỢI Ý), chỉnh lại sau khi thử trên file thật
# ----------------------------------------------------------------------
LEVELS = ("light", "medium", "strong", "max")

# level -> (DPI đích, chất lượng JPEG). "light" không đụng vào ảnh nên không có mục ở đây.
_IMAGE_PARAMS: Dict[str, tuple] = {
    "medium": (150, 70),
    "strong": (120, 55),
    "max": (100, 45),
}

# Chỉ hạ DPI với ảnh có DPI > DPI đích * hệ số này — tránh thu nhỏ ảnh chỉ nhỉnh hơn mục tiêu
# một ít (mất chất lượng mà lợi dung lượng không đáng).
_THRESHOLD_FACTOR = 1.2

# Chỉ thay ảnh khi ảnh mới <= tỉ lệ này so với ảnh gốc (biên an toàn, tránh đổi lấy lợi quá nhỏ).
_MIN_GAIN_RATIO = 0.95

# Ảnh nhỏ hơn ngưỡng này (byte) không đáng xử lý (logo, con dấu...).
_MIN_IMAGE_BYTES = 20 * 1024

# Kích thước tối thiểu (pixel) mỗi cạnh sau khi hạ DPI.
_MIN_SIDE_PX = 16

# Mức garbage thử lần lượt khi lưu. Có báo cáo lỗi PyMuPDF: sau khi đổi ảnh mà lưu với
# garbage > 1 thì font có thể hỏng -> mức có nén ảnh chỉ dùng garbage 1.
# Mức "light" không đụng ảnh nên thử garbage 4 trước.
_GARBAGE_LADDER_LIGHT = (4, 1)
_GARBAGE_LADDER_IMAGE = (1,)

# Bước kiểm tra lớp chữ: số ký tự sau nén phải >= tỉ lệ này so với trước nén.
_TEXT_KEEP_RATIO = 0.95

# Đuôi file tạm đặt cạnh file đích
_TMP_SUFFIX = ".compress_tmp"
_BEST_SUFFIX = ".compress_best"


# ----------------------------------------------------------------------
# Hàm phụ
# ----------------------------------------------------------------------
def _check_level(level: str) -> None:
    if level not in LEVELS:
        raise ValueError(f"Mức nén không hợp lệ: {level}")


def _require_image_api() -> None:
    """Cần các hàm xử lý ảnh của PyMuPDF bản đủ mới."""
    needed = (
        hasattr(fitz.Page, "replace_image")
        and hasattr(fitz.Page, "get_image_info")
        and hasattr(fitz.Pixmap, "tobytes")
    )
    if not needed:
        raise CompressError(
            f"Phiên bản PyMuPDF hiện tại ({getattr(fitz, 'VersionBind', '?')}) quá cũ, "
            "chưa hỗ trợ nén ảnh. Hãy nâng cấp PyMuPDF (pip install -U pymupdf) rồi chạy lại."
        )


def _fmt_size(num_bytes: float) -> str:
    size = float(max(0.0, num_bytes))
    for unit in ("B", "KB", "MB"):
        if size < 1024:
            return f"{int(size)} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.2f} GB"


def _collect_images(doc: "fitz.Document") -> List[dict]:
    """Liệt kê mọi ảnh trong file, mỗi ảnh 1 lần (theo xref).

    Mỗi bản ghi: xref, pno (trang đầu thấy ảnh), smask, bpc, filter, len (byte thô),
    dpi (DPI NHỎ NHẤT trong các chỗ ảnh được vẽ = chỗ ảnh hiển thị to nhất; None nếu
    không xác định được)."""
    records: Dict[int, dict] = {}
    for pno in range(doc.page_count):
        page = doc[pno]
        for im in page.get_images(full=True):
            xref = im[0]
            if xref not in records:
                records[xref] = {
                    "xref": xref, "pno": pno, "smask": im[1], "bpc": im[4],
                    "filter": im[8] or "", "len": 0, "dpi": None,
                }
        for info in page.get_image_info(xrefs=True):
            xref = info.get("xref") or 0
            rec = records.get(xref)
            if rec is None:
                continue
            bbox = fitz.Rect(info["bbox"])
            if bbox.width <= 0 or bbox.height <= 0:
                continue
            # Dùng cạnh dài để không phụ thuộc ảnh bị xoay 90 độ trên trang
            dpi = max(info["width"], info["height"]) / (max(bbox.width, bbox.height) / 72.0)
            if rec["dpi"] is None or dpi < rec["dpi"]:
                rec["dpi"] = dpi
                rec["pno"] = pno
    for rec in records.values():
        try:
            rec["len"] = len(doc.xref_stream_raw(rec["xref"]))
        except Exception:
            rec["len"] = 0
    return list(records.values())


def _recompress_images(doc: "fitz.Document", level: str, to_grayscale: bool) -> dict:
    """Hạ DPI + nén lại JPEG từng ảnh theo mức; chỉ thay khi ảnh mới nhỏ hơn rõ rệt.

    Trả về thống kê dùng cho chẩn đoán:
    images, image_bytes, replaced, kept, skipped, failed, saved_bytes, by_filter."""
    _require_image_api()
    dpi_target, quality = _IMAGE_PARAMS[level]
    threshold = dpi_target * _THRESHOLD_FACTOR

    records = _collect_images(doc)
    stats = {
        "images": len(records),
        "image_bytes": sum(r["len"] for r in records),
        "replaced": 0, "kept": 0, "skipped": 0, "failed": 0, "saved_bytes": 0,
        "by_filter": {},
    }
    for rec in records:
        name = rec["filter"] or "không nén"
        stats["by_filter"][name] = stats["by_filter"].get(name, 0) + 1

    for rec in records:
        # Bỏ qua: ảnh 1-bit, ảnh có mặt nạ trong suốt, ảnh quá nhỏ, ảnh không rõ vị trí vẽ
        if rec["bpc"] == 1 or rec["smask"] or rec["len"] < _MIN_IMAGE_BYTES or rec["dpi"] is None:
            stats["skipped"] += 1
            continue
        try:
            pix = fitz.Pixmap(doc, rec["xref"])
            if pix.colorspace is not None and pix.colorspace.n == 4:
                pix = fitz.Pixmap(fitz.csRGB, pix)          # CMYK -> RGB cho JPEG chuẩn
            if to_grayscale and pix.colorspace is not None and pix.colorspace.n != 1:
                pix = fitz.Pixmap(fitz.csGRAY, pix)
            if pix.alpha:
                pix = fitz.Pixmap(pix, 0)                    # bỏ kênh alpha thừa
            if rec["dpi"] > threshold:
                scale = dpi_target / rec["dpi"]
                new_w = max(_MIN_SIDE_PX, int(pix.width * scale))
                new_h = max(_MIN_SIDE_PX, int(pix.height * scale))
                pix = fitz.Pixmap(pix, new_w, new_h)
            data = pix.tobytes("jpeg", jpg_quality=quality)
        except Exception:
            stats["failed"] += 1                              # ảnh lạ: giữ nguyên, không làm hỏng cả file
            continue

        if len(data) <= rec["len"] * _MIN_GAIN_RATIO:
            try:
                doc[rec["pno"]].replace_image(rec["xref"], stream=data)
            except Exception:
                stats["failed"] += 1
                continue
            stats["replaced"] += 1
            stats["saved_bytes"] += rec["len"] - len(data)
        else:
            stats["kept"] += 1                                # nén xong không nhỏ hơn -> giữ ảnh gốc
    return stats


def _build_diag(level: str, size_before: int, stats: Optional[dict], total_pages: int) -> str:
    """Chuỗi chẩn đoán 1 dòng, dễ đọc, dùng để hiển thị/ghi log."""
    ver = getattr(fitz, "VersionBind", "?")
    if stats is None:
        return f"PyMuPDF {ver} · {total_pages} trang · mức Nhẹ (không đụng ảnh)"
    formats = ", ".join(f"{k}×{v}" for k, v in stats["by_filter"].items()) or "không có ảnh"
    share = (stats["image_bytes"] / size_before * 100) if size_before else 0
    return (
        f"PyMuPDF {ver} · {total_pages} trang · {stats['images']} ảnh "
        f"({_fmt_size(stats['image_bytes'])}, {share:.0f}% dung lượng file) · "
        f"đã thu nhỏ {stats['replaced']} (tiết kiệm {_fmt_size(stats['saved_bytes'])}) · "
        f"giữ nguyên {stats['kept']} · bỏ qua {stats['skipped']} · lỗi {stats['failed']} · "
        f"định dạng ảnh: {formats}"
    )


def _sample_indexes(total_pages: int) -> List[int]:
    """Các trang dùng để kiểm tra sau nén: đầu, cuối và 3 điểm giữa (không trùng)."""
    if total_pages <= 0:
        return []
    picks = {0, total_pages // 4, total_pages // 2, (total_pages * 3) // 4, total_pages - 1}
    return sorted(i for i in picks if 0 <= i < total_pages)


def _save_variants(level: str) -> List[dict]:
    """Các kiểu lưu thử lần lượt. Dừng ở kiểu đầu tiên cho file đạt kiểm tra VÀ nhỏ hơn bản gốc.
    Kiểu cuối (không clean, không deflate) là phương án dự phòng cho file có cấu trúc đặc biệt,
    nơi các tùy chọn nén lại làm file phình ra."""
    ladder = _GARBAGE_LADDER_LIGHT if level == "light" else _GARBAGE_LADDER_IMAGE
    variants: List[dict] = []
    for garbage in ladder:
        variants.append(dict(garbage=garbage, clean=True, deflate=True,
                             deflate_images=True, deflate_fonts=True))
    variants.append(dict(garbage=ladder[-1], clean=False, deflate=True))
    variants.append(dict(garbage=0, clean=False, deflate=False))
    return variants


def _save_temp(doc: "fitz.Document", tmp_path: str, options: dict) -> None:
    """Lưu bản nén ra file tạm. KHÔNG dùng Brotli (deflate=2) để mọi trình đọc PDF mở được."""
    try:
        doc.save(tmp_path, **options)
    except Exception as exc:
        raise FileLockedError(f"Không thể ghi file (có thể đang bị khóa): {tmp_path}") from exc


def _verify_output(tmp_path: str, total_pages: int, sample: List[int],
                   text_before: Dict[int, int]) -> Optional[str]:
    """Kiểm tra file kết quả. Trả về None nếu đạt, hoặc chuỗi mô tả vấn đề.

    a. mở lại được; b. đủ số trang; c. render thử các trang mẫu không lỗi;
    d. số ký tự văn bản các trang mẫu không giảm đáng kể (phát hiện hỏng font/lớp chữ ẩn).
    """
    try:
        out = fitz.open(tmp_path)
    except Exception:
        return "không mở lại được file kết quả"
    try:
        if out.needs_pass:
            return "file kết quả bị yêu cầu mật khẩu"
        if out.page_count != total_pages:
            return f"số trang không khớp ({out.page_count}/{total_pages})"
        for i in sample:
            page = out[i]
            page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25))  # chỉ cần chứng minh render được
            before = text_before.get(i, 0)
            if before > 0:
                after = len(page.get_text())
                if after < before * _TEXT_KEEP_RATIO:
                    return f"lớp chữ ở trang {i + 1} bị mất ({after}/{before} ký tự)"
        return None
    except Exception as exc:
        return f"lỗi khi đọc/render file kết quả: {exc}"
    finally:
        out.close()


def _remove_quietly(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


# ----------------------------------------------------------------------
# Hàm công khai
# ----------------------------------------------------------------------
def compress_pdf(path: str, level: str, output_path: str, to_grayscale: bool = False) -> dict:
    """Nén file PDF `path` ra `output_path`.

    level: "light" | "medium" | "strong" | "max".
    to_grayscale: ép ảnh sang xám — bị bỏ qua ở mức "light" (không đụng vào ảnh).

    Trả về dict: {"size_before", "size_after", "percent", "status", "page_count", "diag"}
      status = "ok"          -> đã ghi file kết quả vào output_path.
      status = "not_smaller" -> kết quả không nhỏ hơn bản gốc: KHÔNG ghi file, không phải lỗi.
      diag = chuỗi chẩn đoán 1 dòng (số ảnh, ảnh chiếm bao nhiêu % dung lượng, bao nhiêu ảnh
             đã thu nhỏ/giữ nguyên...) giúp biết vì sao file nén được ít hoặc không nén được.

    Raise: ValueError (mức sai / trùng file gốc), CorruptedFileError, PasswordProtectedError,
    FileLockedError (không ghi được), CompressError (kết quả không đạt kiểm tra...).
    Khi raise, file gốc và file đích có sẵn (nếu có) luôn được giữ nguyên.
    """
    _check_level(level)
    if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(output_path)):
        raise ValueError("Không được ghi đè lên chính file gốc, vui lòng chọn tên file khác")

    try:
        size_before = os.path.getsize(path)
    except OSError as exc:
        raise CorruptedFileError(f"Không thể mở file: {path}") from exc

    tmp_path = output_path + _TMP_SUFFIX
    best_path = output_path + _BEST_SUFFIX
    try:
        with PDFDocument(path) as src:       # raise CorruptedFileError / PasswordProtectedError
            doc = src.raw
            total_pages = src.page_count
            sample = _sample_indexes(total_pages)
            text_before = {i: len(doc[i].get_text()) for i in sample}

            stats: Optional[dict] = None
            if level != "light":
                stats = _recompress_images(doc, level, to_grayscale)
            diag = _build_diag(level, size_before, stats, total_pages)

            best_size: Optional[int] = None
            last_problem = "không xác định"
            for options in _save_variants(level):
                _save_temp(doc, tmp_path, options)
                issue = _verify_output(tmp_path, total_pages, sample, text_before)
                if issue is not None:
                    last_problem = issue
                    continue
                size = os.path.getsize(tmp_path)
                if best_size is None or size < best_size:
                    os.replace(tmp_path, best_path)
                    best_size = size
                if best_size < size_before:
                    break                     # đã nhỏ hơn bản gốc, không cần thử kiểu lưu khác
            if best_size is None:
                raise CompressError(
                    f"Kết quả nén không đạt kiểm tra ({last_problem}). "
                    "Đã hủy, file gốc giữ nguyên."
                )

        if best_size >= size_before:
            return {
                "size_before": size_before,
                "size_after": best_size,
                "percent": 0.0,
                "status": "not_smaller",
                "page_count": total_pages,
                "diag": diag,
            }

        try:
            os.replace(best_path, output_path)   # chỉ lúc này file đích mới bị thay
        except OSError as exc:
            raise FileLockedError(
                f"Không thể ghi file (có thể đang bị khóa): {output_path}"
            ) from exc

        return {
            "size_before": size_before,
            "size_after": best_size,
            "percent": (1 - best_size / size_before) * 100 if size_before else 0.0,
            "status": "ok",
            "page_count": total_pages,
            "diag": diag,
        }
    finally:
        _remove_quietly(tmp_path)
        _remove_quietly(best_path)


def has_digital_signature(path: str) -> bool:
    """True nếu file có trường chữ ký số (nén/ghi lại sẽ làm chữ ký mất hiệu lực).
    Không bao giờ raise: lỗi đọc coi như không có chữ ký (chỉ là cảnh báo phụ)."""
    try:
        with PDFDocument(path) as doc:
            # get_sigflags(): -1 = không phải form; 0 = không có chữ ký; bit 0 = có chữ ký
            flags = doc.raw.get_sigflags()
            return flags > 0 and bool(flags & 1)
    except Exception:
        return False


def render_compressed_page(path: str, page_index: int, level: str,
                           to_grayscale: bool = False, target_width: int = 794) -> bytes:
    """Dùng cho nút "Xem thử": nén RIÊNG 1 trang trong bộ nhớ (không ghi file nào) theo
    mức đã chọn rồi render PNG ở độ rộng `target_width` px để so sánh với trang gốc.

    Mức "light" không đụng vào ảnh nên ảnh trả về giống trang gốc."""
    _check_level(level)
    with PDFDocument(path) as src:
        if not (0 <= page_index < src.page_count):
            raise ValueError(f"Trang không hợp lệ: {page_index + 1}")
        one = fitz.open()
        try:
            one.insert_pdf(src.raw, from_page=page_index, to_page=page_index)
            if level != "light":
                _recompress_images(one, level, to_grayscale)
            page = one[0]
            zoom = target_width / page.rect.width if page.rect.width else 1.0
            return page.get_pixmap(matrix=fitz.Matrix(zoom, zoom)).tobytes("png")
        finally:
            one.close()