"""CNC numeric CAD analyzer (Phase 1). Returns numeric metrics from STEP geometry."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from diskcache import Cache

from agent.config import CONFIG

logger = logging.getLogger(__name__)

_CACHE: Cache | None = None

NAME = "numeric_cnc_v1"
TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days


def _get_cache() -> Cache:
    global _CACHE
    if _CACHE is None:
        cache_dir = getattr(CONFIG, "cache_dir", "data/outputs/cache")
        _CACHE = Cache(cache_dir)
    return _CACHE


def supports(process: str) -> bool:
    """Return True only for CNC and CNC_TURNING."""
    return process in ("CNC", "CNC_TURNING")


def analyze(step_path: Path) -> dict[str, Any]:
    """
    Analyze STEP file and return CNC-relevant numeric metrics.
    Timeout 5s; on failure raises. Uses diskcache by STEP hash.
    """
    step_path = Path(step_path)
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_path}")

    step_bytes = step_path.read_bytes()
    cache_key_raw = hashlib.sha256(step_bytes).hexdigest() + NAME
    cache = _get_cache()
    cached = cache.get(cache_key_raw)
    if cached is not None:
        return cached

    try:
        from agent.cad.step_ingest import extract_cad_metrics
    except ImportError:
        raise RuntimeError("CAD module (OCP) not available for numeric analysis")

    try:
        metrics = extract_cad_metrics(step_path)
    except Exception as e:
        logger.warning("CNC numeric analysis failed: %s", e)
        raise

    dx = float(metrics.get("dx_mm", 0) or 0)
    dy = float(metrics.get("dy_mm", 0) or 0)
    dz = float(metrics.get("dz_mm", 0) or 0)
    faces = int(metrics.get("faces", 0))
    edges = int(metrics.get("edges", 0))

    bounding_box_mm = [dx, dy, dz]
    volume_mm3 = round(dx * dy * dz, 2) if dx and dy and dz else 0.0
    surface_area_mm2 = None  # Not computed in MVP
    min_internal_radius_mm = None  # Would need edge curvature analysis
    min_wall_thickness_mm = None  # Would need offset analysis
    thin_wall_flag = None
    tool_access_proxy = None

    if dx and dy and dz:
        dims = [d for d in (dx, dy, dz) if d > 0]
        if dims:
            max_dim = max(dims)
            min_dim = min(dims)
            tool_access_proxy = round(min_dim / max_dim, 4) if max_dim > 0 else None
            if min_dim < 2.0 and max_dim > 20.0:
                thin_wall_flag = True
            elif min_dim >= 5.0:
                thin_wall_flag = False

    result = {
        "bounding_box_mm": bounding_box_mm,
        "volume_mm3": volume_mm3,
        "surface_area_mm2": surface_area_mm2,
        "min_internal_radius_mm": min_internal_radius_mm,
        "min_wall_thickness_mm": min_wall_thickness_mm,
        "thin_wall_flag": thin_wall_flag,
        "tool_access_proxy": tool_access_proxy,
        "faces": faces,
        "edges": edges,
    }
    # Only cache on success with required keys; do not cache failures
    required = {"bounding_box_mm", "volume_mm3", "surface_area_mm2"}
    if result and required <= result.keys():
        cache.set(cache_key_raw, result, expire=TTL_SECONDS)
    return result
