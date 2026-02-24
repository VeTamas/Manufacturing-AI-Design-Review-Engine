from __future__ import annotations

from dataclasses import asdict
from typing import Any


def _to_dict(obj: Any) -> dict:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return dict(obj.__dict__)
    try:
        return asdict(obj)  # type: ignore
    except Exception:
        return {"value": str(obj)}


def build_fallback_report(state: dict) -> str:
    inputs = _to_dict(state.get("inputs"))
    part = _to_dict(state.get("part_summary"))
    pr = _to_dict(state.get("process_recommendation") or state.get("process_selection") or {})
    conf = _to_dict(state.get("confidence") or {})
    cad_lite = _to_dict(pr.get("cad_lite") or state.get("cad_lite") or {})
    sm_like = _to_dict(pr.get("sheet_metal_likelihood") or state.get("sheet_metal_likelihood") or {})
    ex_like = _to_dict(pr.get("extrusion_likelihood") or state.get("extrusion_likelihood") or {})

    findings = state.get("findings") or []
    f_out = []
    for f in findings:
        if isinstance(f, dict):
            f_out.append(f)
        else:
            f_out.append(
                {
                    "id": getattr(f, "id", None),
                    "severity": getattr(f, "severity", None),
                    "title": getattr(f, "title", None),
                    "why_it_matters": getattr(f, "why_it_matters", None),
                    "recommendation": getattr(f, "recommendation", None),
                }
            )

    primary = pr.get("primary")
    secondary = pr.get("secondary") or []
    not_rec = pr.get("not_recommended") or []
    tradeoffs = pr.get("tradeoffs") or []

    lines: list[str] = []
    lines.append("# CNC Design Review + DFM Report (Offline mode)")
    lines.append("")
    lines.append("## Input summary")
    lines.append("")
    process = inputs.get('process', '')
    if process == "AUTO" and primary:
        lines.append(f"- Manufacturing process: AUTO")
        lines.append(f"- Recommended process: {primary}")
    else:
        lines.append(f"- Manufacturing process: {process}")
    lines.append(f"- Material: {inputs.get('material')}")
    lines.append(f"- Production volume: {inputs.get('production_volume')}")
    lines.append(f"- Load type: {inputs.get('load_type')}")
    lines.append(f"- Tolerance criticality: {inputs.get('tolerance_criticality')}")
    lines.append("")

    if part:
        lines.append("## Part summary (bins)")
        lines.append("")
        for k in [
            "part_size",
            "min_internal_radius",
            "min_wall_thickness",
            "hole_depth_class",
            "pocket_aspect_class",
            "feature_variety",
            "accessibility_risk",
            "has_clamping_faces",
        ]:
            if k in part:
                lines.append(f"- {k}: {part.get(k)}")
        lines.append("")

    lines.append("## Process recommendation")
    lines.append("")
    lines.append(f"- Primary: **{primary}**")
    lines.append(f"- Secondary: {', '.join(secondary) if secondary else 'None'}")
    if not_rec:
        lines.append(f"- Less suitable (given current inputs): {', '.join(not_rec)}")
    lines.append("")

    if tradeoffs:
        lines.append("### Tradeoffs")
        lines.append("")
        for t in tradeoffs:
            lines.append(f"- {t}")
        lines.append("")

    lines.append("## Manufacturing confidence inputs")
    lines.append("")
    if cad_lite:
        lines.append(f"- CAD Lite analysis: {cad_lite.get('status', 'n/a')}")
        if cad_lite.get("bbox_dims"):
            lines.append(f"- bbox_dims: {cad_lite.get('bbox_dims')}")
        if cad_lite.get("t_est") is not None:
            lines.append(f"- t_est: {cad_lite.get('t_est')}")
    if ex_like:
        lines.append(f"- Extrusion likelihood: {ex_like.get('level', 'n/a')} (source={ex_like.get('source', 'n/a')})")
    if sm_like:
        lines.append(f"- Sheet metal likelihood: {sm_like.get('level', 'n/a')} (source={sm_like.get('source', 'n/a')})")
    lines.append("")

    sev_order = ["HIGH", "MEDIUM", "LOW"]
    for sev in sev_order:
        group = [x for x in f_out if (x.get("severity") or "").upper() == sev]
        if not group:
            continue
        lines.append(f"## Findings ({sev})")
        lines.append("")
        for x in group:
            title = x.get("title") or ""
            rid = x.get("id") or x.get("rule_id") or ""
            why = x.get("why_it_matters") or ""
            rec = x.get("recommendation") or ""
            lines.append(f"- **{title}** ({rid})")
            if why:
                lines.append(f"  - Why it matters: {why}")
            if rec:
                lines.append(f"  - Recommendation: {rec}")
        lines.append("")

    lines.append("## Action checklist")
    lines.append("")
    if f_out:
        for x in f_out:
            title = x.get("title") or ""
            rec = x.get("recommendation") or ""
            if title and rec:
                lines.append(f"- [ ] {title}: {rec}")
            elif title:
                lines.append(f"- [ ] {title}")
    else:
        lines.append("- [ ] No findings. Validate with a prototype / supplier quote.")
    lines.append("")

    if conf:
        score = conf.get("score")
        if isinstance(score, (int, float)):
            lines.append("## Agent confidence")
            lines.append("")
            lines.append(f"- Score: {float(score):.2f}")
            lines.append("")

    lines.append("## Notes")
    lines.append("")
    lines.append("- This report was generated without an online LLM (offline deterministic fallback).")
    lines.append("- For best results, provide a 2D drawing (GD&T) and confirm STEP scale.")
    lines.append("")
    return "\n".join(lines)
