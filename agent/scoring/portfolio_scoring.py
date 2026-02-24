"""Portfolio baseline scoring: table-driven, coverage-first.

Uses only material_family, volume, tolerance_criticality, feature_variety,
and optionally part_size / wall_thickness. Production heuristics are not included.
"""
from __future__ import annotations

from agent.processes.gating import material_family

CANDIDATES = (
    "CNC",
    "CNC_TURNING",
    "AM",
    "SHEET_METAL",
    "INJECTION_MOLDING",
    "CASTING",
    "FORGING",
    "EXTRUSION",
    "MIM",
    "THERMOFORMING",
    "COMPRESSION_MOLDING",
)

SECONDARY_DELTA = 2  # Max score gap for secondary (deterministic tie-break)

# ---------------------------------------------------------------------------
# Table-driven bonuses (0–3 per category). Transparent, coverage-first baseline.
# ---------------------------------------------------------------------------
# Material "unknown": neutral small values so coverage stays stable without biasing toward metal.
PROCESS_RULES: dict[str, dict[str, dict[str, int]]] = {
    "CNC": {
        "material": {"metal": 3, "polymer": 1, "unknown": 1},
        "volume": {"proto": 2, "small_batch": 1, "production": 0},
        "tolerance": {"low": 0, "medium": 1, "high": 2},
        "feature_variety": {"low": 1, "medium": 1, "high": 0},
    },
    "CNC_TURNING": {
        "material": {"metal": 2, "polymer": 0, "unknown": 1},
        "volume": {"proto": 2, "small_batch": 1, "production": 0},
        "tolerance": {"low": 0, "medium": 1, "high": 2},
        "feature_variety": {"low": 2, "medium": 1, "high": 0},
    },
    "AM": {
        "material": {"metal": 1, "polymer": 2, "unknown": 1},
        "volume": {"proto": 3, "small_batch": 2, "production": 0},
        "tolerance": {"low": 1, "medium": 0, "high": 0},
        "feature_variety": {"low": 0, "medium": 1, "high": 2},
    },
    "SHEET_METAL": {
        "material": {"metal": 2, "polymer": 0, "unknown": 0},
        # proto=1 so sheet metal can appear plausibly in proto scenarios (minimal balance vs CNC/AM).
        "volume": {"proto": 1, "small_batch": 1, "production": 2},
        "tolerance": {"low": 2, "medium": 1, "high": 0},
        "feature_variety": {"low": 2, "medium": 1, "high": 0},
    },
    "INJECTION_MOLDING": {
        "material": {"metal": 0, "polymer": 3, "unknown": 1},
        "volume": {"proto": 0, "small_batch": 0, "production": 3},
        "tolerance": {"low": 1, "medium": 1, "high": 0},
        "feature_variety": {"low": 2, "medium": 1, "high": 0},
    },
    "CASTING": {
        "material": {"metal": 2, "polymer": 0, "unknown": 1},
        "volume": {"proto": 0, "small_batch": 1, "production": 2},
        "tolerance": {"low": 1, "medium": 1, "high": 0},
        "feature_variety": {"low": 1, "medium": 1, "high": 0},
    },
    "FORGING": {
        "material": {"metal": 2, "polymer": 0, "unknown": 1},
        "volume": {"proto": 0, "small_batch": 0, "production": 2},
        "tolerance": {"low": 1, "medium": 1, "high": 0},
        "feature_variety": {"low": 2, "medium": 1, "high": 0},
    },
    "EXTRUSION": {
        "material": {"metal": 2, "polymer": 1, "unknown": 1},
        "volume": {"proto": 0, "small_batch": 1, "production": 2},
        "tolerance": {"low": 1, "medium": 1, "high": 0},
        "feature_variety": {"low": 2, "medium": 1, "high": 0},
    },
    "MIM": {
        "material": {"metal": 2, "polymer": 0, "unknown": 1},
        "volume": {"proto": 0, "small_batch": 0, "production": 2},
        "tolerance": {"low": 1, "medium": 1, "high": 0},
        "feature_variety": {"low": 0, "medium": 1, "high": 2},
    },
    "THERMOFORMING": {
        "material": {"metal": 0, "polymer": 2, "unknown": 1},
        "volume": {"proto": 0, "small_batch": 0, "production": 2},
        "tolerance": {"low": 1, "medium": 1, "high": 0},
        "feature_variety": {"low": 2, "medium": 1, "high": 0},
    },
    "COMPRESSION_MOLDING": {
        "material": {"metal": 0, "polymer": 2, "unknown": 1},
        "volume": {"proto": 0, "small_batch": 0, "production": 2},
        "tolerance": {"low": 1, "medium": 1, "high": 0},
        "feature_variety": {"low": 2, "medium": 1, "high": 0},
    },
}


