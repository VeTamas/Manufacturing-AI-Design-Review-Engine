"""Extrusion likelihood from extrusion_lite geometry.
Deterministic helper used by legacy_bins scorer when cad_status != ok.
"""
from __future__ import annotations

from agent.state import GraphState


def extrusion_likelihood(state: GraphState) -> dict:
    """
    Compute extrusion likelihood from extrusion_lite metrics.

    Returns {"level": "high"|"med"|"low"|"none", "source": "extrusion_lite"|"none"}.
    """
    extrusion_lite = state.get("extrusion_lite")

    if not isinstance(extrusion_lite, dict) or extrusion_lite.get("status") != "ok":
        return {"level": "none", "source": "none"}

    coeff_var = extrusion_lite.get("coeff_var")
    robust_coeff_var = extrusion_lite.get("robust_coeff_var", coeff_var)
    cv = robust_coeff_var if robust_coeff_var is not None else coeff_var
    bbox_dims = extrusion_lite.get("bbox_dims")
    if cv is None or not bbox_dims or len(bbox_dims) < 3:
        return {"level": "none", "source": "extrusion_lite"}

    dims_sorted = sorted(bbox_dims, reverse=True)
    bbox_long = dims_sorted[0]
    bbox_mid = dims_sorted[1] if len(dims_sorted) > 1 else dims_sorted[0]
    bbox_min = dims_sorted[2] if len(dims_sorted) > 2 else dims_sorted[0]
    axis = extrusion_lite.get("axis", "?")

    if bbox_mid <= 0:
        return {"level": "none", "source": "extrusion_lite"}

    ld_ratio = bbox_long / bbox_mid
    
    # Axis ratio: extrusion axis length / max(other two dims)
    # This prevents false positives on impeller-like rotational solids
    axis_ratio = bbox_long / max(bbox_mid, bbox_min) if max(bbox_mid, bbox_min) > 1e-6 else None

    # Updated thresholds: HIGH <= 0.20, MED <= 0.35, else LOW
    # But cap to LOW if axis_ratio < 1.30 (not meaningfully elongated)
    if cv <= 0.20:
        level = "high"
    elif cv <= 0.35:
        level = "med"
    else:
        level = "low"
    
    # Axis ratio gate: extrusion must be meaningfully elongated
    if axis_ratio is not None and axis_ratio < 1.30:
        level = "low"  # Cap to LOW even if coeff_var is good
    
    return {
        "level": level,
        "source": "extrusion_lite",
        "coeff_var": cv,
        "robust_coeff_var": robust_coeff_var,
        "axis": axis,
        "ld_ratio": round(ld_ratio, 2) if ld_ratio else None,
        "axis_ratio": round(axis_ratio, 3) if axis_ratio is not None else None,
    }
