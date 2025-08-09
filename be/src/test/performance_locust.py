from locust import HttpUser, task, between
import os

class RAGUser(HttpUser):
    wait_time = between(1, 3)  # mỗi request cách nhau 1-3 giây

    def on_start(self):
        # Chuẩn bị PDF giả để upload
        self.uid = f"user_{os.getpid()}_{self.environment.runner.user_count}"
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="Test PDF Content", ln=True)
        pdf.output("locust_test.pdf")

        with open("locust_test.pdf", "rb") as f:
            self.client.post(
                "/api/v1/document",
                data={"uid": self.uid},
                files={"file": ("locust_test.pdf", f, "application/pdf")}
            )

    @task(3)  # Tỉ lệ chạy cao hơn
    def retrieve(self):
        self.client.post(
            "/api/v1/retrieve",
            data={"query_text": "Hello?", "uid": self.uid}
        )

    @task(1)  # Ít hơn
    def upload_new_file(self):
        with open("locust_test.pdf", "rb") as f:
            self.client.post(
                "/api/v1/document",
                data={"uid": self.uid},
                files={"file": ("locust_test.pdf", f, "application/pdf")}
            )
