"""Embedding provider abstraction."""
from __future__ import annotations

import logging
import os
from typing import Any

from agent.config import CONFIG

logger = logging.getLogger(__name__)

_EMBEDDER_CACHE: Any = None


class OpenAIEmbedderWrapper:
    """Wrapper for OpenAI embeddings (backwards compatibility)."""
    
    def __init__(self):
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError:
            raise ImportError(
                "langchain-openai not installed. Install with: pip install langchain-openai"
            )
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY not set. Set EMBEDDING_MODE=local to use local embeddings, "
                "or set OPENAI_API_KEY environment variable."
            )
        
        self.model = OpenAIEmbeddings(model="text-embedding-3-small")
        logger.info("Using OpenAI embeddings (text-embedding-3-small)")
    
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query text."""
        vec = self.model.embed_query(text)
        return vec if isinstance(vec, list) else vec.tolist()
    
    def embed_texts(self, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        """Embed multiple texts."""
        vecs = self.model.embed_documents(texts)
        return [v if isinstance(v, list) else v.tolist() for v in vecs]


def get_embedder():
    """Get embedding provider based on CONFIG.embedding_mode.
    
    Returns:
        Embedder instance with embed_query() and embed_texts() methods.
    """
    global _EMBEDDER_CACHE
    
    if _EMBEDDER_CACHE is not None:
        return _EMBEDDER_CACHE
    
    mode = CONFIG.embedding_mode.lower()
    
    if mode == "local":
        from agent.embeddings.local_embedder import LocalEmbedder
        
        # Auto-detect CUDA if available, otherwise use CPU
        device = "cpu"
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                logger.info("CUDA available, using GPU for embeddings")
        except ImportError:
            pass
        
        _EMBEDDER_CACHE = LocalEmbedder(
            model_name=CONFIG.local_embed_model,
            device=device,
        )
    elif mode == "openai":
        _EMBEDDER_CACHE = OpenAIEmbedderWrapper()
    else:
        raise ValueError(
            f"Unknown EMBEDDING_MODE={mode}. Must be 'local' or 'openai'."
        )
    
    return _EMBEDDER_CACHE