def _norm_volume(production_volume: str) -> str:
    """Map to proto | small_batch | production."""
    v = (production_volume or "").strip().lower()
    if v in ("proto",):
        return "proto"
    if v in ("small batch", "small_batch"):
        return "small_batch"
    if v in ("production",):
        return "production"
    return "small_batch"


def _norm_tolerance(tolerance_criticality: str) -> str:
    """Map to low | medium | high."""
    t = (tolerance_criticality or "").strip().lower()
    if t in ("low",):
        return "low"
    if t in ("high",):
        return "high"
    return "medium"


def _norm_feature_variety(feature_variety: str) -> str:
    """Map to low | medium | high."""
    fv = (feature_variety or "").strip().lower()
    if fv in ("low",):
        return "low"
    if fv in ("high",):
        return "high"
    return "medium"


def _norm_size(part_size: str) -> str:
    """Map to small | medium | large."""
    s = (part_size or "").strip().lower()
    if s in ("small",):
        return "small"
    if s in ("large",):
        return "large"
    return "medium"


def _norm_wall(min_wall_thickness: str) -> str:
    """Map to thin | medium | thick."""
    w = (min_wall_thickness or "").strip().lower()
    if w in ("thin",):
        return "thin"
    if w in ("thick",):
        return "thick"
    return "medium"


def _score_from_table(
    process: str,
    mat_family: str,
    volume: str,
    tolerance: str,
    feature_variety: str,
) -> tuple[int, list[dict]]:
    """Sum table bonuses for one process. Returns (score, breakdown_entries)."""
    rules = PROCESS_RULES.get(process)
    if not rules:
        return 0, []

    entries: list[dict] = []
    total = 0

    mat_r = rules.get("material") or {}
    delta = mat_r.get(mat_family, mat_r.get("unknown", 0))
    if delta:
        total += delta
        entries.append({"delta": delta, "reason": f"Material family ({mat_family})", "rule_id": "PORT_MAT", "severity": "info"})

    vol_r = rules.get("volume") or {}
    delta = vol_r.get(volume, 0)
    if delta:
        total += delta
        entries.append({"delta": delta, "reason": f"Volume ({volume})", "rule_id": "PORT_VOL", "severity": "info"})

    tol_r = rules.get("tolerance") or {}
    delta = tol_r.get(tolerance, 0)
    if delta:
        total += delta
        entries.append({"delta": delta, "reason": f"Tolerance ({tolerance})", "rule_id": "PORT_TOL", "severity": "info"})

    fv_r = rules.get("feature_variety") or {}
    delta = fv_r.get(feature_variety, 0)
    if delta:
        total += delta
        entries.append({"delta": delta, "reason": f"Feature variety ({feature_variety})", "rule_id": "PORT_FV", "severity": "info"})

    return total, entries


