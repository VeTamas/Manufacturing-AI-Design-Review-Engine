#!/usr/bin/env python3
"""
Quick validation script for material resolver.
Tests deterministic resolution and backward compatibility.
"""
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from agent.materials import resolve_material, load_material_profiles


def test_material_resolver():
    """Test material resolution with various inputs."""
    print("Testing material resolver...")
    
    # Test legacy mappings (backward compatibility)
    test_cases = [
        ("steel", "steel_generic"),
        ("aluminium", "aluminum_generic"),
        ("aluminum", "aluminum_generic"),
        ("plastic", "plastic_generic"),
        ("stainless", "stainless_generic"),
        ("titanium", "titanium_generic"),
        ("Steel", "steel_generic"),  # Case insensitive
        ("ALUMINUM", "aluminum_generic"),
    ]
    
    all_passed = True
    for material_text, expected_id in test_cases:
        resolution = resolve_material(material_text=material_text)
        actual_id = resolution.profile.id
        if actual_id == expected_id:
            print(f"  PASS: {material_text!r} -> {actual_id} (source={resolution.source})")
        else:
            print(f"  FAIL: {material_text!r} -> {actual_id} (expected {expected_id})")
            all_passed = False
    
    # Test profile loading
    try:
        profiles = load_material_profiles()
        print(f"\nLoaded {len(profiles)} material profiles:")
        for profile in profiles:
            print(f"  - {profile.id}: {profile.label} (family={profile.family.value})")
        print("\nAll tests passed!" if all_passed else "\nSome tests failed!")
        return 0 if all_passed else 1
    except Exception as e:
        print(f"\nError loading profiles: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(test_material_resolver())
