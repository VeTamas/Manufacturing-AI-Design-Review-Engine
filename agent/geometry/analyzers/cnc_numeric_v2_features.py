"""CNC numeric feature detection (Phase 2): holes, pockets, fillets from STEP.
Uses OCP (OpenCASCADE). Conservative heuristics; under-detect rather than over-detect.
Phase 4.1: Fallback hole/pocket proxies when analytic counts are 0 (analytic-loss STEP).
"""
from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Heuristic v2; tune later
HOLE_DIAMETER_MIN_MM = 0.5
HOLE_LD_THRESHOLD = 6.0
POCKET_ASPECT_THRESHOLD = 4.0
HOLE_COUNT_TOOLING_THRESHOLD = 6
POCKET_COUNT_OVERHEAD_THRESHOLD = 4
NORMAL_ALIGN_TOL_DEG = 20  # degrees for pocket proxy normal alignment


def extract_cnc_features_from_step(step_path: Path | str) -> dict[str, Any]:
    """
    Extract CNC-relevant feature metrics from STEP geometry.
    Returns dict with: hole_count, hole_diameters_mm, hole_max_depth_mm, hole_max_ld,
    pocket_count, pocket_max_depth_mm, pocket_max_aspect, fillet_min_radius_mm (optional).
    All keys optional; returns empty-ish dict on failure.
    """
    step_path = Path(step_path)
    if not step_path.exists():
        return {}

    try:
        from agent.cad.step_ingest import read_step
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane, GeomAbs_BSplineSurface, GeomAbs_BezierSurface
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_FACE
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.GProp import GProp_GProps
        from OCP.BRepGProp import BRepGProp
    except ImportError as e:
        logger.debug("OCP not available for v2 features: %s", e)
        return {}

    try:
        shape = read_step(step_path)
    except Exception as e:
        logger.warning("STEP read failed for v2 features: %s", e)
        return {}

    result: dict[str, Any] = {}
    hole_diameters: list[float] = []
    hole_depths: list[float] = []
    hole_lds: list[float] = []
    pocket_depths: list[float] = []
    pocket_aspects: list[float] = []
    hole_proxy_diams: list[float] = []
    hole_proxy_depths: list[float] = []
    hole_proxy_lds: list[float] = []
    pocket_proxy_depths: list[float] = []
    pocket_proxy_aspects: list[float] = []

    # Part bbox for scale
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    dx = float(xmax - xmin)
    dy = float(ymax - ymin)
    dz = float(zmax - zmin)
    part_scale = max(dx, dy, dz) if (dx and dy and dz) else 100.0

    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = exp.Current()
        exp.Next()
        try:
            adapt = BRepAdaptor_Surface(face, True)
            surf_type = adapt.GetType()

            if surf_type == GeomAbs_Cylinder:
                cyl = adapt.Cylinder()
                radius = cyl.Radius()
                dia = 2.0 * radius
                if dia < HOLE_DIAMETER_MIN_MM and part_scale < 50:
                    continue
                hole_diameters.append(round(dia, 2))
                props = GProp_GProps()
                BRepGProp.SurfaceProperties(face, props)
                area = props.Mass()
                if area > 1e-6 and radius > 1e-6:
                    depth = area / (2.0 * 3.14159 * radius)
                    depth = max(0.1, min(depth, part_scale))
                    hole_depths.append(round(depth, 2))
                    if dia > 0.01:
                        hole_lds.append(round(depth / dia, 2))
            elif surf_type == GeomAbs_Plane:
                pln = adapt.Plane()
                loc = pln.Location()
                normal = pln.Axis().Direction()
                # Pocket heuristic: planar face not at part envelope
                # Distance from face center to part center as depth proxy
                cx = (xmin + xmax) / 2
                cy = (ymin + ymax) / 2
                cz = (zmin + zmax) / 2
                fc = loc.X(), loc.Y(), loc.Z()
                dist = (
                    (fc[0] - cx) ** 2 + (fc[1] - cy) ** 2 + (fc[2] - cz) ** 2
                ) ** 0.5
                if dist > part_scale * 0.05:
                    props = GProp_GProps()
                    BRepGProp.SurfaceProperties(face, props)
                    area = props.Mass()
                    if area > 0.1:
                        # Depth proxy: sqrt(area) as opening span
                        span = max(0.5, (area) ** 0.5)
                        depth_proxy = min(dist, part_scale * 0.5)
                        pocket_depths.append(round(depth_proxy, 2))
                        aspect = depth_proxy / span
                        pocket_aspects.append(round(aspect, 2))
            elif surf_type in (GeomAbs_BSplineSurface, GeomAbs_BezierSurface) and not hole_diameters:
                try:
                    from OCP.BRep import BRep_Tool
                    from OCP.GeomLProp import GeomLProp_SLProps
                    surface = BRep_Tool.Surface_s(face)
                    if surface is not None:
                        u1, u2 = adapt.FirstUParameter(), adapt.LastUParameter()
                        v1, v2 = adapt.FirstVParameter(), adapt.LastVParameter()
                        radii: list[float] = []
                        for i in range(2):
                            u = u1 + (u2 - u1) * (i + 1) / 3
                            for j in range(2):
                                v = v1 + (v2 - v1) * (j + 1) / 3
                                props_sl = GeomLProp_SLProps(surface, u, v, 2, 1e-7)
                                if props_sl.IsCurvatureDefined():
                                    gk = props_sl.GaussianCurvature()
                                    mk = props_sl.MeanCurvature()
                                    if abs(gk) < 1e-3 and mk is not None and abs(mk) > 1e-6:
                                        r = 1.0 / abs(mk)
                                        if 0.1 < r < 1000:
                                            radii.append(r)
                        if radii:
                            radius = sum(radii) / len(radii)
                            dia = round(radius * 2, 2)
                            if dia >= HOLE_DIAMETER_MIN_MM or part_scale >= 50:
                                hole_proxy_diams.append(dia)
                                props = GProp_GProps()
                                BRepGProp.SurfaceProperties(face, props)
                                area = props.Mass()
                                if area > 1e-6 and radius > 0.01:
                                    depth = area / (2.0 * 3.14159 * radius)
                                    depth = max(0.1, min(depth, part_scale))
                                    hole_proxy_depths.append(round(depth, 2))
                                    hole_proxy_lds.append(round(depth / dia, 2))
                except Exception:
                    pass
        except Exception:
            continue

    # Fallback pocket proxy: planar faces not on outer bbox planes, normal aligned with X/Y/Z
    if not pocket_depths:
        exp2 = TopExp_Explorer(shape, TopAbs_FACE)
        bbox_eps = max(0.5, part_scale * 0.01)
        axis_dirs = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
        cos_tol = math.cos(math.radians(NORMAL_ALIGN_TOL_DEG))
        while exp2.More():
            face = exp2.Current()
            exp2.Next()
            try:
                adapt = BRepAdaptor_Surface(face, True)
                if adapt.GetType() == GeomAbs_Plane:
                    pln = adapt.Plane()
                    loc = pln.Location()
                    n = pln.Axis().Direction()
                    cx, cy, cz = loc.X(), loc.Y(), loc.Z()
                    on_outer = (
                        abs(cx - xmin) < bbox_eps or abs(cx - xmax) < bbox_eps or
                        abs(cy - ymin) < bbox_eps or abs(cy - ymax) < bbox_eps or
                        abs(cz - zmin) < bbox_eps or abs(cz - zmax) < bbox_eps
                    )
                    if on_outer:
                        continue
                    aligned = any(
                        abs(n.X() * ax + n.Y() * ay + n.Z() * az) >= cos_tol
                        for ax, ay, az in axis_dirs
                    )
                    if aligned:
                        props = GProp_GProps()
                        BRepGProp.SurfaceProperties(face, props)
                        area = props.Mass()
                        if area > 0.1:
                            dist = ((cx - (xmin + xmax) / 2) ** 2 + (cy - (ymin + ymax) / 2) ** 2 + (cz - (zmin + zmax) / 2) ** 2) ** 0.5
                            depth_proxy = min(dist, part_scale * 0.5)
                            span = max(0.5, (area) ** 0.5)
                            pocket_proxy_depths.append(round(depth_proxy, 2))
                            pocket_proxy_aspects.append(round(depth_proxy / span, 2))
            except Exception:
                continue

    # Always set analytic keys (0/[]/None when empty)
    result["hole_count"] = len(hole_diameters)
    result["hole_diameters_mm"] = sorted(set(round(d, 2) for d in hole_diameters)) if hole_diameters else []
    result["hole_max_depth_mm"] = round(max(hole_depths), 2) if hole_depths else None
    result["hole_max_ld"] = round(max(hole_lds), 2) if hole_lds else None
    result["pocket_count"] = len(pocket_depths)
    result["pocket_max_depth_mm"] = round(max(pocket_depths), 2) if pocket_depths else None
    result["pocket_max_aspect"] = round(max(pocket_aspects), 2) if pocket_aspects else None

    # Fallback proxy keys (only when analytic count is 0; do not mix)
    if not hole_diameters and hole_proxy_diams:
        result["hole_proxy_count"] = len(hole_proxy_diams)
        result["hole_proxy_diameters_mm"] = sorted(set(round(d, 2) for d in hole_proxy_diams))
        result["hole_proxy_max_depth_mm"] = round(max(hole_proxy_depths), 2) if hole_proxy_depths else None
        result["hole_proxy_max_ld"] = round(max(hole_proxy_lds), 2) if hole_proxy_lds else None
    if not pocket_depths and pocket_proxy_depths:
        result["pocket_proxy_count"] = len(pocket_proxy_depths)
        result["pocket_proxy_max_depth_mm"] = round(max(pocket_proxy_depths), 2)
        result["pocket_proxy_max_aspect"] = round(max(pocket_proxy_aspects), 2) if pocket_proxy_aspects else None

    return result
