"""Hard gating: material-family vs process compatibility.

Ensures clearly incompatible processes never appear in scoring or "Less suitable".
"""
from __future__ import annotations

from typing import Literal

# Material family keywords
_METAL_KW = frozenset({"steel", "aluminum", "stainless", "titanium", "brass", "copper", "metal"})
_POLYMER_KW = frozenset({"plastic", "abs", "pla", "pp", "pe", "pc", "nylon", "pom", "petg", "polyester", "polyethylene", "polypropylene", "polycarbonate", "polymer", "resin"})


def material_family(material: str) -> Literal["metal", "polymer", "unknown"]:
    """Classify material as metal, polymer, or unknown."""
    m = (material or "").lower().strip()
    if not m:
        return "unknown"
    if m in _METAL_KW or any(kw in m for kw in _METAL_KW):
        return "metal"
    if m in _POLYMER_KW or any(kw in m for kw in _POLYMER_KW):
        return "polymer"
    # Inputs material enum: Aluminum, Steel, Plastic
    if m in ("aluminum", "steel"):
        return "metal"
    if m == "plastic":
        return "polymer"
    return "unknown"


def hard_gates(
    processes: tuple[str, ...],
    material: str,
) -> dict[str, dict[str, bool | str]]:
    """Return eligibility map: {proc: {"eligible": bool, "reason": str}}."""
    family = material_family(material)
    result: dict[str, dict[str, bool | str]] = {}
    for p in processes:
        result[p] = {"eligible": True, "reason": ""}
    if family == "metal":
        for proc in ("INJECTION_MOLDING", "COMPRESSION_MOLDING", "THERMOFORMING"):
            if proc in result:
                result[proc] = {"eligible": False, "reason": "polymer process"}
    elif family == "polymer":
        for proc in ("FORGING", "MIM", "CASTING"):
            if proc in result:
                result[proc] = {"eligible": False, "reason": "metal process"}
    return result
