"""Build geometry evidence block for LLM prompts (explain, refine, self_review)."""
from __future__ import annotations

from agent.state import GraphState


def build_geometry_evidence_block(state: GraphState) -> str:
    """Build a text block of geometry/metrics for LLM prompts.

    Includes: flatness, thinness, t_over_min_dim, extrusion/turning likelihood,
    accessibility_risk, feature_variety, forced_primary, raw_best, score_diff.
    Base rationale ONLY on these metrics; do not invent geometry.
    """
    lines: list[str] = []
    proc_rec = state.get("process_recommendation") or {}
    scores = proc_rec.get("scores") or {}
    primary = proc_rec.get("primary")
    secondary = proc_rec.get("secondary") or []
    second_process = None
    if primary and len(scores) >= 2:
        sorted_procs = sorted(
            (p for p in scores if scores.get(p, 0) > 0),
            key=lambda p: scores.get(p, 0),
            reverse=True,
        )
        second_process = next((p for p in sorted_procs if p != primary), None)
    primary_score = scores.get(primary, 0) if primary else 0
    second_score = scores.get(second_process, 0) if second_process else 0
    score_diff = primary_score - second_score

    # CAD Lite
    cad_lite = proc_rec.get("cad_lite") or state.get("cad_lite")
    if isinstance(cad_lite, dict) and cad_lite.get("status") == "ok":
        t_over = cad_lite.get("t_over_min_dim")
        if t_over is not None:
            lines.append(f"  - t_over_min_dim: {round(float(t_over), 4)}")
        bbox = cad_lite.get("bbox_dims")
        if isinstance(bbox, (list, tuple)) and len(bbox) >= 3:
            a, b, c = float(bbox[0]), float(bbox[1]), float(bbox[2])
            if a >= b >= c and b > 1e-6 and a > 1e-6:
                flatness = c / b
                thinness = c / a
                lines.append(f"  - flatness (c/b): {round(flatness, 3)}")
                lines.append(f"  - thinness (c/a): {round(thinness, 3)}")
        if cad_lite.get("av_ratio") is not None:
            lines.append(f"  - av_ratio: {round(float(cad_lite['av_ratio']), 4)}")

    # Extrusion likelihood
    ext_lh = proc_rec.get("extrusion_likelihood") or state.get("extrusion_likelihood")
    if isinstance(ext_lh, dict):
        level = ext_lh.get("level") or ext_lh.get("likelihood")
        coeff_var = ext_lh.get("coeff_var")
        parts = [f"  - extrusion_likelihood: {level}"]
        if coeff_var is not None:
            parts.append(f" coeff_var={round(float(coeff_var), 4)}")
        lines.append("".join(parts))

    # Turning likelihood
    turn_lh = proc_rec.get("turning_likelihood") or state.get("turning_likelihood")
    if isinstance(turn_lh, dict):
        level = turn_lh.get("level") or turn_lh.get("likelihood")
        lines.append(f"  - turning_likelihood: {level}")

    # Part summary
    part = state.get("part_summary")
    if part:
        acc = getattr(part, "accessibility_risk", None)
        if acc:
            lines.append(f"  - accessibility_risk: {acc}")
        var = getattr(part, "feature_variety", None)
        if var:
            lines.append(f"  - feature_variety: {var}")

    # Process decision
    forced_primary = bool(proc_rec.get("forced_primary"))
    raw_best = proc_rec.get("raw_best") or primary
    lines.append(f"  - forced_primary: {forced_primary}")
    lines.append(f"  - raw_best_process: {raw_best}")
    lines.append(f"  - score_diff (primary - second): {score_diff}")

    if not lines:
        return "(no geometry metrics available)"
    return "Geometry/metrics (use only these; do not invent):\n" + "\n".join(lines)


def build_cad_lite_evidence_from_rec(proc_rec: dict) -> dict | None:
    """Build evidence dict from process_recommendation (cad_lite, extrusion/turning) for bins path."""
    cad_lite = proc_rec.get("cad_lite")
    if not isinstance(cad_lite, dict) or cad_lite.get("status") != "ok":
        return None
    out = {"source": "cad_lite", "t_over_min_dim": cad_lite.get("t_over_min_dim")}
    bbox = cad_lite.get("bbox_dims")
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 3:
        a, b, c = float(bbox[0]), float(bbox[1]), float(bbox[2])
        if a >= b >= c and b > 1e-6 and a > 1e-6:
            out["flatness"] = round(c / b, 4)
            out["thinness"] = round(c / a, 4)
    ext_lh = proc_rec.get("extrusion_likelihood")
    if isinstance(ext_lh, dict):
        out["extrusion_likelihood_level"] = ext_lh.get("level") or ext_lh.get("likelihood")
        if ext_lh.get("coeff_var") is not None:
            out["extrusion_coeff_var"] = ext_lh.get("coeff_var")
    turn_lh = proc_rec.get("turning_likelihood")
    if isinstance(turn_lh, dict):
        out["turning_likelihood_level"] = turn_lh.get("level") or turn_lh.get("likelihood")
    return out


def build_cad_lite_evidence_dict(state: GraphState) -> dict | None:
    """Build evidence dict from cad_lite + process_recommendation for bins path."""
    proc_rec = state.get("process_recommendation") or {}
    return build_cad_lite_evidence_from_rec(proc_rec)
