import asyncio
import json
import logging
import pickle  # Dùng để serialize/deserialize vectorstore
import time
import os  # Thêm import os để quản lý file
from typing import Annotated, Union
from fastapi import FastAPI, Form, UploadFile, HTTPException
from fastapi.concurrency import asynccontextmanager
from fastapi.datastructures import FormData
from fastapi.middleware.cors import CORSMiddleware
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from celery.result import AsyncResult
from redis.asyncio import Redis as AsyncRedis
from redis import Redis
from src.celery_worker import process_document
from src.rag.preprocess import QuotaRateLimit, RetrieveDocument
import dotenv
dotenv.load_dotenv()
USE_MOCK_EMBEDDINGS = os.environ.get("USE_MOCK_EMBEDDINGS", "False").lower() in ("true", "1", "t")

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

# TTL (Time-to-live) cho dữ liệu người dùng trong Redis.
# 1800 giây = 30 phút.
INACTIVITY_TTL = 1800

async_redis_client = AsyncRedis(host="redis", port=6379, db=1, decode_responses=True)
async_redis_binary_client = AsyncRedis(host="redis", port=6379, db=1, decode_responses=False)

# Cache cục bộ để lưu trữ vectorstore đã được giải mã,
# giúp tránh việc tải và giải mã lại nhiều lần.
users_vectorstores_cache = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")
    try:
        yield
    finally:
        pass

# Khởi tạo FastAPI app
app = FastAPI(lifespan=lifespan)

# Cấu hình CORS
origins = ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Endpoint test
@app.get("/")
def read_root():
    return {"Hello": "World"}

# Endpoint xử lý tải file
@app.post("/api/v1/document")
async def get_document_from_client(file: UploadFile | None, uid: Annotated[str, Form()]):
    if not file:
        raise HTTPException(status_code=400, detail="No upload file sent")
    
    # --- Bắt đầu logic Rate-Limiting ---
    # Đọc thời gian yêu cầu gần nhất từ Redis
    last_request_time_str = await async_redis_client.get(f"user:{uid}:doc_last_request")
    current_time = time.time()
    
    if last_request_time_str:
        last_request_time = float(last_request_time_str)
        # Kiểm tra nếu thời gian giữa hai yêu cầu nhỏ hơn 3 giây
        if (current_time - last_request_time) < 3:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait before uploading another document.")
    
    # Cập nhật thời gian yêu cầu gần nhất
    await async_redis_client.set(f"user:{uid}:doc_last_request", current_time, ex=INACTIVITY_TTL)
    # --- Kết thúc logic Rate-Limiting ---

    try:
        contents = await file.read()
        
        # Gửi trực tiếp nội dung bytes đến Celery worker
        task = process_document.delay(contents, uid)
            
        await async_redis_client.set(f"user:{uid}:status", "processing", ex=INACTIVITY_TTL)
        
        return {
            'status': 202,
            'message': 'Upload accepted, processing in background.',
            'task_id': task.id
        }
    except Exception as e:
        logger.error(f"Error processing document upload: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")

