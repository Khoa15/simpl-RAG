import json
import pickle
import time
import logging
from celery import Celery
from redis import Redis

from src.rag.preprocess import PDFLoader, SplittingDocuments, StoringDocuments

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

redis_client = Redis(host="localhost", port=6379, db=1, decode_responses=False)

celery_app = Celery(
    "worker",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0"
)

celery_app.conf.update(
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_track_started=True,
    worker_max_tasks_per_child=100,
    broker_transport_options={'visibility_timeout': 3600}
)

@celery_app.task(bind=True)
def process_document(self, file_content: bytes, uid):
    """
    Tác vụ Celery để xử lý tài liệu.
    Tác vụ này nhận nội dung file dưới dạng bytes.
    """
    logger.info(f"Task {self.request.id}: Starting to process document for uid={uid}")
    
    try:
        # Bước 1: Tải và chia nhỏ tài liệu từ nội dung bytes
        docs = PDFLoader(file_content)
        splitted_docs = SplittingDocuments(docs)

        # Bước 2: Tạo vector store
        vectorstores = StoringDocuments(splitted_docs)
        
        # Bước 3: Serialize và lưu vector store vào Redis
        serialized_vs = pickle.dumps(vectorstores)
        redis_client.set(f"user:{uid}:vectorstore", serialized_vs, ex=1800)

        # Bước 4: Cập nhật trạng thái người dùng trong Redis
        redis_client.set(f"user:{uid}:status", "ready", ex=1800)
        
        logger.info(f"Task {self.request.id}: Successfully processed document for uid={uid}")

        return "success"
    except Exception as e:
        logger.error(f"Task {self.request.id}: Failed to process document for uid={uid} with error: {e}")
        redis_client.set(f"user:{uid}:status", f"error: {str(e)}", ex=1800)
        self.update_state(state='FAILURE', meta={'exc': str(e)})
        raise e
