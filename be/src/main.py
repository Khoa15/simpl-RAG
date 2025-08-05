import time
import logging
import threading
from typing import Annotated, Union
from fastapi import FastAPI, Form, UploadFile
from fastapi.concurrency import asynccontextmanager
from fastapi.datastructures import FormData
from fastapi.middleware.cors import CORSMiddleware
from src.rag.preprocess import PDFLoader, QuotaRateLimit, SplittingDocuments, StoringDocuments, RetrieveDocument
from langgraph.graph import START, StateGraph
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger(__name__)



async def cleanup_task():
    while True:
        for user in users_vectorstores:
            if user['time'] < time.time() - 108000:
                del user
                


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")
    scheduler.add_job(func=cleanup_task, trigger="interval", seconds=1800)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)



app = FastAPI(lifespan=lifespan)

origins = [
    "http://localhost:3000", # frontend
]

users_vectorstores = {}

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
        return {
            'status': 200,
            "message": "No upload file sent"
            }
    
    import tempfile

    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp:
        tmp.write(await file.read())
        tmp.flush()


        docs = PDFLoader(tmp.name)

    splitted_docs = SplittingDocuments(docs)

    try:
        users_vectorstores[uid] = {
            "time": time.time(),
            "vectorstores": StoringDocuments(splitted_docs)
        }
    except MemoryError as e:
        if e.args[0] == 500:
            return {
                'status': 500,
                'message': 'Your file is too large'
            }
        else:
            return {
                'status': 500,
                'message': 'Upload failed'
            }

    return {
        'status': 200,
        'message': 'Upload successfully'
    }

@app.post('/api/v1/retrieve')
async def retrieve_documents(query_text: Annotated[str, Form()], uid: Annotated[str, Form()]):
    if uid not in users_vectorstores.keys():
        return {
            'status': 200,
            'message': 'You should upload a document first'
        }
    retriever = users_vectorstores[uid]['vectorstores'].as_retriever()

    try:
        result = RetrieveDocument(query_text, retriever)
    except QuotaRateLimit as e:
        return {
            'status': 500,
            'message': 'Please wait a minute because of too much request'
        }
    except Exception as e:
        return {
            'status': 500,
            'message': 'There have some errors. Please wait!'
        }

    
    return {
            'status': 200,
            'question': query_text,
            'message': result
        }



