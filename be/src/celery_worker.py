"""Celery app: background indexing of uploaded files and cleanup of expired users."""
import logging
import os
import time

from celery import Celery
from celery.schedules import crontab

from src.config import get_settings
from src.rag.errors import PermanentError, TransientError, is_transient
from src.rag.preprocess import index_document, remove_document
from src.rag.vectorstore import delete_collection
from src.store import EXPIRY_SET, collection_key, collection_name_for, doc_key, docs_key, make_sync_client

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery("worker", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    task_track_started=True,
    task_time_limit=1800,
    task_soft_time_limit=1700,
    result_expires=3600,
    broker_transport_options={"visibility_timeout": 3600},
    beat_schedule={
        "cleanup-expired-users": {
            "task": "src.celery_worker.cleanup_expired_users",
            "schedule": crontab(minute="*"),
        }
    },
)

_redis = make_sync_client(settings.redis_url)


def _remove_file(path: str) -> None:
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _mark_failed(uid: str, doc_id: str, code: str) -> None:
    _redis.hset(doc_key(uid, doc_id), mapping={"status": "failed", "error": code})


@celery_app.task(
    bind=True,
    autoretry_for=(TransientError,),
    retry_backoff=5,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=5,
)
def process_document(self, path: str, uid: str, doc_id: str, filename: str) -> dict:
    """Index one uploaded file. Transient failures are retried; permanent ones are recorded as failed."""
    collection = collection_name_for(uid)
    try:
        counts = index_document(path, filename, collection, doc_id)
    except PermanentError as exc:
        remove_document(collection, doc_id)
        _mark_failed(uid, doc_id, str(exc))
        _remove_file(path)
        logger.info("Document %s rejected: %s", doc_id, exc)
        return {"status": "failed", "error": str(exc)}
    except Exception as exc:
        remove_document(collection, doc_id)  # drop partial points before any retry
        if is_transient(exc):
            if self.request.retries >= self.max_retries:
                _mark_failed(uid, doc_id, "temporarily_unavailable")
                _remove_file(path)
                return {"status": "failed", "error": "temporarily_unavailable"}
            raise TransientError(str(exc)) from exc
        _mark_failed(uid, doc_id, "internal_error")
        _remove_file(path)
        logger.exception("Unexpected failure indexing document %s", doc_id)
        return {"status": "failed", "error": "internal_error"}

    now = time.time()
    pipe = _redis.pipeline()
    pipe.hset(doc_key(uid, doc_id), mapping={"status": "ready", "chunks": counts["chunks"], "segments": counts["segments"], "error": ""})
    pipe.set(collection_key(uid), collection, ex=settings.document_ttl_seconds)
    pipe.zadd(EXPIRY_SET, {uid: now + settings.document_ttl_seconds})
    pipe.execute()
    _remove_file(path)
    return {"status": "ready", **counts}


@celery_app.task(name="src.celery_worker.cleanup_expired_users")
def cleanup_expired_users() -> int:
    """Remove the Qdrant collection and Redis keys of users inactive past the TTL."""
    removed = 0
    for uid in _redis.zrangebyscore(EXPIRY_SET, "-inf", time.time()):
        try:
            delete_collection(collection_name_for(uid))
            doc_ids = _redis.zrange(docs_key(uid), 0, -1)
            keys = [doc_key(uid, d) for d in doc_ids] + [docs_key(uid), collection_key(uid)]
            _redis.delete(*keys)
            _redis.zrem(EXPIRY_SET, uid)
            removed += 1
        except Exception:
            logger.exception("Cleanup failed for user; will retry on next run")
    return removed
