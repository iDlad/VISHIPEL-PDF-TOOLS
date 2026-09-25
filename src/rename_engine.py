"""
Vishipel PDF Tools — src/rename_engine.py

Lõi xử lý cho tính năng Đổi tên (Rename):
  1. Đọc/ghi hồ sơ mẫu (profile) vào rename_profiles.json.
  2. Sinh tên file mới theo hồ sơ mẫu (Vận hành / Phát sinh) — đúng quy tắc
     xoay vòng Ca/Ngày và đệm số "Số thứ tự tự tăng" đã CHỐT ở
     08_dac_ta_doi_ten.md mục 3, 4.
  3. Thực thi đổi tên hàng loạt: luôn COPY file gốc sang thư mục đích với tên
     mới — KHÔNG BAO GIỜ đụng/ghi đè/xóa file gốc (đúng quy ước chung
     02_dac_ta_tinh_nang.md mục 0), xử lý trùng tên theo mục 8 (Ghi đè / Đổi
     tên khác / Hủy — Hủy thì dừng hẳn toàn bộ thao tác, không ghi tiếp các
     file phía sau).

Toàn bộ nội dung file này THUẦN LOGIC, không import PySide6 — cùng nguyên tắc
đã áp dụng cho pdf_core.py (xem 04_kien_truc_module_va_flow.md mục 1), để có
thể tự test độc lập bằng script trước khi gắn vào rename_widget.py.

File này HOÀN TOÀN MỚI — không sửa bất kỳ dòng nào của pdf_core.py. Chỉ import
lại đúng 1 exception có sẵn (FileLockedError) để widget xử lý lỗi ghi file
thống nhất theo cùng 1 luồng lỗi giữa mọi tính năng (đúng nguyên tắc chung ở
đầu 04_kien_truc_module_va_flow.md — không tạo thêm exception trùng lặp không
cần thiết cho cùng 1 loại lỗi).
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set, Tuple

from src.pdf_core import FileLockedError


# =============================================================================
# 1. Hồ sơ mẫu (profile) — đọc/ghi rename_profiles.json (08_dac_ta_doi_ten.md mục 2)
# =============================================================================

class ProfileStoreError(Exception):
    """Không đọc/ghi được file rename_profiles.json (hỏng JSON, mất quyền ghi,
    ổ đĩa đầy...)."""


def load_profiles(json_path: str) -> List[dict]:
    """Đọc danh sách hồ sơ mẫu từ file JSON.

    - Nếu file chưa tồn tại: tự tạo file rỗng `[]` rồi trả về danh sách rỗng
      (đúng 08_dac_ta_doi_ten.md mục 2 — file trống cho tới khi đại ca tạo hồ
      sơ đầu tiên qua UI).
    - Nếu file tồn tại nhưng nội dung hỏng (JSON lỗi cú pháp, hoặc không phải
      1 list): KHÔNG tự xóa/ghi đè file cũ (tránh mất dữ liệu hồ sơ thật của
      đại ca chỉ vì 1 lỗi đọc tạm thời) — raise ProfileStoreError để widget tự
      quyết định thông báo gì cho người dùng."""
    if not os.path.exists(json_path):
        save_profiles(json_path, [])
        return []

    try:
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileStoreError(f"Không đọc được file hồ sơ mẫu: {json_path} ({exc})") from exc

    if not isinstance(data, list):
        raise ProfileStoreError(f"Nội dung file hồ sơ mẫu không hợp lệ (không phải danh sách): {json_path}")
    return data


def save_profiles(json_path: str, profiles: List[dict]) -> None:
    """Ghi đè toàn bộ danh sách hồ sơ mẫu ra file JSON (hồ sơ mẫu là 1 danh
    sách nhỏ, không cần merge từng phần — mỗi lần Tạo/Sửa/Xóa ghi lại cả file).

    Ghi ra file tạm cùng thư mục rồi `os.replace()` sang đúng tên thật, để
    tránh trường hợp app bị tắt đột ngột giữa lúc đang ghi làm hỏng luôn file
    JSON cũ (os.replace là thao tác atomic trên cùng 1 ổ đĩa)."""
    directory = os.path.dirname(json_path) or "."
    tmp_path = os.path.join(directory, f".{os.path.basename(json_path)}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, json_path)
    except OSError as exc:
        raise ProfileStoreError(f"Không ghi được file hồ sơ mẫu: {json_path} ({exc})") from exc


# =============================================================================
# 2. Sinh tên file theo hồ sơ mẫu (08_dac_ta_doi_ten.md mục 3, 4)
# =============================================================================

def generate_name(profile: dict, values: dict, batch_size: int = 1) -> str:
    """Sinh 1 tên file .pdf từ hồ sơ mẫu + giá trị hiện tại (đã tính batch
    progression qua compute_row_values() bên dưới, nếu cần).

    - Vận hành: `{Ngày}[_{Ca}]_{Văn bản cố định}` (mục 3).
    - Phát sinh: ghép tối đa 4 khối theo đúng thứ tự đã lưu trong hồ sơ (mục
      4). Đệm số của khối "Số thứ tự tự tăng" = `max(2, số chữ số của tổng số
      file trong batch)`, tính 1 LẦN cho toàn bộ batch (CHỐT — không đổi đệm
      giữa chừng, VD batch 150 file dùng đệm 3 chữ số ngay từ `001`)."""
    ext = ".pdf"
    if profile.get("type") == "van_hanh":
        date_value: datetime.date = values.get("date") or datetime.date.today()
        parts = [date_value.strftime("%d%m%Y")]
        if profile.get("has_ca"):
            ca_index = values.get("ca_index", 1)
            parts.append(f"K{ca_index}")
        fixed_text = (profile.get("fixed_text") or "").strip()
        if fixed_text:
            parts.append(fixed_text)
        return "_".join(parts) + ext

    segments: List[str] = []
    pad_width = max(2, len(str(max(1, batch_size))))
    for block in profile.get("blocks", []):
        btype = block.get("type")
        cfg = block.get("config", {})
        if btype == "fixed_text":
            value = (cfg.get("value") or "").strip()
            if value:
                segments.append(value)
        elif btype == "auto_number":
            start = values.get("auto_number_start", cfg.get("start", 1))
            segments.append(str(start).zfill(pad_width))
        elif btype == "date":
            date_value = values.get("date") or datetime.date.today()
            segments.append(date_value.strftime("%d%m%Y"))
        elif btype == "manual":
            segments.append(values.get("manual_sample") or "TenNhapTay")
    return ("_".join(segments) if segments else "ten_file") + ext


def compute_row_values(profile: dict, base_values: dict, row_index: int) -> dict:
    """Tính giá trị Ngày/Ca/Số thứ tự cho file thứ `row_index` (0-based) trong
    batch, dựa trên giá trị khởi tạo `base_values` (nhập ở Form Cột B) và quy
    tắc xoay vòng/tăng dần đã CHỐT (mục 3, 4):

    - Vận hành có Ca: hết `KN` của 1 ngày quay lại `K1`, đồng thời Ngày +1.
    - Vận hành không Ca: mỗi file kế tiếp +1 ngày.
    - Phát sinh: "Số thứ tự tự tăng" += `step * row_index`; khối "Ngày" chỉ
      tăng dần nếu bật "Tăng dần mỗi file", ngược lại giữ nguyên 1 ngày cho cả
      batch. Khối "Văn bản cố định"/"Nhập tay" không có progression (nhập tay
      điền riêng từng dòng ở bảng preview)."""
    values = dict(base_values)
    if profile.get("type") == "van_hanh":
        base_date: datetime.date = values.get("date") or datetime.date.today()
        if profile.get("has_ca"):
            ca_count = profile.get("ca_count", 1) or 1
            start_ca = values.get("ca_index", 1)
            absolute = (start_ca - 1) + row_index
            values["ca_index"] = (absolute % ca_count) + 1
            values["date"] = base_date + datetime.timedelta(days=absolute // ca_count)
        else:
            values["date"] = base_date + datetime.timedelta(days=row_index)
    else:
        start = values.get("auto_number_start")
        step = values.get("auto_number_step", 1)
        if start is not None:
            values["auto_number_start"] = start + row_index * step
        for block in profile.get("blocks", []):
            if block.get("type") == "date" and block.get("config", {}).get("increment_daily"):
                base_date = values.get("date") or datetime.date.today()
                values["date"] = base_date + datetime.timedelta(days=row_index)
    return values


def generate_batch_names(
    profile: dict,
    base_values: dict,
    batch_size: int,
    manual_values: Optional[Dict[int, str]] = None,
) -> List[str]:
    """Sinh sẵn toàn bộ danh sách tên file mới cho cả batch trong 1 lần gọi —
    dùng lúc thật sự ghi file (đảm bảo đệm số auto_number tính đúng theo
    batch_size thật). `manual_values` (nếu có) là giá trị người dùng đã gõ tay
    ở bảng preview cho từng dòng (0-based index)."""
    manual_values = manual_values or {}
    names: List[str] = []
    for row_index in range(batch_size):
        values = compute_row_values(profile, base_values, row_index)
        if row_index in manual_values:
            values["manual_sample"] = manual_values[row_index]
        names.append(generate_name(profile, values, batch_size=batch_size))
    return names


# =============================================================================
# 3. Thực thi đổi tên hàng loạt — luôn COPY sang thư mục đích với tên mới,
#    KHÔNG BAO GIỜ đụng/xóa file gốc (02_dac_ta_tinh_nang.md mục 0).
# =============================================================================

class ConflictAction:
    """3 lựa chọn khi tên file đích đã tồn tại (02_dac_ta_tinh_nang.md mục 8)."""
    OVERWRITE = "overwrite"
    RENAME = "rename"
    CANCEL = "cancel"


@dataclass
class RenameItemResult:
    source_path: str
    original_name: str
    final_name: Optional[str]      # None nếu bị hủy trước khi kịp ghi
    final_path: Optional[str]
    status: str                     # "ok" | "error" | "cancelled"
    message: str = ""


@dataclass
class RenameBatchResult:
    items: List[RenameItemResult] = field(default_factory=list)
    # True nếu người dùng bấm "Hủy" ở 1 file đang trùng tên — CHỐT: dừng hẳn
    # toàn bộ thao tác ngay tại đó, KHÔNG ghi tiếp các file phía sau. Các file
    # đã ghi xong ở những lượt trước đó trong cùng batch KHÔNG bị hoàn tác.
    aborted: bool = False

    @property
    def success_count(self) -> int:
        return sum(1 for it in self.items if it.status == "ok")

    @property
    def error_count(self) -> int:
        return sum(1 for it in self.items if it.status == "error")


def _copy_one_file(source_path: str, dest_path: str) -> None:
    """Copy nguyên vẹn 1 file (KHÔNG move) — giữ file gốc nguyên trạng tuyệt
    đối. Chuyển mọi lỗi ghi (đích đang bị khóa bởi chương trình khác, hết dung
    lượng, không có quyền ghi...) thành FileLockedError để widget xử lý thống
    nhất theo đúng 1 luồng lỗi, giống pdf_core._safe_save()."""
    try:
        shutil.copy2(source_path, dest_path)
    except OSError as exc:
        raise FileLockedError(f"Không thể ghi file (có thể đang bị khóa): {dest_path}") from exc


def apply_rename_batch(
    files: List[Tuple[str, str]],           # (source_path, original_name), đúng thứ tự Cột A
    new_names: List[str],                    # cùng độ dài files — lấy từ generate_batch_names()
    output_dir: str,
    resolve_conflict: Callable[[str, bool], Tuple[str, Optional[str]]],
) -> RenameBatchResult:
    """Ghi từng file theo đúng thứ tự trong `files`.

    `resolve_conflict(candidate_name, same_as_source)` do widget cung cấp để
    hiện dialog Ghi đè/Đổi tên khác/Hủy (mục 8) — hàm này THUẦN LOGIC, không tự
    vẽ gì (đúng nguyên tắc pdf_core.py). Phải trả về
    `(ConflictAction, tên_mới_nếu_chọn_Đổi_tên_khác_hoặc_None)`.

    `same_as_source=True` nghĩa là tên/thư mục đích trùng ĐÚNG file gốc đang
    đổi tên — trường hợp này widget PHẢI không cho chọn "Ghi đè" (sẽ phá hủy
    file gốc, vi phạm quy ước chung mục 0), chỉ còn Đổi tên khác/Hủy.

    Gặp lỗi ghi file (khóa, hết dung lượng...) ở 1 file: ghi nhận lỗi, TIẾP TỤC
    xử lý các file còn lại (đúng mục 8 — không crash, không dừng cả batch chỉ
    vì 1 file lỗi kỹ thuật). Chỉ dừng hẳn khi người dùng CHỦ ĐỘNG bấm Hủy."""
    if len(files) != len(new_names):
        raise ValueError("files và new_names phải cùng độ dài")

    result = RenameBatchResult()
    used_names: Set[str] = set()  # tên đã ghi THÀNH CÔNG trong batch này — tránh 1 file mới đè lên đúng file mới vừa tạo

    for (source_path, original_name), desired_name in zip(files, new_names):
        candidate = desired_name
        while True:
            dest_path = os.path.join(output_dir, candidate)
            same_as_source = os.path.abspath(dest_path) == os.path.abspath(source_path)
            conflict = same_as_source or candidate in used_names or os.path.exists(dest_path)
            if not conflict:
                break

            action, renamed_to = resolve_conflict(candidate, same_as_source)
            if action == ConflictAction.CANCEL:
                result.aborted = True
                result.items.append(RenameItemResult(
                    source_path, original_name, None, None, "cancelled",
                    "Người dùng hủy khi gặp trùng tên — dừng toàn bộ thao tác đổi tên.",
                ))
                return result
            if action == ConflictAction.RENAME and renamed_to:
                candidate = renamed_to
                continue
            # OVERWRITE (chỉ khả dụng khi same_as_source=False) — chấp nhận
            # ghi đè đúng candidate hiện tại, thoát vòng lặp kiểm tra trùng.
            break

        dest_path = os.path.join(output_dir, candidate)
        try:
            _copy_one_file(source_path, dest_path)
        except FileLockedError as exc:
            result.items.append(RenameItemResult(
                source_path, original_name, candidate, dest_path, "error", str(exc)
            ))
            continue
        except OSError as exc:
            result.items.append(RenameItemResult(
                source_path, original_name, candidate, dest_path, "error", str(exc)
            ))
            continue

        used_names.add(candidate)
        result.items.append(RenameItemResult(source_path, original_name, candidate, dest_path, "ok"))

    return result