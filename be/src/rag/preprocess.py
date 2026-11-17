"""Indexing and retrieval for one user's documents.

Indexing streams segments from disk and embeds chunks in fixed-size batches, so memory stays
bounded for large files. Chunk IDs are deterministic (doc_id + chunk index), so a retried batch
overwrites its own points instead of creating duplicates.
"""
import logging
import uuid

from langchain.chat_models import init_chat_model
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_text_splitters import RecursiveCharacterTextSplitter
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_random_exponential

from src.config import get_settings
from src.rag import PROMPTS
from src.rag.errors import PermanentError, QuotaRateLimit, TransientError, is_transient
from src.rag.extract import iter_segments
from src.rag.vectorstore import delete_document_points, ensure_collection, open_store

logger = logging.getLogger(__name__)
_ID_NAMESPACE = uuid.UUID("6f1d1a52-7c1e-4b8e-9a53-2f0d7c1b9e11")


@retry(
    retry=retry_if_exception(is_transient),
    wait=wait_random_exponential(multiplier=1, max=30),
    stop=stop_after_attempt(5),
    reraise=True,
)
def _write_batch(store, texts, metadatas, ids) -> None:
    store.add_texts(texts=texts, metadatas=metadatas, ids=ids)


def index_document(path: str, filename: str, collection: str, doc_id: str) -> dict:
    """Index one uploaded file into the user's collection. Returns counts."""
    settings = get_settings()
    ensure_collection(collection)
    store = open_store(collection)
    splitter = RecursiveCharacterTextSplitter(chunk_size=settings.chunk_size, chunk_overlap=settings.chunk_overlap)

    texts, metadatas, ids = [], [], []
    chunks = 0
    segments_seen = 0

    def flush() -> None:
        if texts:
            _write_batch(store, texts, metadatas, ids)
            texts.clear(); metadatas.clear(); ids.clear()

    for segment in iter_segments(path, filename, settings.max_pages, settings.ocr_langs):
        segments_seen += 1
        for piece in splitter.split_text(segment.text):
            ids.append(str(uuid.uuid5(_ID_NAMESPACE, f"{doc_id}:{chunks}")))
            texts.append(piece)
            metadatas.append({"doc_id": doc_id, "filename": filename, **segment.locator})
            chunks += 1
            if len(texts) >= settings.embedding_batch_size:
                flush()
    flush()

    if chunks == 0:
        raise PermanentError("no_extractable_text")
    return {"segments": segments_seen, "chunks": chunks}


def remove_document(collection: str, doc_id: str) -> None:
    delete_document_points(collection, doc_id)


def search(collection: str, query: str, k: int | None = None) -> list[dict]:
    """Top-k chunks for a query across all of the user's documents. No chat model is called."""
    hits = open_store(collection).similarity_search_with_score(query, k=k or get_settings().top_k)
    return [
        {"text": doc.page_content, "source": dict(doc.metadata), "score": float(score)}
        for doc, score in hits
    ]


def answer(collection: str, query: str) -> str:
    """Answer a question from the retrieved chunks using the chat model."""
    settings = get_settings()
    retriever = open_store(collection).as_retriever(search_kwargs={"k": settings.top_k})
    llm = init_chat_model(settings.chat_model, model_provider="google_genai")
    prompt = PromptTemplate.from_template(PROMPTS.RAG_PROMPT)
    chain = {"context": retriever, "question": RunnablePassthrough()} | prompt | llm | StrOutputParser()
    try:
        return chain.invoke(query)
    except Exception as exc:
        if is_transient(exc):
            if "ResourceExhausted" in type(exc).__name__ or "429" in str(exc):
                raise QuotaRateLimit(str(exc)) from exc
            raise TransientError(str(exc)) from exc
        raise
