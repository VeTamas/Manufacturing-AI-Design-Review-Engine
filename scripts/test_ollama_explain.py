"""Test script for Ollama explain node (local mode).

Run on Windows PowerShell:
    $env:LLM_MODE="local"
    $env:OLLAMA_BASE_URL="http://localhost:11434"
    $env:OLLAMA_MODEL="jamba2-3b-q6k"
    python scripts/test_ollama_explain.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Set env vars before importing agent modules
os.environ["LLM_MODE"] = os.getenv("LLM_MODE", "local")
os.environ["OLLAMA_BASE_URL"] = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
os.environ["OLLAMA_MODEL"] = os.getenv("OLLAMA_MODEL", "jamba2-3b-q6k")

# Add project root to path
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from agent.nodes.explain import explain_node
from agent.state import Finding, GraphState, Inputs, Severity


def main():
    """Test explain_node with local Ollama."""
    print("=" * 60)
    print("Testing Ollama explain node (local mode)")
    print("=" * 60)
    print(f"LLM_MODE: {os.getenv('LLM_MODE')}")
    print(f"OLLAMA_BASE_URL: {os.getenv('OLLAMA_BASE_URL')}")
    print(f"OLLAMA_MODEL: {os.getenv('OLLAMA_MODEL')}")
    print()

    # Create minimal GraphState compatible with explain_node
    inputs = Inputs(
        process="CNC",
        material="Aluminum",
        production_volume="Small batch",
        load_type="Static",
        tolerance_criticality="Medium",
    )

    findings = [
        Finding(
            id="CNC1",
            category="DFM",
            severity="HIGH",
            title="Deep pocket detected",
            why_it_matters="Deep pockets require longer tool paths and may need specialized tools.",
            recommendation="Consider reducing pocket depth or splitting into multiple operations.",
        ),
        Finding(
            id="CNC2",
            category="DESIGN_REVIEW",
            severity="MEDIUM",
            title="Sharp internal corners",
            why_it_matters="Sharp corners require expensive EDM or manual finishing.",
            recommendation="Add fillets (R ≥ 0.5mm) to internal corners where possible.",
        ),
    ]

    state: GraphState = {
        "inputs": inputs,
        "findings": findings,
        "rag_enabled": False,
    }

    print("Calling explain_node...")
    print()
    result = explain_node(state)

    if "error" in result:
        print("ERROR:")
        print(f"  Type: {result['error'].type}")
        print(f"  Message: {result['error'].message}")
        print(f"  Retry exhausted: {result['error'].retry_exhausted}")
        print("TRACE (on failure):")
        for msg in result.get("trace", []):
            print(f"  - {msg}")
        sys.exit(1)

    trace_list = result.get("trace", [])
    if os.getenv("LLM_MODE", "").strip().lower() == "local":
        assert any("attempting local Ollama call" in (t or "") for t in trace_list), (
            "Local mode must attempt Ollama; trace should contain 'attempting local Ollama call'. "
            f"Trace: {trace_list}"
        )
        assert not any("offline fallback (no LLM)" in (t or "") for t in trace_list), (
            "Local mode must not use offline fallback. Trace: " + str(trace_list)
        )

    print("TRACE:")
    for msg in trace_list:
        print(f"  - {msg}")
    print()

    print("ACTIONS:")
    for i, action in enumerate(result.get("actions", []), 1):
        print(f"  {i}. {action}")
    print()

    print("ASSUMPTIONS:")
    for i, assumption in enumerate(result.get("assumptions", []), 1):
        print(f"  {i}. {assumption}")
    print()

    print("USAGE:")
    usage = result.get("usage", {})
    for key, value in usage.items():
        print(f"  {key}: {value}")
    print()

    print("=" * 60)
    print("Test completed successfully!")
    print("=" * 60)


if __name__ == "__main__":
    main()
