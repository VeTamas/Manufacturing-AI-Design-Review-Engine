from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import faiss
import numpy as np
from diskcache import Cache

from agent.config import CONFIG
from agent.embeddings.provider import get_embedder
from agent.utils.filetrace import traced_faiss_read_index, traced_open

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
INDEX_BASE = PROJECT_ROOT / "data" / "outputs" / "kb_index"
_EMBEDDING_CACHE: Cache | None = None

# Casting subprocess hint to source path mapping
CASTING_HINT_TO_PATH = {
    "DIE_CASTING": "casting/die_casting/",
    "INVESTMENT_CASTING": "casting/investment_casting/",
    "URETHANE_CASTING": "casting/urethane_casting/",
    "STEEL_CASTING": "casting/steel_casting/",
}

# Forging subprocess hint to source path mapping
FORGING_HINT_TO_PATH = {
    "CLOSED_DIE": "forging/closed_die/",
    "OPEN_DIE": "forging/open_die/",
    "HYBRID": "forging/hybrid_open_closed/",
    "DIE_MACHINING": "forging/die_machining/",
    "COMMON": "forging/common/",
}

# Per-process lazy-loaded state
_CACHE: dict[str, tuple] = {}


def _get_embedding_cache() -> Cache:
    """Get or create embedding cache."""
    global _EMBEDDING_CACHE
    if _EMBEDDING_CACHE is None:
        cache_dir = CONFIG.embedding_cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        _EMBEDDING_CACHE = Cache(cache_dir)
    return _EMBEDDING_CACHE


def _embed_query_with_cache(query: str) -> list[float]:
    """Embed query text with caching.
    
    Cache key: sha256(model_name + "\n" + query_text)
    """
    embedder = get_embedder()
    model_name = getattr(embedder, "model_name", CONFIG.local_embed_model if CONFIG.embedding_mode == "local" else "openai-text-embedding-3-small")
    
    # Generate cache key
    cache_key_raw = f"{model_name}\n{query}".encode("utf-8")
    cache_key = hashlib.sha256(cache_key_raw).hexdigest()
    
    # Check cache
    cache = _get_embedding_cache()
    cached_vec = cache.get(cache_key, default=None)
    if cached_vec is not None:
        logger.debug(f"Embedding cache hit for query: {query[:50]}...")
        return cached_vec
    
    # Embed and cache
    vec = embedder.embed_query(query)
    cache.set(cache_key, vec, expire=CONFIG.embedding_cache_ttl_seconds)
    logger.debug(f"Embedded and cached query: {query[:50]}...")
    return vec


def _load_index(process: str) -> tuple:
    """Lazy load index and metadata for a process. process normalized to lowercase (cnc, am, sheet_metal, injection_molding)."""
    key = (process or "cnc").lower()
    if key not in _CACHE:
        index_dir = INDEX_BASE / key
        index_file = index_dir / "index.faiss"
        metadata_file = index_dir / "metadata.json"
        if not index_file.exists():
            raise FileNotFoundError(
                f"RAG index not found for process={process.upper()} (expected: {index_dir})"
            )
        try:
            idx = traced_faiss_read_index(index_file)
        except RuntimeError as e:
            if "dimension" in str(e).lower() or "dim" in str(e).lower():
                raise RuntimeError(
                    f"Index dimension mismatch for process={process.upper()}. "
                    f"The index was built with a different embedding model. "
                    f"Rebuild indices with: python scripts/build_kb_index.py --process {key}"
                ) from e
            raise
        
        with traced_open(metadata_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        _CACHE[key] = (idx, data["chunks"], data["metadata"])
    return _CACHE[key]


def retrieve(query: str, process: str, top_k: int = 5, subprocess_hint: str | None = None) -> list[dict]:
    """
    Retrieve top_k chunks by query for the given process.

    process: "CNC" | "AM" | "SHEET_METAL" | "INJECTION_MOLDING" | "CASTING" (or lowercase). Defaults to CNC if missing.
    subprocess_hint: when process=AM and "FDM", prefer am/fdm + am/common over am/metal_lpbf (by source name).
                     when process=CASTING, prefer sources from matching casting subfolder (die_casting/investment_casting/urethane_casting/steel_casting).
                     when process=FORGING, prefer sources from matching forging subfolder (closed_die/open_die/hybrid_open_closed/die_machining).
    Returns list of dicts with "text" and "source" keys.
    """
    proc = (process or "cnc").lower()
    index, chunks, metadata = _load_index(proc)
    qe = _embed_query_with_cache(query)
    qv = np.array([qe], dtype=np.float32)
    
    # Verify dimension matches index
    if qv.shape[1] != index.d:
        raise RuntimeError(
            f"Embedding dimension mismatch: query vector dim={qv.shape[1]}, index dim={index.d}. "
            f"Rebuild indices with: python scripts/build_kb_index.py --process {proc}"
        )
    # Increase fetch_k for AM(FDM) and CASTING with subprocess hint to allow reranking
    fetch_k = top_k
    if proc == "am" and (subprocess_hint or "").upper() == "FDM":
        fetch_k = top_k * 3
    elif proc == "casting" and subprocess_hint:
        hint_upper = (subprocess_hint or "").upper().strip()
        if hint_upper in CASTING_HINT_TO_PATH:
            fetch_k = top_k * 3
    elif proc == "forging" and subprocess_hint:
        hint_upper = (subprocess_hint or "").upper().strip()
        if hint_upper in FORGING_HINT_TO_PATH:
            fetch_k = top_k * 3
    k = min(fetch_k, len(chunks))
    _, indices = index.search(qv, k)

    results = []
    for idx in indices[0]:
        if idx >= len(chunks):
            continue
        src = metadata[idx]["source"]
        results.append({"text": chunks[idx], "source": src})
    
    # AM(FDM) subprocess preference
    if proc == "am" and (subprocess_hint or "").upper() == "FDM" and len(results) > top_k:
        # Prefer fdm + common (exclude metal_am_* when hint=FDM)
        preferred = [r for r in results if "metal_am" not in (r.get("source") or "")]
        rest = [r for r in results if "metal_am" in (r.get("source") or "")]
        results = (preferred + rest)[:top_k]
    # CASTING subprocess preference
    elif proc == "casting" and subprocess_hint:
        hint_upper = (subprocess_hint or "").upper().strip()
        preferred_path = CASTING_HINT_TO_PATH.get(hint_upper)
        if preferred_path and len(results) > top_k:
            preferred = [r for r in results if preferred_path in (r.get("source") or "")]
            rest = [r for r in results if preferred_path not in (r.get("source") or "")]
            results = (preferred + rest)[:top_k]
        else:
            results = results[:top_k]
    # FORGING subprocess preference
    elif proc == "forging" and subprocess_hint:
        hint_upper = (subprocess_hint or "").upper().strip()
        preferred_path = FORGING_HINT_TO_PATH.get(hint_upper)
        if preferred_path and len(results) > top_k:
            preferred = [r for r in results if preferred_path in (r.get("source") or "")]
            rest = [r for r in results if preferred_path not in (r.get("source") or "")]
            results = (preferred + rest)[:top_k]
        else:
            results = results[:top_k]
    else:
        results = results[:top_k]
    return results
