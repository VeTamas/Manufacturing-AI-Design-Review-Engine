"""Sheet metal likelihood from CAD Lite geometry + bins hints.
Deterministic helper used by legacy_bins scorer when cad_status != ok.
"""
from __future__ import annotations

from typing import Literal

from agent.state import GraphState

# Thresholds for t_over_min_dim (thin-shell thickness / min bbox dim)
# high only for thin parts; 0.0945 must not be "high"
T_OVER_MIN_HIGH = 0.06   # strong sheet-metal signal
T_OVER_MIN_MED = 0.10    # moderate signal
THINNESS_BBOX_THRESHOLD = 0.08  # min/max <= this => at least med (bbox_fallback)


def sheet_metal_likelihood(state: GraphState) -> tuple[Literal["low", "med", "high"], str, float | None]:
    """
    Compute sheet-metal likelihood from cad_lite metrics, bbox fallback, and bins hints.

    Returns (likelihood, source, thinness_bbox) where source in ("cad_lite", "bbox_fallback", "bins_only", "none").
    thinness_bbox is set when using bbox_fallback, else None.
    """
    part = state.get("part_summary")
    cad_lite = state.get("cad_lite")

    # Primary: CAD Lite geometry
    if isinstance(cad_lite, dict) and cad_lite.get("status") == "ok":
        t_over = cad_lite.get("t_over_min_dim")
        av_ratio = cad_lite.get("av_ratio")
        bbox_dims = cad_lite.get("bbox_dims")

        if t_over is not None and av_ratio is not None:
            # Compute flatness: sorted dims a >= b >= c, flatness = c/b, thinness = c/a
            flatness = None
            thinness = None
            a_val, b_val, c_val = None, None, None
            if bbox_dims and len(bbox_dims) >= 3:
                dims_sorted_desc = sorted(bbox_dims, reverse=True)  # a >= b >= c
                a_val, b_val, c_val = dims_sorted_desc[0], dims_sorted_desc[1], dims_sorted_desc[2]
                if b_val > 1e-6 and a_val > 1e-6:
                    flatness = c_val / b_val
                    thinness = c_val / a_val
            
            # Permissive flatness gate: flatness <= 0.60 AND thinness <= 0.20
            flat_candidate = (
                flatness is not None and thinness is not None
                and flatness <= 0.60 and thinness <= 0.20
            )
            
            # Determine base likelihood from geometry (not t_over, which was too strict)
            base = "low"
            if flat_candidate:
                # HIGH if: very thin (c <= 6mm) OR very thin ratio (thinness <= 0.08) OR very high av_ratio
                if (c_val is not None and c_val <= 6.0) or (thinness is not None and thinness <= 0.08) or (av_ratio is not None and av_ratio > 50.0):
                    base = "high"
                # MED if: thinness <= 0.15
                elif thinness is not None and thinness <= 0.15:
                    base = "med"
                else:
                    base = "low"
            else:
                # Not flat enough - cap to low (prevents impeller misclassification)
                base = "low"

            # Bins hints: only allow low->med bump; never bump med->high (avoid CNC2 misclass)
            if part:
                hole_depth = getattr(part, "hole_depth_class", None) or ""
                pocket_aspect = getattr(part, "pocket_aspect_class", None) or ""
                feature_variety = getattr(part, "feature_variety", None) or ""

                if hole_depth in ("None", "Unknown") and pocket_aspect == "OK" and base == "low":
                    base = "med"
                if feature_variety == "High":
                    if base == "high":
                        base = "med"
                    elif base == "med":
                        base = "low"

            return base, "cad_lite", None

    # Fallback: bbox-only when cad_lite failed (cheap thinness proxy)
    bbox_fallback = state.get("bbox_fallback")
    if isinstance(bbox_fallback, dict):
        bbox_dims = bbox_fallback.get("bbox_dims")
        if bbox_dims and len(bbox_dims) >= 3:
            min_dim = min(bbox_dims)
            max_dim = max(bbox_dims)
            if max_dim > 0:
                thinness_bbox = min_dim / max_dim
                if thinness_bbox <= THINNESS_BBOX_THRESHOLD:
                    return "med", "bbox_fallback", round(thinness_bbox, 4)

    # Fallback: bins-only hints (no CAD Lite, no bbox)
    if part:
        hole_depth = getattr(part, "hole_depth_class", None) or ""
        pocket_aspect = getattr(part, "pocket_aspect_class", None) or ""
        feature_variety = getattr(part, "feature_variety", None) or ""
        min_wall = getattr(part, "min_wall_thickness", None) or ""
        part_size = getattr(part, "part_size", None) or ""

        if min_wall == "Thin" and part_size in ("Medium", "Large"):
            if hole_depth in ("None", "Unknown") and pocket_aspect == "OK" and feature_variety != "High":
                return "med", "bins_only", None
            if feature_variety == "High":
                return "low", "bins_only", None
            return "med", "bins_only", None

    return "low", "none", None