def _plausibility_bonuses(
    process: str,
    mat_family: str,
    volume: str,
    tolerance: str,
    feature_variety: str,
    size_class: str,
    eligible_processes: list[str],
) -> tuple[int, str | None]:
    """
    Minimal plausibility rules: small +1 or +2 only.
    Returns (delta, reason_or_none).
    """
    if process not in eligible_processes:
        return 0, None

    # Sheet metal: metal + low/med tolerance + low/med feature variety (+ optional medium/large size)
    if process == "SHEET_METAL" and mat_family == "metal":
        if tolerance in ("low", "medium") and feature_variety in ("low", "medium"):
            if size_class in ("medium", "large"):
                return 2, "Metal, moderate tolerance and variety, medium/large size favor sheet metal"
            return 1, "Metal, moderate tolerance and variety favor sheet metal"

    # Extrusion: metal + low feature variety (+ optional medium/large size)
    if process == "EXTRUSION" and mat_family == "metal":
        if feature_variety == "low":
            if size_class in ("medium", "large"):
                return 2, "Metal, low feature variety, medium/large size favor extrusion"
            return 1, "Metal, low feature variety favor extrusion"

    # Injection molding / thermoforming / compression: polymer + production (+ optional size)
    if process in ("INJECTION_MOLDING", "THERMOFORMING", "COMPRESSION_MOLDING") and mat_family == "polymer":
        if volume == "production":
            if size_class in ("medium", "large"):
                return 2, "Polymer, production volume, medium/large size favor forming/molding"
            return 1, "Polymer, production volume favor forming/molding"

    return 0, None


def _portfolio_scores(
    material: str,
    production_volume: str,
    part_size: str,
    feature_variety: str,
    tolerance_criticality: str,
    min_wall_thickness: str,
    user_process_raw: str,
    eligible_processes: list[str],
    user_text: str = "",
) -> tuple[dict[str, int], dict[str, list[dict]], list[str]]:
    """
    Table-driven score + minimal plausibility. Returns (scores, score_breakdown, all_reasons).
    """
    mat_family = material_family(material)
    # Keep "unknown" as-is; PROCESS_RULES has neutral "unknown" entries so we do not bias toward metal.
    volume = _norm_volume(production_volume)
    tolerance = _norm_tolerance(tolerance_criticality)
    fv = _norm_feature_variety(feature_variety)
    size_class = _norm_size(part_size)
    wall_class = _norm_wall(min_wall_thickness)

    scores: dict[str, int] = {p: 0 for p in CANDIDATES}
    score_breakdown: dict[str, list[dict]] = {p: [] for p in CANDIDATES}
    reasons: list[str] = []

    for process in eligible_processes:
        base, entries = _score_from_table(process, mat_family, volume, tolerance, fv)
        scores[process] = base
        score_breakdown[process] = list(entries)
        for e in entries:
            if e.get("reason"):
                reasons.append(e["reason"])

        delta, reason = _plausibility_bonuses(
            process, mat_family, volume, tolerance, fv, size_class, eligible_processes
        )
        if delta and reason:
            scores[process] = scores.get(process, 0) + delta
            score_breakdown[process].append({"delta": delta, "reason": reason, "rule_id": "PORT_PLAUS", "severity": "info"})
            reasons.append(reason)

    # User selection bias (when not AUTO)
    user_process = None if user_process_raw == "AUTO" else user_process_raw
    if user_process and user_process in eligible_processes:
        scores[user_process] = scores.get(user_process, 0) + 1
        score_breakdown[user_process].append({"delta": 1, "reason": "User-selected process bias", "rule_id": "PORT_USER", "severity": "info"})
        reasons.append("User-selected process bias")

    # Optional: one simple keyword nudge for demo plausibility (keep minimal)
    text = (user_text or "").lower()
    if "extrusion" in text or "profile" in text:
        if "EXTRUSION" in eligible_processes:
            scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + 1
            score_breakdown["EXTRUSION"].append({"delta": 1, "reason": "Description suggests extrusion", "rule_id": "PORT_KW", "severity": "info"})
    if "sheet metal" in text or "bend" in text:
        if "SHEET_METAL" in eligible_processes:
            scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) + 1
            score_breakdown["SHEET_METAL"].append({"delta": 1, "reason": "Description suggests sheet metal", "rule_id": "PORT_KW", "severity": "info"})
    if "additive" in text or "3d print" in text:
        if "AM" in eligible_processes:
            scores["AM"] = scores.get("AM", 0) + 1
            score_breakdown["AM"].append({"delta": 1, "reason": "Description suggests additive", "rule_id": "PORT_KW", "severity": "info"})

    for p in CANDIDATES:
        if p not in eligible_processes:
            scores[p] = 0

    return scores, score_breakdown, reasons


