"""CNC-only numeric → bins + evidence adapter. Maps numeric metrics to PartSummary bins and builds evidence dict."""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from agent.state import PartSummary

# Threshold constants (conservative placeholders, easy to tune)
WALL_LOW_MM = 1.0
WALL_MEDIUM_MM = 2.5
RADIUS_LOW_MM = 0.5
RADIUS_MEDIUM_MM = 1.5
ACCESS_HIGH = 0.70
ACCESS_MEDIUM = 0.40
CNC_ACCESS_MIN_FACES = 20

# Valid evidence keys only (no derived/guessed fields)
VALID_EVIDENCE_KEYS = frozenset({
    "min_wall_thickness_mm", "min_internal_radius_mm", "thin_wall_flag",
    "tool_access_proxy", "bounding_box_mm", "volume_mm3", "surface_area_mm2",
})


def _valid_float(v: Any) -> float | None:
    """Return float if valid and finite, else None."""
    if v is None:
        return None
    try:
        f = float(v)
        return f if f == f and abs(f) != float("inf") else None
    except (TypeError, ValueError):
        return None


def _faces_count(part_metrics: dict[str, Any]) -> int:
    """Return face count; handles int or list (for future flexibility)."""
    faces = part_metrics.get("faces")
    if faces is None:
        return 0
    if isinstance(faces, (list, tuple)):
        return len(faces)
    try:
        return int(faces)
    except (TypeError, ValueError):
        return 0


def apply_numeric_to_bins(part_summary: PartSummary, part_metrics: dict[str, Any]) -> tuple[PartSummary, dict[str, Any]]:
    """
    Map numeric metrics to PartSummary bins (CNC numeric mode only).
    Internal mapping: Low/Medium/High -> Thin/Medium/Thick (wall) or Small/Medium/Large (radius).
    Only override when value present and valid.
    Returns (updated_part_summary, evidence_dict).
    """
    evidence: dict[str, Any] = {}
    updates: dict[str, Any] = {}

    min_wall_mm = _valid_float(part_metrics.get("min_wall_thickness_mm"))
    if min_wall_mm is not None:
        evidence["min_wall_thickness_mm"] = min_wall_mm
        if min_wall_mm <= WALL_LOW_MM:
            updates["min_wall_thickness"] = "Thin"  # Low -> Thin
        elif min_wall_mm <= WALL_MEDIUM_MM:
            updates["min_wall_thickness"] = "Medium"
        else:
            updates["min_wall_thickness"] = "Thick"  # High -> Thick

    min_radius_mm = _valid_float(part_metrics.get("min_internal_radius_mm"))
    if min_radius_mm is not None:
        evidence["min_internal_radius_mm"] = min_radius_mm
        if min_radius_mm <= RADIUS_LOW_MM:
            updates["min_internal_radius"] = "Small"  # Low -> Small
        elif min_radius_mm <= RADIUS_MEDIUM_MM:
            updates["min_internal_radius"] = "Medium"
        else:
            updates["min_internal_radius"] = "Large"  # High -> Large

    tool_access = _valid_float(part_metrics.get("tool_access_proxy"))
    faces_ok = _faces_count(part_metrics) >= CNC_ACCESS_MIN_FACES
    if tool_access is not None and faces_ok:
        evidence["tool_access_proxy"] = tool_access
        if tool_access >= ACCESS_HIGH:
            updates["accessibility_risk"] = "High"
        elif tool_access >= ACCESS_MEDIUM:
            updates["accessibility_risk"] = "Medium"
        else:
            updates["accessibility_risk"] = "Low"
    elif tool_access is not None:
        evidence["tool_access_proxy"] = tool_access

    # Evidence: only valid keys
    for key in VALID_EVIDENCE_KEYS:
        v = part_metrics.get(key)
        if v is not None and key not in evidence:
            evidence[key] = v

    updated = replace(part_summary, **updates) if updates else part_summary
    return updated, evidence
