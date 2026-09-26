"""
/src/rename_engine.py
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
# 1. Hồ sơ mẫu (profile) 
# =============================================================================

class ProfileStoreError(Exception):
    """Không đọc/ghi được file rename_profiles.json (hỏng JSON, mất quyền ghi,
    ổ đĩa đầy...)."""

def load_profiles(json_path: str) -> List[dict]:

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

    directory = os.path.dirname(json_path) or "."
    tmp_path = os.path.join(directory, f".{os.path.basename(json_path)}.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, json_path)
    except OSError as exc:
        raise ProfileStoreError(f"Không ghi được file hồ sơ mẫu: {json_path} ({exc})") from exc


# =============================================================================
# 2. Sinh tên file theo hồ sơ mẫu 
# =============================================================================

def generate_name(profile: dict, values: dict, batch_size: int = 1) -> str:

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

    manual_values = manual_values or {}
    names: List[str] = []
    for row_index in range(batch_size):
        values = compute_row_values(profile, base_values, row_index)
        if row_index in manual_values:
            values["manual_sample"] = manual_values[row_index]
        names.append(generate_name(profile, values, batch_size=batch_size))
    return names


# =============================================================================
# 3. Thực thi đổi tên hàng loạt
# =============================================================================

class ConflictAction:

    OVERWRITE = "overwrite"
    RENAME = "rename"
    CANCEL = "cancel"


@dataclass
class RenameItemResult:
    source_path: str
    original_name: str
    final_name: Optional[str]      
    final_path: Optional[str]
    status: str                    
    message: str = ""


@dataclass
class RenameBatchResult:
    items: List[RenameItemResult] = field(default_factory=list)

    aborted: bool = False

    @property
    def success_count(self) -> int:
        return sum(1 for it in self.items if it.status == "ok")

    @property
    def error_count(self) -> int:
        return sum(1 for it in self.items if it.status == "error")


def _copy_one_file(source_path: str, dest_path: str) -> None:

    try:
        shutil.copy2(source_path, dest_path)
    except OSError as exc:
        raise FileLockedError(f"Không thể ghi file (có thể đang bị khóa): {dest_path}") from exc


def apply_rename_batch(
    files: List[Tuple[str, str]],         
    new_names: List[str],                   
    output_dir: str,
    resolve_conflict: Callable[[str, bool], Tuple[str, Optional[str]]],
) -> RenameBatchResult:

    if len(files) != len(new_names):
        raise ValueError("files và new_names phải cùng độ dài")

    result = RenameBatchResult()
    used_names: Set[str] = set()  
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