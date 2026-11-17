"""Embedding model selection. Both providers are real models; there is no mock."""
from functools import lru_cache

from src.config import get_settings


@lru_cache(maxsize=1)
def get_embeddings():
    settings = get_settings()
    if settings.embedding_provider == "gemini":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(
            model=settings.gemini_embedding_model,
            google_api_key=settings.google_api_key,
        )
    from langchain_community.embeddings import FastEmbedEmbeddings

    return FastEmbedEmbeddings(model_name=settings.local_embedding_model)
