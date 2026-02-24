"""Process selection: deterministic primary/secondary recommendation.

Portfolio release: only simplified scoring (agent.scoring.portfolio_scoring) is used.
Production heuristics are not included in this repository.
"""
from __future__ import annotations

from agent.processes.gating import hard_gates
from agent.state import GraphState
from agent.scoring.portfolio_scoring import CANDIDATES, compute_portfolio_recommendation

# Re-export for consumers (report, rules)
__all__ = ["CANDIDATES", "process_selection_node", "_resolve_am_tech", "_normalize_primary_secondary"]


def _normalize_primary_secondary(primary: str | None, secondary: list[str] | None) -> list[str]:
    """Normalize secondary list: remove duplicates and primary."""
    if not secondary:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for s in secondary:
        if not s or (primary and s == primary) or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _resolve_am_tech(state: GraphState, user_selected_am_tech: str | None = None) -> tuple[str, str]:
    """
    Resolve AM technology for RAG/rules. Portfolio: material-based default only.
    Returns (am_tech, resolution_source).
    """
    if user_selected_am_tech and user_selected_am_tech != "AUTO":
        return user_selected_am_tech, "explicit"
    inp = state.get("inputs")
    material = (getattr(inp, "material", "") or "").lower() if inp else ""
    if material in ("steel", "aluminum", "stainless steel", "titanium"):
        return "METAL_LPBF", "material"
    return "FDM", "default"


def process_selection_node(state: GraphState) -> dict:
    """Compute process recommendation using portfolio baseline scoring only."""
    trace = ["Process selection node entered"]
    inp = state.get("inputs")
    part = state.get("part_summary")

    if not inp or not part:
        trace.append("Process selection skipped: missing inputs or part_summary")
        return {
            "process_recommendation": {
                "primary": None,
                "secondary": [],
                "not_recommended": [],
                "reasons": ["Missing inputs/part summary for process selection."],
                "tradeoffs": [],
                "scores": {},
            },
            "trace": trace,
            "findings": list(state.get("findings", [])),
        }

    material = getattr(inp, "material", "") or ""
    production_volume = getattr(inp, "production_volume", "") or ""
    user_text = (
        (getattr(inp, "user_text", None) or getattr(inp, "text", None) or getattr(inp, "notes", None) or "")
        or state.get("user_text") or state.get("text") or state.get("description") or ""
    ).strip().lower()

    gates = hard_gates(CANDIDATES, material)
    eligible_processes = [p for p in CANDIDATES if gates.get(p, {}).get("eligible", True)]
    if not eligible_processes:
        eligible_processes = ["CNC"]
        trace.append("fallback_primary_due_to_empty_eligible")

    part_size = getattr(part, "part_size", "") or ""
    min_wall_thickness = getattr(part, "min_wall_thickness", "") or ""
    feature_variety = getattr(part, "feature_variety", "") or ""
    tolerance_criticality = getattr(inp, "tolerance_criticality", "") or ""
    user_process_raw = getattr(inp, "process", "") or "AUTO"

    trace.append(f"process_selection: eligible_processes={sorted(eligible_processes)}")
    trace.append(f'PSI: user_text_len={len(user_text)} preview="{user_text[:60]}"')

    rec = compute_portfolio_recommendation(
        material=material,
        production_volume=production_volume,
        part_size=part_size,
        feature_variety=feature_variety,
        min_wall_thickness=min_wall_thickness,
        tolerance_criticality=tolerance_criticality,
        user_process_raw=user_process_raw,
        eligible_processes=eligible_processes,
        gates=gates,
        user_text=user_text,
    )
    trace.append(f"Process selection (portfolio baseline scoring): primary={rec['primary']} secondary={rec.get('secondary', [])}")

    return {
        "process_recommendation": rec,
        "trace": trace,
        "findings": list(state.get("findings", [])),
    }
