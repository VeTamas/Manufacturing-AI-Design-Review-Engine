"""Extrusion Lite: constant cross-section proxy via section planes.
Uses OCP (same as cad_lite). Cached, timeout-protected.
"""
from __future__ import annotations

import hashlib
import logging
import math
from concurrent.futures import TimeoutError as FuturesTimeoutError
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from diskcache import Cache

from agent.config import CONFIG

logger = logging.getLogger(__name__)

NAME = "extrusion_lite"
TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days
SECTION_FRACTIONS = (0.10, 0.30, 0.50, 0.70, 0.90)
NUM_SLICES_PER_AXIS = 31  # Increased sampling for better robustness
TRIM_FRACTION = 0.10  # Ignore first and last 10% of length

_CACHE: Cache | None = None


def _trimmed_coeff_var(values: list[float], trim_frac: float = 0.10) -> float:
    """Compute coefficient of variation on trimmed values (ignore outliers).
    
    Args:
        values: List of numeric values
        trim_frac: Fraction to trim from each end (default 0.10 = 10%)
        
    Returns:
        Coefficient of variation (std/mean) on trimmed data, or NaN if empty
    """
    if not values:
        return float("nan")
    v = sorted(float(x) for x in values)
    n = len(v)
    if n < 5:
        mean = sum(v) / n
        if mean == 0:
            return 0.0
        var = sum((x - mean) ** 2 for x in v) / max(1, n - 1)
        return (var ** 0.5) / abs(mean)

    k = int(n * trim_frac)
    lo, hi = k, n - k
    if hi - lo < 3:
        lo, hi = 0, n

    tv = v[lo:hi]
    mean = sum(tv) / len(tv)
    if mean == 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in tv) / max(1, len(tv) - 1)
    return (var ** 0.5) / abs(mean)


def _get_cache() -> Cache:
    global _CACHE
    if _CACHE is None:
        cache_dir = getattr(CONFIG, "cache_dir", "data/outputs/cache")
        _CACHE = Cache(cache_dir)
    return _CACHE


def _section_area_at(shape: Any, axis: int, frac: float, bbox_xyz: tuple[float, ...]) -> float:
    """Compute section area at fraction along principal axis. Returns 0 on failure."""
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Pnt, gp_Dir, gp_Pln, gp_Ax3
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    dims = (float(xmax - xmin), float(ymax - ymin), float(zmax - zmin))
    margin = max(dims) * 0.6

    # Principal axis: 0=X, 1=Y, 2=Z
    if axis == 0:
        pos = xmin + frac * dims[0]
        normal = gp_Dir(1, 0, 0)
        cx, cy, cz = pos, (ymin + ymax) / 2, (zmin + zmax) / 2
    elif axis == 1:
        pos = ymin + frac * dims[1]
        normal = gp_Dir(0, 1, 0)
        cx, cy, cz = (xmin + xmax) / 2, pos, (zmin + zmax) / 2
    else:
        pos = zmin + frac * dims[2]
        normal = gp_Dir(0, 0, 1)
        cx, cy, cz = (xmin + xmax) / 2, (ymin + ymax) / 2, pos

    pln = gp_Pln(gp_Pnt(cx, cy, cz), normal)
    face_maker = BRepBuilderAPI_MakeFace(pln, -margin, margin, -margin, margin)
    if not face_maker.IsDone():
        return 0.0
    plane_face = face_maker.Face()

    try:
        common = BRepAlgoAPI_Common(shape, plane_face)
        if not common.IsDone():
            return 0.0
        result_shape = common.Shape()
    except Exception:
        return 0.0

    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(result_shape, props)
    return float(props.Mass())


