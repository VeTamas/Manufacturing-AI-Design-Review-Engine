"""Simplified deterministic scoring for portfolio / public demo.

PORTFOLIO DEMO MODE:
- This module implements a small set of simplified rules and weights for public release.
- Results are deterministic and plausible but not equivalent to production heuristics.
- Use PORTFOLIO_MODE=0 and the full logic in agent.nodes.process_selection for production.
"""
from __future__ import annotations

# Same process tuple as process_selection for compatibility
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

# Simple weights (portfolio demo only; production uses detailed heuristics)
WEIGHT_MATERIAL_CNC = 3
WEIGHT_MATERIAL_IM = 3
WEIGHT_VOLUME_PROTO_AM = 2
WEIGHT_VOLUME_PROTO_CNC = 1
WEIGHT_VOLUME_PROD_IM = 2
WEIGHT_VOLUME_PROD_CASTING = 1
WEIGHT_FEATURE_HIGH_AM = 1
WEIGHT_TOLERANCE_HIGH_CNC = 1
SECONDARY_DELTA = 2  # Max score gap for secondary (portfolio: simple tie-break)


def _portfolio_scores(
    material: str,
    production_volume: str,
    part_size: str,
    feature_variety: str,
    tolerance_criticality: str,
    user_process_raw: str,
    eligible_processes: list[str],
    user_text: str = "",
) -> tuple[dict[str, int], dict[str, list[dict]], list[str]]:
    """
    Compute scores and breakdown for eligible processes only.
    Returns (scores, score_breakdown, all_reasons).
    """
    scores: dict[str, int] = {p: 0 for p in CANDIDATES}
    score_breakdown: dict[str, list[dict]] = {p: [] for p in CANDIDATES}
    reasons: list[str] = []
    text = (user_text or "").lower()

    # ----- Material base (simplified) -----
    if material in ("Steel", "Aluminum", "Stainless Steel", "Titanium"):
        if "CNC" in eligible_processes:
            scores["CNC"] = WEIGHT_MATERIAL_CNC
            score_breakdown["CNC"].append({"delta": WEIGHT_MATERIAL_CNC, "reason": "Metal material favors CNC", "rule_id": "PORT_CNC_METAL", "severity": "info"})
            reasons.append("Metal material favors CNC")
        if "CASTING" in eligible_processes:
            scores["CASTING"] = 1
            score_breakdown["CASTING"].append({"delta": 1, "reason": "Metal allows casting", "rule_id": "PORT_CAST_METAL", "severity": "info"})
        if "FORGING" in eligible_processes:
            scores["FORGING"] = 1
            score_breakdown["FORGING"].append({"delta": 1, "reason": "Metal allows forging", "rule_id": "PORT_FORG_METAL", "severity": "info"})
        if "SHEET_METAL" in eligible_processes:
            scores["SHEET_METAL"] = 1
            score_breakdown["SHEET_METAL"].append({"delta": 1, "reason": "Metal allows sheet metal", "rule_id": "PORT_SM_METAL", "severity": "info"})
        if "MIM" in eligible_processes:
            scores["MIM"] = 0  # No base; keyword or volume can add
        if "EXTRUSION" in eligible_processes and material in ("Aluminum", "Stainless Steel"):
            scores["EXTRUSION"] = 1
            score_breakdown["EXTRUSION"].append({"delta": 1, "reason": "Aluminum/stainless favor extrusion", "rule_id": "PORT_EXTR_AL", "severity": "info"})
    elif material == "Plastic":
        if "INJECTION_MOLDING" in eligible_processes:
            scores["INJECTION_MOLDING"] = WEIGHT_MATERIAL_IM
            score_breakdown["INJECTION_MOLDING"].append({"delta": WEIGHT_MATERIAL_IM, "reason": "Plastic material favors injection molding", "rule_id": "PORT_IM_PLASTIC", "severity": "info"})
            reasons.append("Plastic material favors injection molding")
        if "AM" in eligible_processes:
            scores["AM"] = 1
            score_breakdown["AM"].append({"delta": 1, "reason": "Plastic allows AM", "rule_id": "PORT_AM_PLASTIC", "severity": "info"})
        if "CNC" in eligible_processes:
            scores["CNC"] = 1
            score_breakdown["CNC"].append({"delta": 1, "reason": "Plastic allows CNC", "rule_id": "PORT_CNC_PLASTIC", "severity": "info"})
        if "THERMOFORMING" in eligible_processes:
            scores["THERMOFORMING"] = 1
            score_breakdown["THERMOFORMING"].append({"delta": 1, "reason": "Plastic allows thermoforming", "rule_id": "PORT_THERM_PLASTIC", "severity": "info"})
        if "COMPRESSION_MOLDING" in eligible_processes:
            scores["COMPRESSION_MOLDING"] = 0

    # ----- Volume (simplified) -----
    if production_volume in ("Proto", "Small batch"):
        if "CNC" in eligible_processes:
            scores["CNC"] = scores.get("CNC", 0) + WEIGHT_VOLUME_PROTO_CNC
            score_breakdown["CNC"].append({"delta": WEIGHT_VOLUME_PROTO_CNC, "reason": "Low volume favors CNC flexibility", "rule_id": "PORT_VOL_CNC", "severity": "info"})
            reasons.append("Low volume favors CNC flexibility")
        if "AM" in eligible_processes:
            scores["AM"] = scores.get("AM", 0) + WEIGHT_VOLUME_PROTO_AM
            score_breakdown["AM"].append({"delta": WEIGHT_VOLUME_PROTO_AM, "reason": "Proto/small batch favors AM", "rule_id": "PORT_VOL_AM", "severity": "info"})
            reasons.append("Proto/small batch favors AM")
        if "INJECTION_MOLDING" in eligible_processes:
            scores["INJECTION_MOLDING"] = scores.get("INJECTION_MOLDING", 0) - 2
            score_breakdown["INJECTION_MOLDING"].append({"delta": -2, "reason": "Low volume tooling risk (IM)", "rule_id": "PORT_IM_LOWVOL", "severity": "med"})
        if "MIM" in eligible_processes:
            scores["MIM"] = scores.get("MIM", 0) - 2
            score_breakdown["MIM"].append({"delta": -2, "reason": "Low volume tooling risk (MIM)", "rule_id": "PORT_MIM_LOWVOL", "severity": "med"})
    elif production_volume == "Production":
        if "INJECTION_MOLDING" in eligible_processes:
            scores["INJECTION_MOLDING"] = scores.get("INJECTION_MOLDING", 0) + WEIGHT_VOLUME_PROD_IM
            score_breakdown["INJECTION_MOLDING"].append({"delta": WEIGHT_VOLUME_PROD_IM, "reason": "Production volume favors IM economics", "rule_id": "PORT_IM_PROD", "severity": "info"})
        if "CASTING" in eligible_processes:
            scores["CASTING"] = scores.get("CASTING", 0) + WEIGHT_VOLUME_PROD_CASTING
            score_breakdown["CASTING"].append({"delta": WEIGHT_VOLUME_PROD_CASTING, "reason": "Production volume favors casting", "rule_id": "PORT_CAST_PROD", "severity": "info"})
        if "MIM" in eligible_processes:
            scores["MIM"] = scores.get("MIM", 0) + 1
            score_breakdown["MIM"].append({"delta": 1, "reason": "Production volume favors MIM", "rule_id": "PORT_MIM_PROD", "severity": "info"})

    # ----- Geometry (minimal) -----
    if feature_variety == "High" and "AM" in eligible_processes:
        scores["AM"] = scores.get("AM", 0) + WEIGHT_FEATURE_HIGH_AM
        score_breakdown["AM"].append({"delta": WEIGHT_FEATURE_HIGH_AM, "reason": "High feature variety favors AM", "rule_id": "PORT_AM_FEATURE", "severity": "info"})
    if tolerance_criticality == "High" and "CNC" in eligible_processes:
        scores["CNC"] = scores.get("CNC", 0) + WEIGHT_TOLERANCE_HIGH_CNC
        score_breakdown["CNC"].append({"delta": WEIGHT_TOLERANCE_HIGH_CNC, "reason": "Tight tolerances favor CNC", "rule_id": "PORT_CNC_TOL", "severity": "info"})

    # ----- User selection (simple bias when not AUTO) -----
    user_process = None if user_process_raw == "AUTO" else user_process_raw
    if user_process and user_process in eligible_processes:
        scores[user_process] = scores.get(user_process, 0) + 1
        score_breakdown[user_process].append({"delta": 1, "reason": "User-selected process bias", "rule_id": "PORT_USER", "severity": "info"})

    # ----- One simple keyword check for demo plausibility -----
    if "extrusion" in text or "profile" in text:
        if "EXTRUSION" in eligible_processes:
            scores["EXTRUSION"] = scores.get("EXTRUSION", 0) + 2
            score_breakdown["EXTRUSION"].append({"delta": 2, "reason": "Description suggests extrusion", "rule_id": "PORT_KW_EXTR", "severity": "info"})
    if "sheet metal" in text or "bend" in text:
        if "SHEET_METAL" in eligible_processes:
            scores["SHEET_METAL"] = scores.get("SHEET_METAL", 0) + 2
            score_breakdown["SHEET_METAL"].append({"delta": 2, "reason": "Description suggests sheet metal", "rule_id": "PORT_KW_SM", "severity": "info"})
    if "additive" in text or "3d print" in text:
        if "AM" in eligible_processes:
            scores["AM"] = scores.get("AM", 0) + 2
            score_breakdown["AM"].append({"delta": 2, "reason": "Description suggests additive", "rule_id": "PORT_KW_AM", "severity": "info"})

    # Ineligible processes stay at 0 (gating already applied by caller)
    for p in CANDIDATES:
        if p not in eligible_processes:
            scores[p] = 0

    return scores, score_breakdown, reasons


def _portfolio_tiebreak(
    scores: dict[str, int],
    eligible_processes: list[str],
    user_process_raw: str,
) -> tuple[str, list[str], list[str]]:
    """
    Simple deterministic tie-break: primary = max score, secondary = next within SECONDARY_DELTA.
    Returns (primary, secondary, not_recommended).
    """
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
        if p in excluded:
            continue
        if user_process and p == user_process:
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
    Compute full process_recommendation dict using portfolio demo scoring.
    Same shape as production process_recommendation for drop-in use.
    """
    scores, score_breakdown, all_reasons = _portfolio_scores(
        material=material,
        production_volume=production_volume,
        part_size=part_size,
        feature_variety=feature_variety,
        tolerance_criticality=tolerance_criticality,
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

    # Normalize secondary: remove primary if present
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
        "user_selected": user_process_raw,
    }
