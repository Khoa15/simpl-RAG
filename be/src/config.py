"""Runtime configuration, read once from environment variables."""
import os
from dataclasses import dataclass
from functools import lru_cache


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    redis_url: str
    qdrant_url: str
    qdrant_api_key: str | None
    jwt_secret: str
    jwt_issuer: str
    jwt_ttl_seconds: int
    embedding_provider: str          # "gemini" or "local"
    gemini_embedding_model: str
    local_embedding_model: str
    chat_model: str
    google_api_key: str | None
    max_upload_bytes: int
    max_pages: int
    document_ttl_seconds: int
    upload_min_interval_seconds: int
    query_min_interval_seconds: int
    upload_dir: str
    embedding_batch_size: int
    chunk_size: int
    chunk_overlap: int
    top_k: int
    ocr_langs: str
    max_documents_per_user: int
    session_rate_per_minute: int


def load_settings() -> Settings:
    secret = os.environ.get("JWT_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET must be set and at least 32 characters long")

    provider = os.environ.get("EMBEDDING_PROVIDER", "gemini").lower()
    if provider not in ("gemini", "local"):
        raise RuntimeError("EMBEDDING_PROVIDER must be 'gemini' or 'local'")

    google_key = os.environ.get("GOOGLE_API_KEY") or None
    if provider == "gemini" and not google_key:
        raise RuntimeError("GOOGLE_API_KEY is required when EMBEDDING_PROVIDER=gemini")

    return Settings(
        redis_url=os.environ["REDIS_URL"],
        qdrant_url=os.environ.get("QDRANT_URL", "http://qdrant:6333"),
        qdrant_api_key=os.environ.get("QDRANT_API_KEY") or None,
        jwt_secret=secret,
        jwt_issuer=os.environ.get("JWT_ISSUER", "simpl-rag"),
        jwt_ttl_seconds=int(os.environ.get("JWT_TTL_SECONDS", "86400")),
        embedding_provider=provider,
        gemini_embedding_model=os.environ.get("GEMINI_EMBEDDING_MODEL", "models/gemini-embedding-001"),
        local_embedding_model=os.environ.get("LOCAL_EMBEDDING_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"),
        chat_model=os.environ.get("CHAT_MODEL", "gemini-2.5-flash"),
        google_api_key=google_key,
        max_upload_bytes=int(os.environ.get("MAX_UPLOAD_MB", "20")) * 1024 * 1024,
        max_pages=int(os.environ.get("MAX_PAGES", "300")),
        document_ttl_seconds=int(os.environ.get("DOCUMENT_TTL_SECONDS", "1800")),
        upload_min_interval_seconds=int(os.environ.get("UPLOAD_MIN_INTERVAL_SECONDS", "3")),
        query_min_interval_seconds=int(os.environ.get("QUERY_MIN_INTERVAL_SECONDS", "3")),
        upload_dir=os.environ.get("UPLOAD_DIR", "/data/uploads"),
        embedding_batch_size=int(os.environ.get("EMBEDDING_BATCH_SIZE", "64")),
        chunk_size=int(os.environ.get("CHUNK_SIZE", "1000")),
        chunk_overlap=int(os.environ.get("CHUNK_OVERLAP", "100")),
        top_k=int(os.environ.get("TOP_K", "4")),
        ocr_langs=os.environ.get("OCR_LANGS", "vie+eng"),
        max_documents_per_user=int(os.environ.get("MAX_DOCUMENTS_PER_USER", "50")),
        session_rate_per_minute=int(os.environ.get("SESSION_RATE_PER_MINUTE", "30")),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
