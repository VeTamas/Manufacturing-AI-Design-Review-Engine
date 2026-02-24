"""Test script for local embeddings.

Run on Windows PowerShell:
    python scripts/test_local_embeddings.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Set env vars before importing agent modules
os.environ["EMBEDDING_MODE"] = os.getenv("EMBEDDING_MODE", "local")

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agent.embeddings.local_embedder import LocalEmbedder


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity (dot product for normalized vectors)."""
    if len(a) != len(b):
        raise ValueError(f"Vector length mismatch: {len(a)} vs {len(b)}")
    return sum(x * y for x, y in zip(a, b))


def main():
    """Test local embeddings."""
    print("=" * 60)
    print("Testing Local Embeddings")
    print("=" * 60)
    print(f"EMBEDDING_MODE: {os.getenv('EMBEDDING_MODE')}")
    print()

    try:
        embedder = LocalEmbedder(model_name="BAAI/bge-small-en-v1.5", device="cpu")
        print(f"Model loaded: {embedder.model_name}")
        print(f"Dimension: {embedder.dimension}")
        print()

        # Test texts
        text1 = "CNC machining deep pockets require specialized tools"
        text2 = "Additive manufacturing with metal powder bed fusion"
        query = "machining deep internal features"

        print("Embedding texts...")
        vecs = embedder.embed_texts([text1, text2])
        query_vec = embedder.embed_query(query)

        print(f"Text 1: {text1}")
        print(f"  Vector length: {len(vecs[0])}")
        print(f"Text 2: {text2}")
        print(f"  Vector length: {len(vecs[1])}")
        print(f"Query: {query}")
        print(f"  Vector length: {len(query_vec)}")
        print()

        # Similarity checks
        sim1 = cosine_similarity(query_vec, vecs[0])
        sim2 = cosine_similarity(query_vec, vecs[1])
        sim_between = cosine_similarity(vecs[0], vecs[1])

        print("Cosine Similarities:")
        print(f"  Query vs Text1: {sim1:.4f}")
        print(f"  Query vs Text2: {sim2:.4f}")
        print(f"  Text1 vs Text2: {sim_between:.4f}")
        print()

        # Verify normalization (should be close to 1.0 for self-similarity)
        self_sim = cosine_similarity(vecs[0], vecs[0])
        print(f"Self-similarity (should be ~1.0): {self_sim:.6f}")
        print()

        print("=" * 60)
        print("Test completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
