from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import numpy as np
import faiss
from faiss import IndexFlatL2
from langchain_text_splitters import RecursiveCharacterTextSplitter
from dotenv import load_dotenv

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from agent.config import CONFIG
from agent.embeddings.provider import get_embedder
from agent.process_registry import get_kb_folder_path

load_dotenv()

KB_BASE = PROJECT_ROOT / "knowledge_base"
INDEX_BASE = PROJECT_ROOT / "data" / "outputs" / "kb_index"

# Process indices supported by build_kb_index (CLI-compatible names)
PROCESSES = ("cnc", "am", "am_fdm", "am_metal_lpbf", "am_thermoplastic_high_temp", "sheet_metal", "injection_molding", "casting", "forging", "extrusion", "mim", "thermoforming", "compression_molding", "am_sla", "am_sls", "am_mjf")


def build_index_for_process(process: str) -> None:
    """Build FAISS index for one process from knowledge_base/<process>/*.md."""
    # Use centralized registry to map process index to KB folder path
    kb_folder_rel = get_kb_folder_path(process)
    kb_dir = KB_BASE / kb_folder_rel
    index_dir = INDEX_BASE / process
    index_file = index_dir / "index.faiss"
    metadata_file = index_dir / "metadata.json"

    if not kb_dir.is_dir():
        raise ValueError(f"Knowledge base folder not found: {kb_dir}")

    md_files = sorted(kb_dir.rglob("*.md"))
    if not md_files:
        raise ValueError(f"No .md files found in {kb_dir}")

    os.makedirs(index_dir, exist_ok=True)
    embedder = get_embedder()
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1200,
        chunk_overlap=200,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    all_chunks = []
    metadata_list = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        # Store source as relative path from knowledge_base (e.g., "injection_molding/im_wall_thickness.md")
        rel_path = md_file.relative_to(KB_BASE)
        source_str = str(rel_path).replace("\\", "/")
        for chunk in text_splitter.split_text(content):
            all_chunks.append(chunk)
            metadata_list.append({"source": source_str})

    if not all_chunks:
        raise ValueError(f"No chunks generated from {kb_dir}")

    # Get model info for logging
    model_name = getattr(embedder, "model_name", CONFIG.local_embed_model if CONFIG.embedding_mode == "local" else "openai-text-embedding-3-small")
    embedding_mode = CONFIG.embedding_mode
    
    print(f"[{process}] Embedding {len(all_chunks)} chunks using provider={embedding_mode} model={model_name}...")
    embeddings = embedder.embed_texts(all_chunks, batch_size=CONFIG.embedding_batch_size)
    dimension = len(embeddings[0])
    print(f"[{process}] Embedding dimension: {dimension}")
    
    index = IndexFlatL2(dimension)
    index.add(np.array(embeddings, dtype=np.float32))

    faiss.write_index(index, str(index_file))
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump({"chunks": all_chunks, "metadata": metadata_list}, f, indent=2, ensure_ascii=False)

    print(f"[{process}] Index built: {len(all_chunks)} chunks → {index_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build FAISS KB index per process.")
    parser.add_argument(
        "--process",
        choices=PROCESSES,
        default=None,
        help="Build index for this process only. Default: build all processes.",
    )
    args = parser.parse_args()
    to_build = [args.process] if args.process else list(PROCESSES)
    for p in to_build:
        build_index_for_process(p)


if __name__ == "__main__":
    main()
