import os
import requests
import uuid
import time
import json
from fpdf import FPDF

# Cấu hình API endpoint
API_URL = "http://localhost:8000"

def create_test_pdf_file():
    """
    Tạo một file PDF đơn giản và lưu vào tệp tạm thời để kiểm thử.
    Trả về đường dẫn của file tạm thời.
    """
    file_path = f"test_document_{int(time.time())}.pdf"
    pdf = FPDF('P', 'mm', 'A4')
    pdf.add_page()
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(200, 10, 'Bao cao kiem thu tai', 0, 1, 'C')
    pdf.ln(10)
    pdf.set_font('Arial', '', 12)
    pdf.multi_cell(0, 5, "Day la mot tai lieu PDF mau de kiem thu. No co dinh dang chuan de tranh cac loi xu ly file.")
    pdf.output(file_path)
    return file_path

def test_upload_and_retrieve():
    """
    Kiểm thử luồng tải lên và lấy thông tin tài liệu.
    """
    print("Bắt đầu kiểm thử tải lên và lấy thông tin...")
    
    # Tạo một UID duy nhất cho người dùng
    user_id = str(uuid.uuid4())
    print(f"Sử dụng UID: {user_id}")

    # Tạo một file PDF giả
    pdf_file_path = create_test_pdf_file()

    # Tải tài liệu lên
    print("Đang tải tài liệu lên...")
    with open(pdf_file_path, "rb") as f:
        files = {'file': (os.path.basename(pdf_file_path), f, 'application/pdf')}
        data = {'uid': user_id}
        upload_response = requests.post(f"{API_URL}/api/v1/document", files=files, data=data)
    
    # Xóa file tạm thời
    try:
        os.remove(pdf_file_path)
    except FileNotFoundError:
        pass

    # Kiểm tra phản hồi tải lên
    if upload_response.status_code == 200:
        print("Tải lên thành công!")
    else:
        print(f"Lỗi tải lên: {upload_response.status_code} - {upload_response.text}")
        return

    # Chờ xử lý hoàn tất (vì nó chạy trên luồng khác)
    time.sleep(5) 

    # Gửi câu truy vấn
    print("Đang gửi câu truy vấn...")
    query_text = "Nội dung của tài liệu là gì?"
    query_data = {'query_text': query_text, 'uid': user_id}
    retrieve_response = requests.post(f"{API_URL}/api/v1/retrieve", json=query_data)
    
    # Kiểm tra phản hồi lấy thông tin
    if retrieve_response.status_code == 200:
        print("Lấy thông tin thành công!")
        print("Kết quả:", retrieve_response.json())
    else:
        print(f"Lỗi lấy thông tin: {retrieve_response.status_code} - {retrieve_response.text}")

def test_single_document_limit():
    """
    Kiểm thử giới hạn một tài liệu cho mỗi người dùng.
    """
    print("\nBắt đầu kiểm thử giới hạn một tài liệu...")
    user_id = str(uuid.uuid4())
    print(f"Sử dụng UID: {user_id}")
    
    pdf_file_path1 = create_test_pdf_file()
    pdf_file_path2 = create_test_pdf_file()

    # Tải tài liệu đầu tiên
    print("Tải tài liệu đầu tiên...")
    with open(pdf_file_path1, "rb") as f:
        files = {'file': (os.path.basename(pdf_file_path1), f, 'application/pdf')}
        data = {'uid': user_id}
        requests.post(f"{API_URL}/api/v1/document", files=files, data=data)

    time.sleep(5) # Chờ xử lý

    # Lấy thông tin từ tài liệu đầu tiên
    query_data1 = {'query_text': "Nội dung của tài liệu đầu tiên?", 'uid': user_id}
    retrieve_response1 = requests.post(f"{API_URL}/api/v1/retrieve", json=query_data1)
    print(f"Lấy thông tin từ tài liệu 1: {retrieve_response1.status_code}")

    # Tải tài liệu thứ hai
    print("Tải tài liệu thứ hai...")
    with open(pdf_file_path2, "rb") as f:
        files = {'file': (os.path.basename(pdf_file_path2), f, 'application/pdf')}
        data = {'uid': user_id}
        requests.post(f"{API_URL}/api/v1/document", files=files, data=data)
    
    time.sleep(5) # Chờ xử lý

    # Lấy thông tin từ tài liệu đầu tiên (đáng lẽ phải không còn)
    query_data1_after = {'query_text': "Nội dung của tài liệu đầu tiên?", 'uid': user_id}
    retrieve_response1_after = requests.post(f"{API_URL}/api/v1/retrieve", json=query_data1_after)
    print(f"Lấy thông tin từ tài liệu 1 sau khi tải tài liệu 2: {retrieve_response1_after.status_code}")
    if retrieve_response1_after.status_code == 404:
        print("Kiểm thử thành công: Tài liệu đầu tiên đã bị xóa.")
    else:
        print("Kiểm thử thất bại: Tài liệu đầu tiên vẫn còn tồn tại.")

    # Lấy thông tin từ tài liệu thứ hai
    query_data2 = {'query_text': "Nội dung của tài liệu thứ hai?", 'uid': user_id}
    retrieve_response2 = requests.post(f"{API_URL}/api/v1/retrieve", json=query_data2)
    print(f"Lấy thông tin từ tài liệu 2: {retrieve_response2.status_code}")
    if retrieve_response2.status_code == 200:
        print("Kiểm thử thành công: Có thể truy vấn tài liệu thứ hai.")
    else:
        print("Kiểm thử thất bại: Không thể truy vấn tài liệu thứ hai.")

    # Xóa các file tạm thời
    try:
        os.remove(pdf_file_path1)
        os.remove(pdf_file_path2)
    except FileNotFoundError:
        pass

if __name__ == "__main__":
    test_upload_and_retrieve()
    test_single_document_limit()
