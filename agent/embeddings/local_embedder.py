"""Local embedding provider using SentenceTransformers."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

# Default offline HF mode (can override from CLI)
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_ENABLE_HF_TRANSFER", "0")

# Project-local HF cache
project_root = Path(__file__).resolve().parents[2]
hf_cache = project_root / ".cache" / "hf"
os.environ.setdefault("HF_HOME", str(hf_cache))
os.environ.setdefault("HUGGINGFACE_HUB_CACHE", str(hf_cache / "hub"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(hf_cache / "transformers"))

logger = logging.getLogger(__name__)


def _offline_enabled() -> bool:
    """Check if offline mode is enabled."""
    return os.getenv("CNCR_OFFLINE", "1") == "1"


def _debug_enabled() -> bool:
    """Check if debug mode is enabled."""
    return os.getenv("CNCR_DEBUG_EMBEDDER", "0") == "1"


def _safe_model_dir_name(model_name: str) -> str:
    """Convert model name to cache directory format.
    
    Args:
        model_name: Model name like "BAAI/bge-small-en-v1.5"
        
    Returns:
        Directory name like "models--BAAI--bge-small-en-v1.5"
    """
    return "models--" + model_name.replace("/", "--")


def _find_latest_snapshot_dir(model_name: str, hub_cache: Path) -> tuple[Path | None, Path]:
    """Find the latest snapshot directory for a model.
    
    Args:
        model_name: Model name like "BAAI/bge-small-en-v1.5"
        hub_cache: Path to HUGGINGFACE_HUB_CACHE directory
        
    Returns:
        Tuple of (snapshot_path: Path | None, model_dir: Path)
    """
    model_dir = hub_cache / _safe_model_dir_name(model_name)
    snaps = model_dir / "snapshots"
    if not snaps.exists():
        return None, model_dir
    candidates = [d for d in snaps.iterdir() if d.is_dir()]
    if not candidates:
        return None, model_dir
    # newest by mtime (simple, reliable)
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0], model_dir

try:
    import torch
    from sentence_transformers import SentenceTransformer
except ImportError:
    torch = None
    SentenceTransformer = None


class LocalEmbedder:
    """Local embedding provider using SentenceTransformers."""

    def __init__(self, model_name: str, device: str | None = None):
        """Initialize local embedder.
        
        Args:
            model_name: SentenceTransformers model name (e.g., "BAAI/bge-small-en-v1.5")
            device: Device to use ("cpu", "cuda", or None for auto-detect)
        """
        if SentenceTransformer is None:
            raise ImportError(
                "sentence-transformers not installed. Install with: pip install sentence-transformers"
            )
        
        self.model_name = model_name
        if device is not None:
            self.device = device
        else:
            self.device = "cuda" if (torch and torch.cuda.is_available()) else "cpu"

        offline = _offline_enabled()
        hub_cache = Path(os.environ.get("HUGGINGFACE_HUB_CACHE", str(hf_cache / "hub")))
        snapshot_dir, model_dir = _find_latest_snapshot_dir(model_name, hub_cache)

        if _debug_enabled():
            print(f"[embedder] CNCR_OFFLINE={os.getenv('CNCR_OFFLINE','1')}")
            print(f"[embedder] HF_HOME={os.getenv('HF_HOME')}")
            print(f"[embedder] HUGGINGFACE_HUB_CACHE={os.getenv('HUGGINGFACE_HUB_CACHE')}")
            print(f"[embedder] TRANSFORMERS_CACHE={os.getenv('TRANSFORMERS_CACHE')}")
            print(f"[embedder] model_id={model_name}")
            print(f"[embedder] model_dir={model_dir}")
            print(f"[embedder] snapshot_dir={snapshot_dir}")

        if offline and snapshot_dir is None:
            raise RuntimeError(
                "Offline mode (CNCR_OFFLINE=1) but the embedding model snapshot is missing from local HF cache.\n"
                f"Model: {model_name}\n"
                f"Expected under: {model_dir}\\snapshots\\<hash>\\\n"
                "Your cache is project-local (.cache/hf). Populate it once (online) then rerun offline.\n"
            )

        logger.info(f"Loading local embedding model: {model_name} (device={self.device}, offline={offline})")
        try:
            # In offline mode, use explicit snapshot path to avoid "mean pooling" fallback
            load_target = str(snapshot_dir) if (offline and snapshot_dir is not None) else model_name
            
            try:
                self.model = SentenceTransformer(
                    load_target,
                    device=self.device,
                    cache_folder=str(hf_cache),
                    local_files_only=offline,
                )
            except TypeError:
                # compatibility fallback
                self.model = SentenceTransformer(
                    load_target,
                    device=self.device,
                    cache_folder=str(hf_cache),
                )

            if _debug_enabled():
                tv = torch.__version__ if torch else "n/a"
                print(f"[embedder] loaded_from={load_target}")
                print(f"[embedder] device={self.device} torch={tv}")
            
            # Get dimension by encoding a dummy text
            test_vec = self.model.encode(["test"], normalize_embeddings=True)
            self.dimension = len(test_vec[0])
            logger.info(f"Local embedding model loaded: dim={self.dimension}")
        except Exception as e:
            if offline and snapshot_dir is None:
                raise RuntimeError(
                    f"Failed to load model in offline mode.\n"
                    f"Model snapshot may be missing or incomplete.\n"
                    f"Expected location: {model_dir}\\snapshots\\<hash>\\\n"
                    f"Original error: {e}\n"
                    f"To fix: Run once online to warm cache, or set CNCR_OFFLINE=0"
                ) from e
            raise RuntimeError(f"Failed to load embedding model {model_name}: {e}") from e

    def embed_query(self, text: str) -> list[float]:
        """Embed a single query text.
        
        Args:
            text: Query text to embed.
            
        Returns:
            List of floats (embedding vector).
        """
        if not text:
            raise ValueError("Query text cannot be empty")
        
        vectors = self.model.encode([text], normalize_embeddings=True, batch_size=1)
        return vectors[0].tolist()

    def embed_texts(self, texts: list[str], batch_size: int | None = None) -> list[list[float]]:
        """Embed multiple texts in batches.
        
        Args:
            texts: List of texts to embed.
            batch_size: Batch size for encoding (defaults to CONFIG.embedding_batch_size).
            
        Returns:
            List of embedding vectors (each is a list of floats).
        """
        if not texts:
            return []
        
        batch = batch_size or 32
        vectors = self.model.encode(texts, normalize_embeddings=True, batch_size=batch)
        return [v.tolist() for v in vectors]
