from __future__ import annotations

PRESETS = {
    "Deep pocket + thin wall (chatter risk)": {
        "part_size": "Medium",
        "min_internal_radius": "Medium",
        "min_wall_thickness": "Thin",
        "hole_depth_class": "Moderate",
        "pocket_aspect_class": "Extreme",
        "feature_variety": "Medium",
        "accessibility_risk": "Low",
        "has_clamping_faces": True,
    },
    "Small radii + deep holes + high variety": {
        "part_size": "Small",
        "min_internal_radius": "Small",
        "min_wall_thickness": "Medium",
        "hole_depth_class": "Deep",
        "pocket_aspect_class": "OK",
        "feature_variety": "High",
        "accessibility_risk": "Medium",
        "has_clamping_faces": True,
    },
}