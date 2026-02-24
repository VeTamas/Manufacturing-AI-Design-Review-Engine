"""
Deterministic bin derivation from CAD geometry (no LLM). Pure functions, conservative thresholds.

Portfolio: production may use additional bin boundaries and internal optimization layers;
this module keeps architecture clarity with simplified placeholder thresholds.
"""
from __future__ import annotations

from typing import Any

# Part size: max dimension in mm
PART_SIZE_SMALL_MM = 100.0
PART_SIZE_MEDIUM_MM = 300.0
# > PART_SIZE_MEDIUM_MM -> Large

# Feature variety: face count (conservative)
FEATURE_FACES_LOW = 200
FEATURE_FACES_HIGH = 800

# Slender part: max_dim / min_dim > SLENDER_RATIO -> higher accessibility risk
SLENDER_RATIO = 6.0

# Clamping heuristic: min bbox dim < 3 mm and max > 50 mm -> likely sheet-like
BBOX_SHEET_MIN_MM = 3.0
BBOX_SHEET_MAX_MM = 50.0


def bin_part_size(max_dim_mm: float) -> str:
    """Small (<=100), Medium (100–300), Large (>300) from max bounding box dimension (mm)."""
    if max_dim_mm <= PART_SIZE_SMALL_MM:
        return "Small"
    if max_dim_mm <= PART_SIZE_MEDIUM_MM:
        return "Medium"
    return "Large"


def bin_feature_variety(faces: int, edges: int) -> str:
    """Low (faces < 200), Medium (200–800), High (> 800). Conservative; edges unused in MVP."""
    if faces < FEATURE_FACES_LOW:
        return "Low"
    if faces <= FEATURE_FACES_HIGH:
        return "Medium"
    return "High"


def bin_accessibility_risk(feature_variety: str, bbox_dims: tuple[float, float, float]) -> str:
    """
    If feature_variety == High -> High.
    Else if max_dim / min_dim > 6 (very slender) -> Medium.
    Else -> Low.
    """
    if feature_variety == "High":
        return "High"
    dx, dy, dz = bbox_dims
    dims = [d for d in (dx, dy, dz) if d > 0]
    if not dims:
        return "Low"
    min_d, max_d = min(dims), max(dims)
    if min_d <= 0:
        return "Low"
    if max_d / min_d > SLENDER_RATIO:
        return "Medium"
    return "Low"


def infer_has_clamping_faces(bbox_dims: tuple[float, float, float]) -> bool:
    """
    MVP heuristic: True when part has reasonably large planar footprint.
    If min(bbox_dims) < 3 mm and max(bbox_dims) > 50 mm -> likely sheet-like -> True.
    Otherwise True (conservative; avoid false negatives).
    """
    if not bbox_dims:
        return True
    min_d = min(bbox_dims)
    max_d = max(bbox_dims)
    if min_d < BBOX_SHEET_MIN_MM and max_d > BBOX_SHEET_MAX_MM:
        return True
    return True


def cad_bins_from_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """
    Return only: part_size, feature_variety, accessibility_risk, has_clamping_faces.
    Other PartSummary fields are not guessed; leave them unchanged by caller.
    """
    dx = metrics.get("dx_mm", 0.0)
    dy = metrics.get("dy_mm", 0.0)
    dz = metrics.get("dz_mm", 0.0)
    faces = metrics.get("faces", 0)
    edges = metrics.get("edges", 0)
    bbox_dims = (dx, dy, dz)
    max_dim = max(dx, dy, dz)

    part_size = bin_part_size(max_dim)
    feature_variety = bin_feature_variety(faces, edges)
    accessibility_risk = bin_accessibility_risk(feature_variety, bbox_dims)
    has_clamping_faces = infer_has_clamping_faces(bbox_dims)

    return {
        "part_size": part_size,
        "feature_variety": feature_variety,
        "accessibility_risk": accessibility_risk,
        "has_clamping_faces": has_clamping_faces,
    }
