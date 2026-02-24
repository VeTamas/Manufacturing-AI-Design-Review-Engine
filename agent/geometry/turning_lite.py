"""Turning Lite: lathe-like geometry detection via bbox dims only.
Uses OCP (same as cad_lite). Cached, timeout-protected.
"""
from __future__ import annotations

import hashlib
import logging
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from diskcache import Cache

from agent.config import CONFIG

logger = logging.getLogger(__name__)

NAME = "turning_lite"
TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days

_CACHE: Cache | None = None


def _get_cache() -> Cache:
    global _CACHE
    if _CACHE is None:
        cache_dir = getattr(CONFIG, "cache_dir", "data/outputs/cache")
        _CACHE = Cache(cache_dir)
    return _CACHE


def _fmt(x: float | None) -> str:
    """Format float or return 'N/A' if None."""
    return "N/A" if x is None else f"{x:.3f}"


def _compute_turning_metrics(step_path: Path) -> dict[str, Any]:
    """Compute turning geometry metrics from bbox dims only.
    
    Heuristic: sorted dims ascending a<=b<=c
    - If (b/a) <= 1.10 AND (c/b) >= 2.5 then level="high"
    - Else if (b/a) <= 1.20 AND (c/b) >= 2.0 then level="med"
    - Else level="low"
    
    Returns dict with status="ok" or status="error" (never raises).
    """
    try:
        from agent.cad.step_ingest import read_step, compute_bbox

        shape = read_step(step_path)
        dx, dy, dz = compute_bbox(shape)
        bbox_dims = (float(dx), float(dy), float(dz))
        dims_sorted_asc = sorted(bbox_dims)  # a <= b <= c
        a = dims_sorted_asc[0]
        b = dims_sorted_asc[1] if len(dims_sorted_asc) > 1 else dims_sorted_asc[0]
        c = dims_sorted_asc[2] if len(dims_sorted_asc) > 2 else dims_sorted_asc[0]
        
        # Determine turning axis (longest dimension)
        dims_sorted_desc = sorted(bbox_dims, reverse=True)
        max_dim = dims_sorted_desc[0]
        if max_dim == dx:
            turning_axis = "X"
        elif max_dim == dy:
            turning_axis = "Y"
        else:
            turning_axis = "Z"
        
        # Compute roundness and slenderness: sorted dims descending a >= b >= c
        dims_sorted_desc = sorted(bbox_dims, reverse=True)  # a >= b >= c
        a_desc = dims_sorted_desc[0]
        b_desc = dims_sorted_desc[1] if len(dims_sorted_desc) > 1 else dims_sorted_desc[0]
        c_desc = dims_sorted_desc[2] if len(dims_sorted_desc) > 2 else dims_sorted_desc[0]
        
        roundness = None
        slenderness = None
        level = "low"
        ratio_ab = None
        ratio_cb = None
        
        if b_desc > 1e-6 and c_desc > 1e-6:
            # Roundness: abs(b - c) / max(b, c) - how similar are the two smaller dims?
            roundness = abs(b_desc - c_desc) / max(b_desc, c_desc)
            # Slenderness: a / max(b, c) - how long is the part relative to cross-section?
            slenderness = a_desc / max(b_desc, c_desc)
            
            # Relaxed thresholds: HIGH if roundness <= 0.15 AND slenderness >= 1.60
            # MED if roundness <= 0.20 AND slenderness >= 1.40
            if roundness <= 0.15 and slenderness >= 1.60:
                level = "high"
            elif roundness <= 0.20 and slenderness >= 1.40:
                level = "med"
            else:
                level = "low"
        
        # Legacy ratios for backward compatibility (using ascending order)
        if a <= 1e-6 or b <= 1e-6:
            ratio_ab = None
            ratio_cb = None
        else:
            ratio_ab = b / a
            ratio_cb = c / b if b > 1e-6 else None
        
        # Safe formatting for debug log
        roundness_s = _fmt(roundness)
        slenderness_s = _fmt(slenderness)
        ratio_ab_s = _fmt(ratio_ab)
        ratio_cb_s = _fmt(ratio_cb)
        logger.info(
            f"turning_lite status=ok level={level} dims=({a_desc:.1f},{b_desc:.1f},{c_desc:.1f}) "
            f"roundness={roundness_s} slenderness={slenderness_s} axis={turning_axis}"
        )
        
        return {
            "status": "ok",
            "bbox_dims": bbox_dims,
            "level": level,
            "source": "bbox",
            "turning_axis": turning_axis,
            "roundness": round(roundness, 4) if roundness is not None else None,
            "slenderness": round(slenderness, 4) if slenderness is not None else None,
            "ratio_ab": round(ratio_ab, 4) if ratio_ab is not None else None,
            "ratio_cb": round(ratio_cb, 4) if ratio_cb is not None else None,
        }
    except Exception as e:
        logger.warning("Turning Lite computation error for %s: %s", step_path, e)
        return {
            "status": "error",
            "level": "low",
            "reason": str(e)[:100] if e else "unknown error",
        }


def run_turning_lite(step_path: str | Path, timeout_s: float | None = None) -> dict[str, Any]:
    """
    Run turning geometry detection on STEP file.
    Returns turning_lite dict or {"status": "failed"|"timeout"} on error.
    """
    step_path = Path(step_path)
    if not step_path.exists():
        return {"status": "failed"}

    if step_path.suffix.lower() not in (".step", ".stp"):
        return {"status": "failed"}

    timeout = timeout_s
    if timeout is None:
        timeout = float(getattr(CONFIG, "cad_lite_timeout_seconds", 5))

    try:
        step_bytes = step_path.read_bytes()
    except Exception:
        return {"status": "failed"}

    cache_key = hashlib.sha256(step_bytes).hexdigest() + NAME
    cache = _get_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    def _run() -> dict[str, Any]:
        result = _compute_turning_metrics(step_path)
        # Only cache successful results
        if result.get("status") == "ok":
            cache.set(cache_key, result, expire=TTL_SECONDS)
        return result

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_run)
            return future.result(timeout=timeout)
    except FuturesTimeoutError:
        logger.warning("Turning Lite timed out after %ss: %s", timeout, step_path)
        return {"status": "timeout"}
