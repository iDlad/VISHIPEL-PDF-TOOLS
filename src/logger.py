
""" /src/logger.py """

from __future__ import annotations

import logging
import logging.handlers
import os

_LOG_DIR = os.path.join(os.getcwd(), "logs")
_LOG_FILE = os.path.join(_LOG_DIR, "app.log")


_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3

os.makedirs(_LOG_DIR, exist_ok=True)

_logger = logging.getLogger("vishipel_pdf_tools")
_logger.setLevel(logging.DEBUG)


def _make_handler() -> logging.handlers.RotatingFileHandler:

    handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
    )
    return handler


if not _logger.handlers:
    _logger.addHandler(_make_handler())


def log_info(message: str) -> None:
    """Ghi log thao tác thành công vào app.log."""
    _logger.info(message)


def log_error(message: str, exc: Exception | None = None) -> None:
    """Ghi log lỗi kèm traceback (nếu có) vào app.log — không hiện traceback cho người dùng."""
    if exc is not None:
        _logger.error(message, exc_info=exc)
    else:
        _logger.error(message)


def clear_log() -> None:

    for handler in list(_logger.handlers):
        handler.close()
        _logger.removeHandler(handler)

    # Xóa file chính + toàn bộ file backup rotation, nếu có tồn tại.
    candidates = [_LOG_FILE] + [f"{_LOG_FILE}.{i}" for i in range(1, _BACKUP_COUNT + 1)]
    for path in candidates:
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                # Hiếm khi xảy ra (VD 1 tool đọc log khác đang giữ file) — bỏ qua,
                # phần còn lại vẫn xóa được, logger vẫn hoạt động lại bình thường.
                pass

    _logger.addHandler(_make_handler())
    log_info("Đã xóa log thủ công theo yêu cầu người dùng.")