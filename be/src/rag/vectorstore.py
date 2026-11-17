"""Qdrant access. One collection per user; each chunk carries its doc_id so single documents can be removed."""
from functools import lru_cache

from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.http import models as qm

from src.config import get_settings
from src.rag.embeddings import get_embeddings


@lru_cache(maxsize=1)
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key, timeout=20)


def ensure_collection(name: str) -> None:
    """Create the user's collection on first use. Safe to call concurrently."""
    client = get_qdrant_client()
    if client.collection_exists(name):
        return
    dim = len(get_embeddings().embed_query("dimension probe"))
    try:
        client.create_collection(
            collection_name=name,
            vectors_config=qm.VectorParams(size=dim, distance=qm.Distance.COSINE),
        )
        client.create_payload_index(
            collection_name=name,
            field_name="metadata.doc_id",
            field_schema=qm.PayloadSchemaType.KEYWORD,
        )
    except Exception:
        # Another request created it first; that is fine as long as it now exists.
        if not client.collection_exists(name):
            raise


def delete_collection(name: str) -> None:
    client = get_qdrant_client()
    if client.collection_exists(name):
        client.delete_collection(name)


def doc_filter(doc_id: str) -> qm.Filter:
    return qm.Filter(must=[qm.FieldCondition(key="metadata.doc_id", match=qm.MatchValue(value=doc_id))])


def delete_document_points(name: str, doc_id: str) -> None:
    client = get_qdrant_client()
    if client.collection_exists(name):
        client.delete(collection_name=name, points_selector=qm.FilterSelector(filter=doc_filter(doc_id)))


def open_store(name: str) -> QdrantVectorStore:
    return QdrantVectorStore(client=get_qdrant_client(), collection_name=name, embedding=get_embeddings())
