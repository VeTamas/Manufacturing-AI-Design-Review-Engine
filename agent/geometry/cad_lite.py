"""CAD Lite: lightweight geometry fingerprint for bins-mode (bbox, volume, surface area).
Uses OCP (same as numeric pipeline). No feature detection; much faster than full numeric.
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

NAME = "cad_lite"
TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days (same as numeric)

_CACHE: Cache | None = None


def _get_cache() -> Cache:
    global _CACHE
    if _CACHE is None:
        cache_dir = getattr(CONFIG, "cache_dir", "data/outputs/cache")
        _CACHE = Cache(cache_dir)
    return _CACHE


def _compute_metrics(step_path: Path) -> dict[str, Any]:
    """Compute bbox, volume, surface area and derived metrics. Raises on error."""
    from agent.cad.step_ingest import read_step, compute_bbox

    shape = read_step(step_path)

    # Bbox dims
    dx, dy, dz = compute_bbox(shape)
    bbox_dims = (float(dx), float(dy), float(dz))
    min_dim = min(dx, dy, dz)
    eps = 1e-9

    # Volume and surface area via OCP GProp
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp

    vol_props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, vol_props)
    volume = float(vol_props.Mass())

    surf_props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(shape, surf_props)
    surface_area = float(surf_props.Mass())

    # Derived metrics for sheet-metal likelihood
    av_ratio = surface_area / max(volume, eps)  # high for thin shells
    t_est = 2.0 * volume / max(surface_area, eps)  # thin-shell thickness proxy
    t_over_min_dim = t_est / max(min_dim, eps)

    return {
        "bbox_dims": bbox_dims,
        "volume": round(volume, 4),
        "surface_area": round(surface_area, 4),
        "av_ratio": round(av_ratio, 4),
        "t_est": round(t_est, 4),
        "min_dim": round(min_dim, 4),
        "t_over_min_dim": round(t_over_min_dim, 4),
    }


def run_cad_lite(step_path: str | Path, timeout_s: float | None = None) -> dict[str, Any]:
    """
    Run lightweight CAD analysis on STEP file.
    Returns metrics (bbox_dims, volume, surface_area, av_ratio, t_est, min_dim, t_over_min_dim)
    or {"status": "failed"|"timeout"} on error.
    """
    step_path = Path(step_path)
    if not step_path.exists():
        return {"status": "failed"}

    if step_path.suffix.lower() not in (".step", ".stp"):
        return {"status": "failed"}

    timeout = timeout_s
    if timeout is None:
        timeout = float(getattr(CONFIG, "cad_lite_timeout_seconds", 5))

    # Cache by sha256
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
        try:
            metrics = _compute_metrics(step_path)
            result = {"status": "ok", **metrics}
            cache.set(cache_key, result, expire=TTL_SECONDS)
            return result
        except Exception as e:
            logger.warning("CAD Lite failed for %s: %s", step_path, e)
            return {"status": "failed"}

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_run)
            return future.result(timeout=timeout)
    except FuturesTimeoutError:
        logger.warning("CAD Lite timed out after %ss: %s", timeout, step_path)
        return {"status": "timeout"}
