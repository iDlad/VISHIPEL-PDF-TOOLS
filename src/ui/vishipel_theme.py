"""
Bảng màu và style dùng chung cho toàn bộ ứng dụng Vishipel PDF Tools.
Mọi module UI khác lấy màu/kích thước từ đây, không tự ý khai báo mã màu riêng lẻ
để tránh lệch màu giữa các màn hình.
"""
from __future__ import annotations

# ----- Bảng màu chính thức (xem 01_dac_ta_giao_dien.md mục 5) -----
COLOR_CONTENT_BG = "#F8FAFC"       # Nền khung nội dung bên phải
COLOR_SIDEBAR_BG = "#0F172A"       # Nền sidebar
COLOR_SIDEBAR_TEXT = "#FFFFFF"     # Chữ thường trên sidebar
COLOR_ACCENT = "#FA9005"           # Accent: mục đang chọn + nút hành động chính
COLOR_ACCENT_LIGHT = "#FFF1DE"     # Tô nền nhạt (VD: thumbnail đang được chọn)
COLOR_TEXT_PRIMARY = "#111827"     # Chữ chính trên nền sáng
COLOR_TEXT_SECONDARY = "#6B7280"   # Chữ phụ / ghi chú
COLOR_SUCCESS = "#16A34A"          # Trạng thái thành công
COLOR_ERROR = "#DC2626"            # Trạng thái lỗi

# ----- Viền dùng chung -----
COLOR_BORDER = "#E5E7EB"           # Viền nhạt: khung card, khung cuộn, dashed drop-zone
COLOR_BORDER_STRONG = "#D1D5DB"    # Viền đậm hơn: input, checkbox, nút phụ (Clear...)

# ----- Kích thước / font dùng chung -----
SIDEBAR_WIDTH = 200
FONT_FAMILY = "Segoe UI"

# ----- Chuẩn control dùng chung cho MỌI tính năng (Split/Merge/Edit/Insert/Rename) -----
# Áp dụng cho label, QSpinBox, QPushButton, QToolButton... nằm trên cùng 1 hàng thao tác
# (VD: hàng nút hành động cuối khung). Luôn setFixedHeight(CONTROL_HEIGHT) thay vì dựa
# vào padding/font để canh chiều cao — tránh lệch 1-2px giữa các loại widget khác nhau.
CONTROL_HEIGHT = 38
CORNER_RADIUS = 8

# Stylesheet toàn cục (QSS) áp dụng cho cả app.
GLOBAL_STYLESHEET = f"""
QWidget {{
    font-family: "{FONT_FAMILY}";
    font-size: 14px;
}}
QMainWindow {{
    background-color: {COLOR_CONTENT_BG};
}}
"""