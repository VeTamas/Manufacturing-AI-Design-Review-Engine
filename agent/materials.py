"""
Deterministic material profiles and resolver.

Material profiles are loaded from data/materials/material_profiles.json.
Resolver maps user input strings to material profiles with property vectors.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Literal, Optional

from agent.utils.filetrace import traced_open

# Module-level cache for material profiles (deterministic singleton)
_MATERIAL_PROFILES_CACHE: Optional[list[dict]] = None


class MaterialFamily(str, Enum):
    """Material family categories."""
    STEEL = "STEEL"
    ALUMINUM = "ALUMINUM"
    THERMOPLASTIC = "THERMOPLASTIC"
    STAINLESS_STEEL = "STAINLESS_STEEL"
    TITANIUM = "TITANIUM"


class Machinability(str, Enum):
    """Machinability levels."""
    VERY_HARD = "VERY_HARD"
    HARD = "HARD"
    MEDIUM = "MEDIUM"
    EASY = "EASY"


class Formability(str, Enum):
    """Formability levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Castability(str, Enum):
    """Castability levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Extrudability(str, Enum):
    """Extrudability levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Weldability(str, Enum):
    """Weldability levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class HardnessClass(str, Enum):
    """Hardness classification."""
    SOFT = "SOFT"
    MEDIUM = "MEDIUM"
    HARD = "HARD"


class ThermalConductivity(str, Enum):
    """Thermal conductivity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class CorrosionSensitivity(str, Enum):
    """Corrosion sensitivity levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AMReadiness(str, Enum):
    """AM readiness levels."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AMPostprocess(str, Enum):
    """AM post-processing intensity."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass
class MaterialProperties:
    """Material property vector."""
    machinability: Machinability
    formability: Formability
    castability: Castability
    extrudability: Extrudability
    weldability: Weldability
    hardness_class: HardnessClass
    thermal_conductivity: ThermalConductivity
    corrosion_sensitivity: CorrosionSensitivity
    am_readiness: AMReadiness
    am_postprocess_intensity: AMPostprocess

    @classmethod
    def from_dict(cls, props: dict) -> MaterialProperties:
        """Create from dict (from JSON)."""
        return cls(
            machinability=Machinability(props["machinability"]),
            formability=Formability(props["formability"]),
            castability=Castability(props["castability"]),
            extrudability=Extrudability(props["extrudability"]),
            weldability=Weldability(props["weldability"]),
            hardness_class=HardnessClass(props["hardness_class"]),
            thermal_conductivity=ThermalConductivity(props["thermal_conductivity"]),
            corrosion_sensitivity=CorrosionSensitivity(props["corrosion_sensitivity"]),
            am_readiness=AMReadiness(props["am_readiness"]),
            am_postprocess_intensity=AMPostprocess(props["am_postprocess_intensity"]),
        )


@dataclass
class MaterialProfile:
    """Material profile with properties."""
    id: str
    label: str
    family: MaterialFamily
    aliases: list[str]
    properties: MaterialProperties

    @classmethod
    def from_dict(cls, data: dict) -> MaterialProfile:
        """Create from dict (from JSON)."""
        return cls(
            id=data["id"],
            label=data["label"],
            family=MaterialFamily(data["family"]),
            aliases=data["aliases"],
            properties=MaterialProperties.from_dict(data["properties"]),
        )


@dataclass
class MaterialResolution:
    """Result of material resolution."""
    profile: MaterialProfile
    source: Literal["profile_id", "alias", "family_default", "fallback_unknown"]
    matched_text: Optional[str] = None


def _normalize_text(text: str) -> str:
    """Normalize material text for matching: lowercase, strip, remove punctuation, collapse whitespace."""
    text = text.lower().strip()
    # Remove common punctuation
    text = re.sub(r'[^\w\s-]', '', text)
    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def load_material_profiles(path: Optional[Path] = None) -> list[MaterialProfile]:
    """
    Load material profiles from JSON file.
    
    Default path: data/materials/material_profiles.json (relative to project root).
    Profiles are cached in module-level singleton for deterministic behavior.
    """
    global _MATERIAL_PROFILES_CACHE
    
    if _MATERIAL_PROFILES_CACHE is not None:
        return _MATERIAL_PROFILES_CACHE
    
    if path is None:
        # Default: project root / data / materials / material_profiles.json
        project_root = Path(__file__).resolve().parents[1]
        path = project_root / "data" / "materials" / "material_profiles.json"
    
    if not path.exists():
        raise FileNotFoundError(f"Material profiles file not found: {path}")
    
    with traced_open(path, encoding="utf-8") as f:
        data = json.load(f)
    
    profiles = [MaterialProfile.from_dict(p) for p in data["profiles"]]
    _MATERIAL_PROFILES_CACHE = profiles
    return profiles


def resolve_material(
    material_text: Optional[str] = None,
    material_profile_id: Optional[str] = None,
    material_family: Optional[str] = None,
) -> MaterialResolution:
    """
    Resolve material from user input to MaterialProfile.
    
    Resolution order:
    1. If material_profile_id provided and exists -> use it
    2. Else if material_text provided -> match against aliases (normalized)
    3. Else if material_family provided -> use default profile for family
    4. Else fallback -> steel_generic (backward compatibility)
    
    Legacy mapping (for backward compatibility):
    - "steel" => steel_generic
    - "aluminium"/"aluminum" => aluminum_generic
    - "plastic" => plastic_generic
    """
    profiles = load_material_profiles()
    
    # 1. Profile ID match
    if material_profile_id:
        for profile in profiles:
            if profile.id == material_profile_id:
                return MaterialResolution(profile=profile, source="profile_id")
    
    # 2. Text/alias match
    if material_text:
        normalized = _normalize_text(material_text)
        
        # Legacy mapping first (backward compatibility)
        legacy_map = {
            "steel": "steel_generic",
            "aluminium": "aluminum_generic",
            "aluminum": "aluminum_generic",
            "plastic": "plastic_generic",
        }
        if normalized in legacy_map:
            profile_id = legacy_map[normalized]
            for profile in profiles:
                if profile.id == profile_id:
                    return MaterialResolution(profile=profile, source="alias", matched_text=material_text)
        
        # Exact alias match (normalized)
        for profile in profiles:
            for alias in profile.aliases:
                if _normalize_text(alias) == normalized:
                    return MaterialResolution(profile=profile, source="alias", matched_text=material_text)
    
    # 3. Family default
    if material_family:
        family_map = {
            "STEEL": "steel_generic",
            "ALUMINUM": "aluminum_generic",
            "THERMOPLASTIC": "plastic_generic",
            "STAINLESS_STEEL": "stainless_generic",
            "TITANIUM": "titanium_generic",
        }
        profile_id = family_map.get(material_family.upper())
        if profile_id:
            for profile in profiles:
                if profile.id == profile_id:
                    return MaterialResolution(profile=profile, source="family_default")
    
    # 4. Fallback (backward compatibility: default to steel)
    for profile in profiles:
        if profile.id == "steel_generic":
            return MaterialResolution(profile=profile, source="fallback_unknown")
    
    # Should never reach here, but safety fallback
    return MaterialResolution(profile=profiles[0], source="fallback_unknown")
