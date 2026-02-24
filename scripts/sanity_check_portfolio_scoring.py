#!/usr/bin/env python3
"""Quick sanity check for portfolio baseline scoring (4–6 representative scenarios).

Validates that primary/secondary are plausible and not always CNC/AM after
unknown-material and sheet-metal-proto changes.
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from agent.scoring.portfolio_scoring import CANDIDATES, compute_portfolio_recommendation
from agent.processes.gating import hard_gates


def run(
    material: str,
    production_volume: str,
    tolerance_criticality: str,
    feature_variety: str,
    part_size: str = "Medium",
    min_wall_thickness: str = "Medium",
    user_process: str = "AUTO",
) -> dict:
    gates = hard_gates(CANDIDATES, material)
    eligible = [p for p in CANDIDATES if gates.get(p, {}).get("eligible", True)]
    if not eligible:
        eligible = ["CNC"]
    return compute_portfolio_recommendation(
        material=material,
        production_volume=production_volume,
        tolerance_criticality=tolerance_criticality,
        feature_variety=feature_variety,
        part_size=part_size,
        min_wall_thickness=min_wall_thickness,
        user_process_raw=user_process,
        eligible_processes=eligible,
        gates=gates,
    )


def main():
    scenarios = [
        ("metal / proto / high tolerance", run("Steel", "Proto", "High", "Medium")),
        ("metal / production / low tolerance", run("Aluminum", "Production", "Low", "Low")),
        ("polymer / production", run("ABS", "Production", "Medium", "Low")),
        ("polymer / proto / high feature variety", run("Nylon", "Proto", "Medium", "High")),
        ("unknown material / proto", run("CustomAlloy", "Proto", "Medium", "Medium")),
        ("metal / proto / sheet-metal-friendly (thin, low variety)", run("Steel", "Proto", "Low", "Low", min_wall_thickness="Thin")),
    ]
    print("Portfolio scoring sanity check")
    print("=" * 60)
    for name, rec in scenarios:
        primary = rec.get("primary", "")
        secondary = rec.get("secondary", [])
        user_sel = rec.get("user_selected")
        print(f"  {name}")
        print(f"    -> primary={primary}, secondary={secondary}, user_selected={user_sel!r}")
    print("=" * 60)
    primaries = [s[1].get("primary") for s in scenarios]
    assert not all(p == "CNC" for p in primaries), "All primary CNC is not plausible"
    assert not all(p == "AM" for p in primaries), "All primary AM is not plausible"
    print("PASS: primary/secondary variety looks plausible")


if __name__ == "__main__":
    main()
    sys.exit(0)