def _compute_extrusion_metrics(step_path: Path) -> dict[str, Any]:
    """Compute section areas and coeff_var. Raises on error.
    
    Enhanced: Evaluates all 3 axes, uses ~31 slices per axis, ignores first/last 10%,
    computes trimmed CV, and selects axis with lowest CV.
    """
    from agent.cad.step_ingest import read_step, compute_bbox

    shape = read_step(step_path)
    dx, dy, dz = compute_bbox(shape)
    bbox_dims = (float(dx), float(dy), float(dz))
    dims_sorted = sorted(bbox_dims, reverse=True)
    long_dim = dims_sorted[0]
    mid_dim = dims_sorted[1] if len(dims_sorted) > 1 else dims_sorted[0]

    eps = 1e-12
    
    # Evaluate all 3 axes and select the one with lowest trimmed CV
    best_axis_idx = 0
    best_axis_name = "X"
    best_areas: list[float] = []
    best_cv = float("inf")
    best_mean_area = 0.0
    
    for axis_idx in range(3):
        axis_name = ("X", "Y", "Z")[axis_idx]
        
        # Generate ~31 slices, ignoring first and last 10%
        n_slices = NUM_SLICES_PER_AXIS
        areas: list[float] = []
        
        # Skip first 10% and last 10%: sample from 0.10 to 0.90
        trim_start = TRIM_FRACTION
        trim_end = 1.0 - TRIM_FRACTION
        for i in range(n_slices):
            # Map i from [0, n_slices-1] to [trim_start, trim_end]
            frac = trim_start + (trim_end - trim_start) * (i / max(1, n_slices - 1))
            a = _section_area_at(shape, axis_idx, frac, (0, 0, 0, dx, dy, dz))
            if a > eps:  # Only collect valid areas
                areas.append(a)
        
        if not areas:
            continue
            
        # Compute trimmed coefficient of variation
        cv = _trimmed_coeff_var(areas, trim_frac=TRIM_FRACTION)
        mean_area = sum(areas) / len(areas)
        
        # Track best axis (lowest CV)
        if not math.isnan(cv) and cv < best_cv:
            best_cv = cv
            best_axis_idx = axis_idx
            best_axis_name = axis_name
            best_areas = areas
            best_mean_area = mean_area
    
    # Fallback: if no valid areas found, use legacy single-axis approach
    if not best_areas:
        axis_idx = bbox_dims.index(long_dim)
        axis_name = ("X", "Y", "Z")[axis_idx]
        areas: list[float] = []
        for frac in SECTION_FRACTIONS:
            a = _section_area_at(shape, axis_idx, frac, (0, 0, 0, dx, dy, dz))
            areas.append(a)
        
        mean_area = sum(areas) / len(areas) if areas else 0.0
        if mean_area <= eps:
            return {
                "status": "ok",
                "axis": axis_name,
                "bbox_dims": bbox_dims,
                "section_areas": [round(a, 6) for a in areas],
                "mean_area": 0.0,
                "coeff_var": 1.0,
                "robust_coeff_var": 1.0,
            }
        
        variance = sum((a - mean_area) ** 2 for a in areas) / len(areas)
        stdev = math.sqrt(variance)
        coeff_var = stdev / mean_area if mean_area > eps else 1.0
        
        # Robust coeff_var: trimmed middle 60% (drop top/bottom 20%)
        robust_coeff_var = coeff_var
        if len(areas) >= 3:
            sorted_areas = sorted(areas)
            n = len(sorted_areas)
            drop = max(0, (n - 1) // 5)
            trimmed = sorted_areas[drop : n - drop] if drop > 0 else sorted_areas
            if len(trimmed) >= 2:
                t_mean = sum(trimmed) / len(trimmed)
                t_var = sum((a - t_mean) ** 2 for a in trimmed) / len(trimmed)
                t_stdev = math.sqrt(t_var)
                robust_coeff_var = t_stdev / t_mean if t_mean > eps else coeff_var
        
        logger.info(
            f"extrusion_lite axis={axis_name} slices={len(areas)} coeff_var={coeff_var:.4f}"
        )
        
        return {
            "status": "ok",
            "axis": axis_name,
            "bbox_dims": bbox_dims,
            "section_areas": [round(a, 6) for a in areas],
            "mean_area": round(mean_area, 6),
            "coeff_var": round(coeff_var, 6),
            "robust_coeff_var": round(robust_coeff_var, 6),
        }
    
    # Compute legacy coeff_var for backward compatibility
    variance = sum((a - best_mean_area) ** 2 for a in best_areas) / len(best_areas)
    stdev = math.sqrt(variance)
    coeff_var = stdev / best_mean_area if best_mean_area > eps else 1.0
    
    # Robust coeff_var: trimmed middle 60% (drop top/bottom 20%)
    robust_coeff_var = best_cv if not math.isnan(best_cv) else coeff_var
    if len(best_areas) >= 3:
        sorted_areas = sorted(best_areas)
        n = len(sorted_areas)
        drop = max(0, (n - 1) // 5)
        trimmed = sorted_areas[drop : n - drop] if drop > 0 else sorted_areas
        if len(trimmed) >= 2:
            t_mean = sum(trimmed) / len(trimmed)
            t_var = sum((a - t_mean) ** 2 for a in trimmed) / len(trimmed)
            t_stdev = math.sqrt(t_var)
            robust_coeff_var = t_stdev / t_mean if t_mean > eps else coeff_var
    
    logger.info(
        f"extrusion_lite axis={best_axis_name} slices={len(best_areas)} coeff_var={best_cv:.4f}"
    )
    
    return {
        "status": "ok",
        "axis": best_axis_name,
        "bbox_dims": bbox_dims,
        "section_areas": [round(a, 6) for a in best_areas],
        "mean_area": round(best_mean_area, 6),
        "coeff_var": round(coeff_var, 6),
        "robust_coeff_var": round(robust_coeff_var, 6),
    }


def run_extrusion_lite(step_path: str | Path, timeout_s: float | None = None) -> dict[str, Any]:
    """
    Run constant cross-section analysis on STEP file.
    Returns extrusion_lite dict or {"status": "failed"|"timeout"} on error.
    """
    step_path = Path(step_path)
    if not step_path.exists():
        return {"status": "failed"}

    if step_path.suffix.lower() not in (".step", ".stp"):
        return {"status": "failed"}

    timeout = timeout_s
    if timeout is None:
        timeout = float(getattr(CONFIG, "extrusion_lite_timeout_seconds", 10))

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
            result = _compute_extrusion_metrics(step_path)
            cache.set(cache_key, result, expire=TTL_SECONDS)
            return result
        except Exception as e:
            logger.warning("Extrusion Lite failed for %s: %s", step_path, e)
            return {"status": "failed"}

    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_run)
            return future.result(timeout=timeout)
    except FuturesTimeoutError:
        logger.warning("Extrusion Lite timed out after %ss: %s", timeout, step_path)
        return {"status": "timeout"}