# Endpoint lấy thông tin
@app.post('/api/v1/retrieve')
async def retrieve_documents(query_text: Annotated[str, Form()], uid: Annotated[str, Form()]):
    # --- Bắt đầu logic Rate-Limiting ---
    # Đọc thời gian yêu cầu gần nhất từ Redis
    last_request_time_str = await async_redis_client.get(f"user:{uid}:retrieve_last_request")
    current_time = time.time()
    
    if last_request_time_str:
        last_request_time = float(last_request_time_str)
        # Kiểm tra nếu thời gian giữa hai yêu cầu nhỏ hơn 3 giây
        if (current_time - last_request_time) < 3:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait before asking another question.")
    
    # Cập nhật thời gian yêu cầu gần nhất
    await async_redis_client.set(f"user:{uid}:retrieve_last_request", current_time, ex=INACTIVITY_TTL)
    # --- Kết thúc logic Rate-Limiting ---

    status = await async_redis_client.get(f"user:{uid}:status")
    
    if status is None:
        raise HTTPException(status_code=404, detail="User session not found. Please upload a document first.")
    
    if status != "ready":
        raise HTTPException(status_code=400, detail="Document is still being processed. Please wait.")
    
    try:
        # Tối ưu hóa hiệu suất: Kiểm tra cache cục bộ trước
        vectorstore = users_vectorstores_cache.get(uid)
        
        if not vectorstore:
            # Nếu chưa có trong cache, tải từ Redis và giải mã
            serialized_vectorstore = await async_redis_binary_client.get(f"user:{uid}:vectorstore")
            
            if not serialized_vectorstore:
                raise HTTPException(status_code=404, detail="Vectorstore data not found in Redis.")
            
            def deserialize_vectorstore_sync(data):
                return pickle.loads(data)

            vectorstore = await asyncio.to_thread(deserialize_vectorstore_sync, serialized_vectorstore)
            
            # Lưu vào cache để sử dụng cho các lần sau
            users_vectorstores_cache[uid] = vectorstore
        retriever = vectorstore
        if not USE_MOCK_EMBEDDINGS:
            retriever = vectorstore.as_retriever()
        
        result = await asyncio.to_thread(RetrieveDocument, query_text, retriever)

        return {
            'status': 200,
            'question': query_text,
            'message': result
        }
    except QuotaRateLimit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded, please wait.")
    except Exception as e:
        logger.error(f"Error retrieving document: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.post('/api/v1/retrieve/mock')
async def retrieve_documents_mock(query_text: Annotated[str, Form()], uid: Annotated[str, Form()]):
    """
    Endpoint này chỉ dành cho mục đích kiểm thử và trả về phản hồi giả lập.
    Không thực hiện các tác vụ tốn tài nguyên.
    """
    logger.info(f"Nhận yêu cầu mock retrieve cho câu hỏi: '{query_text}'")
    
    

    # --- Bắt đầu logic Rate-Limiting ---
    # Đọc thời gian yêu cầu gần nhất từ Redis
    last_request_time_str = await async_redis_client.get(f"user:{uid}:retrieve_last_request")
    current_time = time.time()
    
    if last_request_time_str:
        last_request_time = float(last_request_time_str)
        # Kiểm tra nếu thời gian giữa hai yêu cầu nhỏ hơn 3 giây
        if (current_time - last_request_time) < 3:
            raise HTTPException(status_code=429, detail="Too many requests. Please wait before asking another question.")
    
    # Cập nhật thời gian yêu cầu gần nhất
    await async_redis_client.set(f"user:{uid}:retrieve_last_request", current_time, ex=INACTIVITY_TTL)
    # --- Kết thúc logic Rate-Limiting ---

    status = await async_redis_client.get(f"user:{uid}:status")
    
    if status is None:
        raise HTTPException(status_code=404, detail="User session not found. Please upload a document first.")
    
    if status != "ready":
        raise HTTPException(status_code=400, detail="Document is still being processed. Please wait.")
    
    try:
        # Tối ưu hóa hiệu suất: Kiểm tra cache cục bộ trước
        vectorstore = users_vectorstores_cache.get(uid)
        
        if not vectorstore:
            # Nếu chưa có trong cache, tải từ Redis và giải mã
            serialized_vectorstore = await async_redis_binary_client.get(f"user:{uid}:vectorstore")
            
            if not serialized_vectorstore:
                raise HTTPException(status_code=404, detail="Vectorstore data not found in Redis.")
            
            def deserialize_vectorstore_sync(data):
                return pickle.loads(data)

            vectorstore = await asyncio.to_thread(deserialize_vectorstore_sync, serialized_vectorstore)
            
            # Lưu vào cache để sử dụng cho các lần sau
            users_vectorstores_cache[uid] = vectorstore
        

        # Dữ liệu giả lập cho phản hồi
        mock_responses = {
            "default": "Đây là một câu trả lời giả lập. Vui lòng kiểm tra lại câu hỏi của bạn.",
            "tên của tôi là gì?": "Tên của bạn là Nguyễn Văn A.",
            "tôi đang ở đâu?": "Bạn đang ở Thành phố Hồ Chí Minh."
        }
        
        # Trả về phản hồi giả lập
        response_message = mock_responses.get(query_text.lower(), mock_responses["default"])
        
        return {
            'status': 200,
            'question': query_text,
            'message': response_message
        }
    except QuotaRateLimit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded, please wait.")
    except Exception as e:
        logger.error(f"Error retrieving document: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.get("/api/v1/task_status")
async def get_task_status(task_id: str):
    task_result = AsyncResult(task_id, app=process_document)
    
    if task_result.ready():
        status = "Completed"
        result = task_result.result
    else:
        status = "Processing"
        result = None
        
    return {
        "task_id": task_id,
        "status": status,
        "result": result
    }
