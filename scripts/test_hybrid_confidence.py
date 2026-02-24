#!/usr/bin/env python3
"""Test script for hybrid confidence scoring system.

Verifies that deterministic_confidence is stable across runs when LLM delta fallback is used.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Load environment variables (optional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not required for test

from agent.nodes.self_review import self_review_node
from agent.state import GraphState, Inputs, PartSummary, Finding

# Set LLM_MODE to force fallback (or use local with invalid model to trigger fallback)
os.environ["LLM_MODE"] = "local"
os.environ["OLLAMA_MODEL"] = "nonexistent-model-to-trigger-fallback"


def create_test_state() -> GraphState:
    """Create a test GraphState for confidence testing."""
    inputs = Inputs(
        process="CNC",
        material="Aluminum",
        production_volume="Production",
        load_type="Static",
        tolerance_criticality="High",
    )
    
    part = PartSummary(
        part_size="Medium",
        min_internal_radius="Medium",
        min_wall_thickness="Medium",
        hole_depth_class="Moderate",
        pocket_aspect_class="OK",
        feature_variety="Medium",
        accessibility_risk="Low",
        has_clamping_faces=True,
    )
    
    findings = [
        Finding(
            id="CNC1",
            category="DFM",
            severity="HIGH",
            title="Thin wall risk",
            why_it_matters="Thin walls may cause machining issues",
            recommendation="Increase wall thickness to 2mm minimum.",
        ),
        Finding(
            id="CNC2",
            category="DFM",
            severity="MEDIUM",
            title="Tool access concern",
            why_it_matters="Some features may be hard to reach",
            recommendation="Review tool paths and accessibility.",
        ),
    ]
    
    return {
        "inputs": inputs,
        "part_summary": part,
        "findings": findings,
        "actions": ["Review findings", "Apply DFM improvements"],
        "assumptions": ["Inputs reflect design intent"],
        "sources": [],
        "rag_enabled": False,
        "confidence_inputs": None,
        "process_recommendation": {
            "primary": "CNC",
            "secondary": [],
            "not_recommended": [],
            "scores": {"CNC": 5},
        },
    }


def test_deterministic_stability():
    """Test that deterministic_confidence is identical across runs."""
    print("Testing hybrid confidence scoring system...")
    print("=" * 60)
    
    state1 = create_test_state()
    state2 = create_test_state()
    
    # Run self_review twice
    print("\nRun 1:")
    result1 = self_review_node(state1)
    conf1 = result1.get("confidence")
    
    print("\nRun 2:")
    result2 = self_review_node(state2)
    conf2 = result2.get("confidence")
    
    # Verify deterministic_confidence is identical
    det_conf1 = conf1.deterministic_confidence if conf1 else None
    det_conf2 = conf2.deterministic_confidence if conf2 else None
    
    print(f"\nRun 1 - deterministic_confidence: {det_conf1}")
    print(f"Run 2 - deterministic_confidence: {det_conf2}")
    
    if det_conf1 is None or det_conf2 is None:
        print("ERROR: deterministic_confidence is None!")
        return False
    
    if abs(det_conf1 - det_conf2) > 0.001:
        print(f"ERROR: deterministic_confidence differs! ({det_conf1} vs {det_conf2})")
        return False
    
    # Verify final_confidence is identical (when LLM fallback is used)
    final_conf1 = conf1.final_confidence if conf1 else None
    final_conf2 = conf2.final_confidence if conf2 else None
    
    print(f"\nRun 1 - final_confidence: {final_conf1}")
    print(f"Run 2 - final_confidence: {final_conf2}")
    
    if final_conf1 is None or final_conf2 is None:
        print("ERROR: final_confidence is None!")
        return False
    
    if abs(final_conf1 - final_conf2) > 0.001:
        print(f"ERROR: final_confidence differs! ({final_conf1} vs {final_conf2})")
        return False
    
    # Verify llm_delta is 0.0 when fallback is used
    llm_delta1 = conf1.llm_delta if conf1 else None
    llm_delta2 = conf2.llm_delta if conf2 else None
    
    print(f"\nRun 1 - llm_delta: {llm_delta1}")
    print(f"Run 2 - llm_delta: {llm_delta2}")
    
    if llm_delta1 != 0.0 or llm_delta2 != 0.0:
        print(f"WARNING: llm_delta is not 0.0 (fallback expected)")
        print("This is OK if LLM actually succeeded, but test assumes fallback.")
    
    # Verify final_confidence = deterministic_confidence + llm_delta
    computed1 = det_conf1 + llm_delta1
    computed2 = det_conf2 + llm_delta2
    
    # Clamp to [0.30, 0.95]
    computed1 = max(0.30, min(0.95, computed1))
    computed2 = max(0.30, min(0.95, computed2))
    
    if abs(computed1 - final_conf1) > 0.01 or abs(computed2 - final_conf2) > 0.01:
        print(f"ERROR: final_confidence != clamp(deterministic + delta, 0.30..0.95)")
        print(f"  Run 1: {final_conf1} != clamp({det_conf1} + {llm_delta1}, 0.30..0.95) = {computed1}")
        print(f"  Run 2: {final_conf2} != clamp({det_conf2} + {llm_delta2}, 0.30..0.95) = {computed2}")
        return False
    
    print("\n" + "=" * 60)
    print("✓ All tests passed!")
    print(f"  deterministic_confidence: {det_conf1:.2f} (stable)")
    print(f"  llm_delta: {llm_delta1:.2f}")
    print(f"  final_confidence: {final_conf1:.2f} (stable)")
    return True


if __name__ == "__main__":
    success = test_deterministic_stability()
    sys.exit(0 if success else 1)
