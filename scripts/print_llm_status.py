#!/usr/bin/env python3
"""Print resolved LLM settings and reason trace. Run after venv activation to verify env."""
from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from agent.config import resolve_llm_settings

def main() -> int:
    s = resolve_llm_settings()
    print("effective_llm_mode=" + s.llm_mode + " offline=" + str(s.offline).lower() +
          " cloud_enabled=" + str(s.cloud_enabled).lower() + " local_enabled=" + str(s.local_enabled).lower())
    print("ollama_base_url=" + s.ollama_base_url + " ollama_model=" + s.ollama_model + " timeout_seconds=" + str(s.timeout_seconds))
    for r in s.reason_trace:
        print("  " + r)
    return 0

if __name__ == "__main__":
    sys.exit(main())
