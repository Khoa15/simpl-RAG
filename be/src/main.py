import asyncio
import json
import logging
import pickle
import time
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

# Cấu hình logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)

INACTIVITY_TTL = 1800

async_redis_client = AsyncRedis(host="localhost", port=6379, db=1, decode_responses=True)
async_redis_binary_client = AsyncRedis(host="localhost", port=6379, db=1, decode_responses=False)
sync_redis_client = Redis(host="localhost", port=6379, db=1, decode_responses=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")
    try:
        yield
    finally:
        pass

app = FastAPI(lifespan=lifespan)

origins = ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/api/v1/document")
async def get_document_from_client(file: UploadFile | None, uid: Annotated[str, Form()]):
    if not file:
        raise HTTPException(status_code=400, detail="No upload file sent")
    
    try:
        # Đọc nội dung file dưới dạng bytes
        contents: bytes = await file.read()
        
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

@app.post('/api/v1/retrieve')
async def retrieve_documents(query_text: Annotated[str, Form()], uid: Annotated[str, Form()]):
    status = await async_redis_client.get(f"user:{uid}:status")
    
    if status is None:
        raise HTTPException(status_code=404, detail="User session not found. Please upload a document first.")
    
    if status != "ready":
        raise HTTPException(status_code=400, detail="Document is still being processed. Please wait.")
    
    try:
        serialized_vectorstore = await async_redis_binary_client.get(f"user:{uid}:vectorstore")
        
        if not serialized_vectorstore:
            raise HTTPException(status_code=404, detail="Vectorstore data not found in Redis.")
        
        def deserialize_vectorstore_sync(data):
            return pickle.loads(data)

        retriever = await asyncio.to_thread(deserialize_vectorstore_sync, serialized_vectorstore)
        # retriever = vectorstore.as_retriever()
        
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
