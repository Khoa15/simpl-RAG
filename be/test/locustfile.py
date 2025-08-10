import uuid
import os
import tempfile
import threading
from locust import HttpUser, task, between
from random import choice
import random as Random
from fpdf import FPDF

# Tên file PDF sẽ được tạo
PDF_TEST_FILE = "test_document.pdf"

def create_test_pdf_content():
    """
    Tạo một file PDF đơn giản và trả về nội dung của nó.
    """
    # Tạo một file tạm thời để lưu PDF
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        file_path = tmp.name
        
        # Tạo nội dung PDF bằng fpdf
        pdf = FPDF('P', 'mm', 'A4')
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.cell(200, 10, 'Bao cao kiem thu tai', 0, 1, 'C')
        pdf.ln(10)
        pdf.set_font('Arial', '', 12)
        pdf.multi_cell(0, 5, "Day la mot tai lieu PDF mau de kiem thu. No co dinh dang chuan de tranh cac loi xu ly file.")
        pdf.output(file_path)
    
    # Đọc nội dung file
    with open(file_path, "rb") as f:
        content = f.read()
    
    # Xóa file tạm thời
    os.remove(file_path)
    
    return content

# Tạo nội dung file PDF một lần duy nhất khi script được tải
pdf_file_content = create_test_pdf_content()

# Danh sách UID để tái sử dụng trong các request
processed_uids = []
# Sửa lỗi: Sử dụng threading.Lock thay cho object()
uid_lock = threading.Lock()

class WebsiteUser(HttpUser):
    wait_time = between(1, 5)

    def on_start(self):
        """Hành động khi một người dùng ảo bắt đầu."""
        self.uid = Random.randint(0, 1000)
        self.pdf_file = pdf_file_content

    @task(20)
    def retrieve_document(self):
        """Task lấy thông tin từ tài liệu đã xử lý."""
        if processed_uids:
            uid_to_retrieve = choice(processed_uids)
            query = f"query for uid {uid_to_retrieve}"
            

            # MockAPI
            with self.client.post(
                "/api/v1/retrieve/mock",
                data={"query_text": query, "uid": uid_to_retrieve},
                catch_response=True
                ) as response:
                if response.status_code == 200:
                    response.success()
                else:
                    response.failure(f"Retrieve failed with status {response.status_code}")

    @task(1)
    def upload_document(self):
        """Task tải tài liệu lên server."""
        with self.client.post(
            "/api/v1/document",
            files={"file": ("test.pdf", self.pdf_file, "application/pdf")},
            data={"uid": self.uid},
            name="/api/v1/document",
            catch_response=True
        ) as response:
        
            if response.status_code == 200:
                with uid_lock:
                    # Thêm uid vào danh sách sau khi tải lên thành công
                    if self.uid not in processed_uids:
                        processed_uids.append(self.uid)
            else:
                response.failure("Upload failed with status code: {}".format(response.status_code))
