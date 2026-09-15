"""
Vishipel PDF Tools — src/logger.py

Ghi log nội bộ vào app.log — không hiện traceback kỹ thuật cho người dùng,
chỉ dùng để debug sau (xem 02_dac_ta_tinh_nang.md mục 6, 04_kien_truc_module_va_flow.md mục 3).
"""
from __future__ import annotations

import logging
import os

_LOG_DIR = os.path.join(os.getcwd(), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")

os.makedirs(_LOG_DIR, exist_ok=True)

_logger = logging.getLogger("vishipel_pdf_tools")
_logger.setLevel(logging.DEBUG)

if not _logger.handlers:
    _handler = logging.FileHandler(_LOG_FILE, encoding="utf-8")
    _handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    _logger.addHandler(_handler)


def log_info(message: str) -> None:
    """Ghi log thao tác thành công vào app.log."""
    _logger.info(message)


def log_error(message: str, exc: Exception | None = None) -> None:
    """Ghi log lỗi kèm traceback (nếu có) vào app.log — không hiện traceback cho người dùng."""
    if exc is not None:
        _logger.error(message, exc_info=exc)
    else:
        _logger.error(message)