def _portfolio_tiebreak(
    scores: dict[str, int],
    eligible_processes: list[str],
    user_process_raw: str,
) -> tuple[str, list[str], list[str]]:
    """Deterministic: primary = max score; secondary = next within SECONDARY_DELTA."""
    user_process = None if user_process_raw == "AUTO" else user_process_raw
    sorted_by_score = sorted(
        eligible_processes,
        key=lambda p: (scores.get(p, 0), 1 if user_process and p == user_process else 0),
        reverse=True,
    )
    primary = sorted_by_score[0] if sorted_by_score else "CNC"
    primary_score = scores.get(primary, 0)

    secondary: list[str] = []
    for p in sorted_by_score[1:]:
        if p == primary:
            continue
        if primary_score - scores.get(p, 0) <= SECONDARY_DELTA and scores.get(p, 0) > 0:
            secondary.append(p)
        if len(secondary) >= 2:
            break

    not_recommended: list[str] = []
    excluded = {primary} | set(secondary)
    for p in eligible_processes:
        if p in excluded or (user_process and p == user_process):
            continue
        sp = scores.get(p, 0)
        if sp <= 0 or (primary_score - sp) >= 4:
            not_recommended.append(p)

    return primary, secondary, not_recommended


def compute_portfolio_recommendation(
    material: str,
    production_volume: str,
    part_size: str,
    feature_variety: str,
    min_wall_thickness: str,
    tolerance_criticality: str,
    user_process_raw: str,
    eligible_processes: list[str],
    gates: dict,
    user_text: str = "",
) -> dict:
    """
    Portfolio baseline scoring. Same output shape as process_recommendation for drop-in use.
    """
    scores, score_breakdown, all_reasons = _portfolio_scores(
        material=material,
        production_volume=production_volume,
        part_size=part_size,
        feature_variety=feature_variety,
        tolerance_criticality=tolerance_criticality,
        min_wall_thickness=min_wall_thickness,
        user_process_raw=user_process_raw,
        eligible_processes=eligible_processes,
        user_text=user_text,
    )
    primary, secondary, not_recommended = _portfolio_tiebreak(
        scores=scores,
        eligible_processes=eligible_processes,
        user_process_raw=user_process_raw,
    )

    reasons_primary = [e["reason"] for e in score_breakdown.get(primary, []) if e.get("reason")]
    reasons_secondary_list: list[str] = []
    for sec_proc in secondary[:2]:
        reasons_secondary_list.extend(e["reason"] for e in score_breakdown.get(sec_proc, []) if e.get("reason"))
    reasons_secondary_list = list(dict.fromkeys(reasons_secondary_list))[:4]

    reasons = list(dict.fromkeys(all_reasons))[:6]
    if secondary and not reasons:
        reasons.append(f"Close alternatives: {', '.join(secondary)}")

    tradeoffs = [
        "Tooling lead time vs unit cost: IM/Sheet metal need tooling; CNC/AM suit low volume.",
        "Tolerance and finish: Define critical interfaces; plan post-machining or inspection where needed.",
        "Volume sensitivity: IM and sheet metal favor production runs; CNC/AM suit proto and small batch.",
    ]

    secondary_normalized = [p for p in secondary if p != primary]

    return {
        "primary": primary,
        "secondary": secondary_normalized,
        "not_recommended": not_recommended,
        "reasons": reasons,
        "reasons_primary": reasons_primary,
        "reasons_secondary": reasons_secondary_list,
        "tradeoffs": tradeoffs,
        "scores": scores,
        "score_breakdown": score_breakdown,
        "process_gates": gates,
        "eligible_processes": eligible_processes,
        # None when process=AUTO so UI/trace do not imply user explicitly chose "AUTO" as a process.
        "user_selected": None if user_process_raw == "AUTO" else user_process_raw,
    }
