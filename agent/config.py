"""App configuration (env-only; no hardcoded secrets).

PORTFOLIO: API keys and secrets must come from environment only (.env or shell).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

from dotenv import load_dotenv

load_dotenv()

# -----------------------------------------------------------------------------
# LLM settings resolution (single source of truth)
# -----------------------------------------------------------------------------

LLM_MODE_T = Literal["local", "remote", "hybrid", "off"]


def is_ollama_available(base_url: str, timeout: float = 0.25) -> bool:
    """Fast ping to Ollama; must not hang app startup. Returns True if /api/tags returns 200."""
    try:
        import requests
        url = f"{base_url.rstrip('/')}/api/tags"
        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


@dataclass(frozen=True)
class LLMSettings:
    llm_mode: LLM_MODE_T
    offline: bool
    ollama_base_url: str
    ollama_model: str
    timeout_seconds: int
    cloud_enabled: bool
    local_enabled: bool
    reason_trace: list[str] = field(default_factory=list)


def resolve_llm_settings() -> LLMSettings:
    """Single source of truth for LLM mode and URLs. CNCR_OFFLINE disables cloud only; local stays allowed."""
    # Precedence: CNCR_* over generic env
    raw_mode = (os.getenv("CNCR_LLM_MODE") or os.getenv("LLM_MODE") or "").strip().lower()
    ollama_base_url = os.getenv("CNCR_OLLAMA_BASE_URL") or os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
    ollama_model = os.getenv("CNCR_OLLAMA_MODEL") or os.getenv("OLLAMA_MODEL") or "jamba2-3b-q6k"
    timeout_seconds = int(os.getenv("CNCR_LLM_TIMEOUT_SECONDS") or os.getenv("LLM_TIMEOUT_SECONDS") or "60")
    offline = os.getenv("CNCR_OFFLINE", "1") == "1"
    cloud_enabled = not offline
    reason_trace: list[str] = []

    # Normalize explicit mode
    if raw_mode in ("local", "remote", "hybrid", "off"):
        llm_mode: LLM_MODE_T = raw_mode
        reason_trace.append(f"explicit LLM_MODE/CNCR_LLM_MODE={llm_mode}")
    elif raw_mode:
        llm_mode = "remote"
        reason_trace.append(f"unknown LLM_MODE '{raw_mode}' -> remote")
    else:
        # Default: dev-friendly local when Ollama available or configured; else off or remote
        ollama_configured = bool(
            os.getenv("OLLAMA_BASE_URL") or os.getenv("CNCR_OLLAMA_BASE_URL")
            or os.getenv("OLLAMA_MODEL") or os.getenv("CNCR_OLLAMA_MODEL")
        )
        ollama_reachable = is_ollama_available(ollama_base_url)
        if offline:
            if ollama_reachable or ollama_configured:
                llm_mode = "local"
                reason_trace.append("default: no LLM_MODE; offline + Ollama configured/reachable -> local")
            else:
                llm_mode = "off"
                reason_trace.append("default: no LLM_MODE; offline and no Ollama -> off")
        else:
            if os.getenv("OPENAI_API_KEY"):
                llm_mode = "remote"
                reason_trace.append("default: no LLM_MODE; not offline + OPENAI_API_KEY -> remote")
            elif ollama_reachable or ollama_configured:
                llm_mode = "local"
                reason_trace.append("default: no LLM_MODE; Ollama configured/reachable -> local")
            else:
                llm_mode = "off"
                reason_trace.append("default: no LLM_MODE; no key and no Ollama -> off")

    # Hybrid + offline → treat as local-only for execution (cloud disabled), keep label "hybrid" in logs
    local_enabled = llm_mode in ("local", "hybrid") and bool(ollama_base_url and ollama_model)
    if llm_mode == "off":
        local_enabled = False

    return LLMSettings(
        llm_mode=llm_mode,
        offline=offline,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        timeout_seconds=timeout_seconds,
        cloud_enabled=cloud_enabled,
        local_enabled=local_enabled,
        reason_trace=reason_trace,
    )


# -----------------------------------------------------------------------------
# App config (frozen; env read at import time)
# -----------------------------------------------------------------------------

@dataclass(frozen=True)
class AppConfig:
    # LLM
    model_name: str = "gpt-5-mini"
    
    # LLM provider mode: "remote" (OpenAI), "local" (Ollama), "hybrid" (try local, fallback to OpenAI)
    llm_mode: str = os.getenv("LLM_MODE", "remote")
    ollama_base_url: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "jamba2-3b-q6k")
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))
    
    # Embedding provider mode: "local" (SentenceTransformers) or "openai" (OpenAI API)
    embedding_mode: str = os.getenv("EMBEDDING_MODE", "local")
    local_embed_model: str = os.getenv("LOCAL_EMBED_MODEL", "BAAI/bge-small-en-v1.5")
    embedding_cache_dir: str = os.getenv("EMBEDDING_CACHE_DIR", "data/outputs/cache/embeddings")
    embedding_cache_ttl_seconds: int = int(os.getenv("EMBEDDING_CACHE_TTL_SECONDS", str(60 * 60 * 24 * 7)))  # 7 days
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "32"))

    # Feature flags
    enable_llm_explain: bool = os.getenv("GOLDEN_TEST") != "1"  # disabled when GOLDEN_TEST=1 for deterministic runs
    strict_privacy: bool = True       # később policy gate-et ide kötjük

    enable_cache: bool = True
    cache_dir: str = "data/outputs/cache"
    cache_ttl_seconds: int = 60 * 60 * 24  # 24h

    enable_retry: bool = True
    retry_max_attempts: int = 2
    retry_backoff_seconds: float = 1.0

    # CNC numeric analysis (Phase 1): timeout for OCP/STEP parsing
    cnc_numeric_timeout_seconds: int = int(os.getenv("CNC_NUMERIC_TIMEOUT_SECONDS", "3"))
    # CAD Lite: slightly higher timeout for bins-mode robustness (+2s default)
    cad_lite_timeout_seconds: float = float(os.getenv("CAD_LITE_TIMEOUT_SECONDS", "5"))
    # Extrusion Lite: timeout for constant cross-section analysis (increased from 3s to 10s)
    extrusion_lite_timeout_seconds: float = float(os.getenv("CNCR_EXTRUSION_TIMEOUT_S", os.getenv("EXTRUSION_LITE_TIMEOUT_SECONDS", "10")))
    
    # Debug flags
    debug_psi: bool = os.getenv("CNCR_DEBUG_PSI", "0") == "1"


CONFIG = AppConfig()