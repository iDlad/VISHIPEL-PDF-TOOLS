===================================================================
                  QUY TRÌNH LÀM VIỆC DỰ ÁN (GIT & VENV)
===================================================================

-------------------------------------------------------------------
1. LẦN ĐẦU TIÊN CÀI ĐẶT TRÊN MÁY MỚI (CHỈ LÀM 1 LẦN TRÊN MỖI MÁY)
-------------------------------------------------------------------
Step 1: Tải code từ GitHub về máy
        git clone https://github.com/iDlad/VISHIPEL-PDF-TOOLS.git
        cd VISHIPEL-PDF-TOOLS

Step 2: Tạo môi trường ảo riêng cho máy này
        python -m venv .venv

Step 3: Kích hoạt môi trường ảo
        (Windows PowerShell): .\.venv\Scripts\Activate.ps1
        (Windows CMD):        .\.venv\Scripts\activate.bat

Step 4: Cài đặt các thư viện cần thiết
        pip install -r requirements.txt

Step 5: Chọn Interpreter trong VS Code
        Nhấn Ctrl + Shift + P -> Chọn "Python: Select Interpreter" -> Chọn .venv


-------------------------------------------------------------------
2. QUY TRÌNH HÀNG NGÀY KHI CHUYỂN ĐỔI GIỮA 2 MÁY TÍNH
-------------------------------------------------------------------

>>> KHI BẮT ĐẦU LÀM VIỆC Ở MÁY MỚI:
    Mở Terminal và kéo code mới nhất về bằng lệnh:
    
    git pull

    (Lưu ý: Nếu có thư viện mới vừa cài từ máy kia, chạy thêm: pip install -r requirements.txt)


>>> KHI KẾT THÚC CÔNG VIỆC (ĐỂ SANG MÁY KHÁC LÀM TIẾP):
    Bước 1: (Nếu có cài thêm thư viện mới) Cập nhật lại file requirements.txt
            pip freeze > requirements.txt

    Bước 2: Lưu và đẩy code lên GitHub
            git add .
            git commit -m "Noi dung thay doi code"
            git push

===================================================================