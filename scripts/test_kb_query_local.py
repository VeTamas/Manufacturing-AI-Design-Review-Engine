"""Test KB query retrieval with local embeddings.

Run on Windows PowerShell:
    $env:EMBEDDING_MODE="local"
    python scripts/test_kb_query_local.py
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

from agent.tools.kb_tool import retrieve


def main():
    """Test KB query retrieval."""
    print("=" * 60)
    print("Testing KB Query Retrieval (Local Embeddings)")
    print("=" * 60)
    print(f"EMBEDDING_MODE: {os.getenv('EMBEDDING_MODE')}")
    print()
    print("NOTE: Ensure indices are rebuilt with local embeddings first:")
    print("  python scripts/build_kb_index.py --process cnc")
    print()

    # Test queries
    test_cases = [
        ("CNC", "deep pocket machining", None),
        ("CNC", "tolerance critical features", None),
        ("AM", "metal powder bed fusion", None),
        ("AM", "FDM thermoplastic", "FDM"),
    ]

    for process, query, hint in test_cases:
        print(f"Query: {query}")
        print(f"Process: {process}, Hint: {hint or 'None'}")
        try:
            results = retrieve(query, process=process, top_k=3, subprocess_hint=hint)
            print(f"  Retrieved {len(results)} results:")
            for i, r in enumerate(results, 1):
                source = r.get("source", "?")
                text_preview = r.get("text", "")[:80]
                print(f"    {i}. [{source}] {text_preview}...")
        except FileNotFoundError as e:
            print(f"  ERROR: {e}")
            print(f"  Rebuild index: python scripts/build_kb_index.py --process {process.lower()}")
        except RuntimeError as e:
            print(f"  ERROR: {e}")
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")
        print()

    print("=" * 60)
    print("Test completed!")
    print("=" * 60)


if __name__ == "__main__":
    main()
