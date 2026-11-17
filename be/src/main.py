"""FastAPI application: anonymous sessions, multi-document upload, search and answers."""
import logging
import time
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.auth import current_user_id, issue_token
from src.celery_worker import process_document
from src.config import Settings, get_settings
from src.rag import preprocess
from src.rag.errors import QuotaRateLimit, TransientError
from src.rag.extract import SUPPORTED_EXTS, supported
from src.store import EXPIRY_SET, collection_name_for, doc_key, docs_key, make_async_client

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

settings: Settings = get_settings()
redis = make_async_client(settings.redis_url)
app = FastAPI(title="SIMPL-RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)


class Query(BaseModel):
    query: str = Field(min_length=1, max_length=2000)


async def _rate_limit(action: str, key: str, interval_seconds: int) -> None:
    """Allow one request per interval. SET NX is atomic, so concurrent requests cannot both pass."""
    allowed = await redis.set(f"ratelimit:{action}:{key}", "1", nx=True, px=interval_seconds * 1000)
    if not allowed:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, please wait a moment.")


async def _touch(uid: str) -> None:
    """Keep a user's data alive while they are active (sliding inactivity TTL)."""
    if await redis.zcard(docs_key(uid)) > 0:
        await redis.zadd(EXPIRY_SET, {uid: time.time() + settings.document_ttl_seconds})


@app.exception_handler(TransientError)
async def _transient_handler(request: Request, exc: TransientError):
    return JSONResponse(status_code=503, content={"detail": "Service temporarily unavailable, please retry."})


@app.get("/health")
async def health():
    await redis.ping()
    return {"status": "ok"}


@app.post("/api/v1/session", status_code=201)
async def create_session(request: Request):
    """Issue an anonymous identity. No account, password or email is needed."""
    ip = request.client.host if request.client else "unknown"
    key = f"ratelimit:session:{ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > settings.session_rate_per_minute:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many new sessions from this address.")
    uid = uuid.uuid4().hex
    return {"token": issue_token(uid, settings), "token_type": "bearer", "expires_in": settings.jwt_ttl_seconds}


@app.post("/api/v1/documents", status_code=status.HTTP_202_ACCEPTED)
async def upload_document(file: UploadFile = File(...), uid: str = Depends(current_user_id)):
    filename = Path(file.filename or "").name or "untitled"
    if not supported(filename):
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"Unsupported file type. Allowed: {', '.join(sorted(SUPPORTED_EXTS))}")
    await _rate_limit("upload", uid, settings.upload_min_interval_seconds)
    if await redis.zcard(docs_key(uid)) >= settings.max_documents_per_user:
        raise HTTPException(status.HTTP_409_CONFLICT, "Document limit reached. Delete a document first.")

    doc_id = uuid.uuid4().hex
    path = Path(settings.upload_dir) / f"{doc_id}{Path(filename).suffix.lower()}"
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with path.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                written += len(chunk)
                if written > settings.max_upload_bytes:
                    raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                        f"File exceeds {settings.max_upload_bytes // (1024 * 1024)} MB limit.")
                out.write(chunk)
        if written == 0:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")
    except HTTPException:
        path.unlink(missing_ok=True)
        raise

    now = time.time()
    await redis.hset(doc_key(uid, doc_id), mapping={
        "filename": filename, "type": path.suffix.lower().lstrip("."), "status": "processing",
        "error": "", "chunks": 0, "segments": 0, "created_at": int(now), "size": written,
    })
    await redis.zadd(docs_key(uid), {doc_id: now})
    await redis.zadd(EXPIRY_SET, {uid: now + settings.document_ttl_seconds})
    process_document.apply_async(args=[str(path), uid, doc_id, filename])
    return {"doc_id": doc_id, "filename": filename, "status": "processing"}


async def _document_view(uid: str, doc_id: str) -> dict:
    data = await redis.hgetall(doc_key(uid, doc_id))
    if not data:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    return {
        "doc_id": doc_id,
        "filename": data.get("filename"),
        "type": data.get("type"),
        "status": data.get("status"),
        "error": data.get("error") or None,
        "chunks": int(data.get("chunks") or 0),
        "created_at": int(data.get("created_at") or 0),
    }


@app.get("/api/v1/documents")
async def list_documents(uid: str = Depends(current_user_id)):
    await _touch(uid)
    doc_ids = await redis.zrevrange(docs_key(uid), 0, -1)
    return {"documents": [await _document_view(uid, d) for d in doc_ids]}


@app.get("/api/v1/documents/{doc_id}")
async def get_document(doc_id: str, uid: str = Depends(current_user_id)):
    await _touch(uid)
    return await _document_view(uid, doc_id)


@app.delete("/api/v1/documents/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(doc_id: str, uid: str = Depends(current_user_id)):
    if not await redis.zscore(docs_key(uid), doc_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Document not found.")
    await run_in_threadpool(preprocess.remove_document, collection_name_for(uid), doc_id)
    await redis.delete(doc_key(uid, doc_id))
    await redis.zrem(docs_key(uid), doc_id)
    return None


async def _require_ready_documents(uid: str) -> None:
    doc_ids = await redis.zrange(docs_key(uid), 0, -1)
    if not doc_ids:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No documents uploaded yet.")
    statuses = [await redis.hget(doc_key(uid, d), "status") for d in doc_ids]
    if "ready" not in statuses:
        raise HTTPException(status.HTTP_409_CONFLICT, "Your documents are still being processed. Please wait.")


@app.post("/api/v1/search")
async def search(body: Query, uid: str = Depends(current_user_id)):
    await _rate_limit("query", uid, settings.query_min_interval_seconds)
    await _touch(uid)
    await _require_ready_documents(uid)
    hits = await run_in_threadpool(preprocess.search, collection_name_for(uid), body.query)
    return {"query": body.query, "results": hits}


@app.post("/api/v1/retrieve")
async def retrieve(body: Query, uid: str = Depends(current_user_id)):
    await _rate_limit("query", uid, settings.query_min_interval_seconds)
    await _touch(uid)
    await _require_ready_documents(uid)
    try:
        answer = await run_in_threadpool(preprocess.answer, collection_name_for(uid), body.query)
    except QuotaRateLimit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded, please wait.")
    return {"status": 200, "question": body.query, "message": answer}
