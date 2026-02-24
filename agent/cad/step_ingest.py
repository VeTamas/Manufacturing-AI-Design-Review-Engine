"""
STEP file ingestion using OCP (OpenCASCADE Python bindings). Deterministic geometry utilities.
Units assumed mm. Do not use pythonocc-core; use OCP only (e.g. cadquery-ocp).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def read_step(path: str | Path) -> Any:
    """
    Load a STEP file using OCP.STEPControl.STEPControl_Reader.
    Returns reader.OneShape(). Raises ValueError if read status != IFSelect_RetDone.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"STEP file not found: {path}")
    if path.suffix.lower() not in (".step", ".stp"):
        raise ValueError(f"Expected .step or .stp, got: {path.suffix}")

    from OCP.STEPControl import STEPControl_Reader
    from OCP.IFSelect import IFSelect_RetDone

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(path))
    if status != IFSelect_RetDone:
        raise ValueError(f"STEP read failed: status={status}")
    reader.TransferRoots()
    shape = reader.OneShape()
    if shape.IsNull():
        raise ValueError("STEP file produced no geometry")
    return shape


def compute_bbox(shape: Any) -> tuple[float, float, float]:
    """
    Compute bounding box dimensions (dx, dy, dz) in mm using OCP.Bnd.Bnd_Box and
    OCP.BRepBndLib.BRepBndLib.AddOptimal_s.
    Returns (dx, dy, dz) = (xmax-xmin, ymax-ymin, zmax-zmin).
    """
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box)
    xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
    return (float(xmax - xmin), float(ymax - ymin), float(zmax - zmin))


def get_bbox_only(path: str | Path) -> dict[str, tuple[float, float, float]] | None:
    """
    Cheap bbox-only read. Returns {"bbox_dims": (dx, dy, dz)} or None on failure.
    Used as fallback when cad_lite fails.
    """
    try:
        shape = read_step(path)
        dx, dy, dz = compute_bbox(shape)
        return {"bbox_dims": (float(dx), float(dy), float(dz))}
    except Exception:
        return None


def count_topology(shape: Any) -> dict[str, int]:
    """
    Count faces, edges, solids using OCP.TopExp.TopExp_Explorer with
    TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID.
    Returns {"faces": int, "edges": int, "solids": int}.
    """
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID

    def _count(kind: Any) -> int:
        exp = TopExp_Explorer(shape, kind)
        n = 0
        while exp.More():
            n += 1
            exp.Next()
        return n

    return {
        "faces": _count(TopAbs_FACE),
        "edges": _count(TopAbs_EDGE),
        "solids": _count(TopAbs_SOLID),
    }


def extract_cad_metrics(path: str | Path) -> dict[str, Any]:
    """
    Load STEP, compute bbox and topology counts. Returns a single dict with
    bbox dimensions (dx_mm, dy_mm, dz_mm) and face/edge/solid counts.
    """
    shape = read_step(path)
    dx, dy, dz = compute_bbox(shape)
    counts = count_topology(shape)
    return {
        "dx_mm": dx,
        "dy_mm": dy,
        "dz_mm": dz,
        "faces": counts["faces"],
        "edges": counts["edges"],
        "solids": counts["solids"],
    }


def ingest_step_to_bins(path: str | Path) -> dict[str, Any]:
    """
    Load STEP, compute geometry metrics, and return PartSummary-compatible bins
    (only part_size, feature_variety, accessibility_risk, has_clamping_faces).
    Returns dict: success (bool), message (str), bins_preview (dict | None).
    On failure: success=False, message=error, bins_preview=None.
    """
    from agent.cad.binning import cad_bins_from_metrics

    out: dict[str, Any] = {"success": False, "message": "", "bins_preview": None}

    try:
        metrics = extract_cad_metrics(path)
        bins = cad_bins_from_metrics(metrics)
        # Compute turning L/D ratio proxy
        dx, dy, dz = metrics["dx_mm"], metrics["dy_mm"], metrics["dz_mm"]
        L = max(dx, dy, dz)
        dims_sorted = sorted([dx, dy, dz])
        D = dims_sorted[1] if len(dims_sorted) > 1 else dims_sorted[0]
        turning_ld_ratio = round(L / D, 2) if D and D > 0 else None

        out["success"] = True
        out["message"] = "CAD ingestion succeeded."
        out["bins_preview"] = {
            **bins,
            "bbox_mm": (dx, dy, dz),
            "turning_ld_ratio": turning_ld_ratio,
        }
        return out
    except FileNotFoundError as e:
        out["message"] = str(e)
        return out
    except ValueError as e:
        out["message"] = str(e)
        logger.warning("CAD ingest failed: %s", e)
        return out
    except Exception as e:
        out["message"] = f"CAD parsing failed: {e}"
        logger.exception("CAD ingest failed for %s", path)
        return out
