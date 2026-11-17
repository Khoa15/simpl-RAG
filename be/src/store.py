"""Redis layout shared by the API and the Celery worker.

Per user (uid is an anonymous id issued by POST /api/v1/session):
  user:{uid}:docs             zset  doc_id -> created_at
  user:{uid}:doc:{doc_id}     hash  filename, type, status, error, chunks, pages, created_at
  user:{uid}:collection       str   Qdrant collection name holding all of this user's chunks
Global:
  documents:expiry            zset  uid -> unix time when the user's data expires (refreshed on activity)
  ratelimit:{action}:{key}    NX + PX keys for rate limiting
"""
import hashlib

from redis import Redis
from redis.asyncio import Redis as AsyncRedis

EXPIRY_SET = "documents:expiry"


def docs_key(uid: str) -> str:
    return f"user:{uid}:docs"


def doc_key(uid: str, doc_id: str) -> str:
    return f"user:{uid}:doc:{doc_id}"


def collection_key(uid: str) -> str:
    return f"user:{uid}:collection"


def collection_name_for(uid: str) -> str:
    # Hash the uid so the collection name is safe and does not expose the raw id.
    return "user_" + hashlib.sha256(uid.encode()).hexdigest()[:40]


def make_sync_client(url: str) -> Redis:
    return Redis.from_url(url, decode_responses=True)


def make_async_client(url: str) -> AsyncRedis:
    return AsyncRedis.from_url(url, decode_responses=True)
