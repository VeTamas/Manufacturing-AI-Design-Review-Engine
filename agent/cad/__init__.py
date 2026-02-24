"""
CAD ingestion (MVP): STEP parsing via OCP and deterministic bin derivation (no LLM).
Requires cadquery-ocp (pip install cadquery-ocp). Do not use pythonocc-core.
"""

from agent.cad.step_ingest import (
    read_step,
    compute_bbox,
    count_topology,
    extract_cad_metrics,
    ingest_step_to_bins,
)
from agent.cad.binning import (
    bin_part_size,
    bin_feature_variety,
    bin_accessibility_risk,
    infer_has_clamping_faces,
    cad_bins_from_metrics,
)

__all__ = [
    "read_step",
    "compute_bbox",
    "count_topology",
    "extract_cad_metrics",
    "ingest_step_to_bins",
    "bin_part_size",
    "bin_feature_variety",
    "bin_accessibility_risk",
    "infer_has_clamping_faces",
    "cad_bins_from_metrics",
]
