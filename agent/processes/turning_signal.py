"""Turning likelihood from turning_lite geometry.
Deterministic helper used by legacy_bins scorer when cad_status != ok.
"""
from __future__ import annotations

from agent.state import GraphState


def turning_likelihood(state: GraphState) -> dict:
    """
    Compute turning likelihood from turning_lite metrics.

    Returns {"level": "high"|"med"|"low"|"none", "source": "turning_lite"|"none"}.
    """
    turning_lite = state.get("turning_lite")

    if not isinstance(turning_lite, dict) or turning_lite.get("status") != "ok":
        return {"level": "none", "source": "none"}

    level = turning_lite.get("level", "low")
    source = turning_lite.get("source", "bbox")
    bbox_dims = turning_lite.get("bbox_dims")
    
    if not bbox_dims or len(bbox_dims) < 3:
        return {"level": "none", "source": "none"}

    if level == "low":
        return {"level": "none", "source": "none"}
    
    return {
        "level": level,
        "source": "turning_lite",
        "turning_axis": turning_lite.get("turning_axis"),
        "ratio_ab": turning_lite.get("ratio_ab"),
        "ratio_cb": turning_lite.get("ratio_cb"),
    }
