# Sheet Metal: Bend Relief Dimensions and Placement

Correct bend relief sizing is essential for predictable forming.

## Relief Width and Depth

- Reliefs must exceed minimum tooling limits
- Undersized reliefs behave as if absent
- Relief depth must extend past bend region

## Placement Rules

- Reliefs required where bends intersect
- Corner reliefs prevent tearing
- Relief geometry must align with bend direction

## Design Implications

- Incorrect reliefs cause cracking or distortion
- Oversized reliefs may weaken corners
- CAD defaults are not always manufacturing-safe

## Agent Heuristics

- Relief width below tooling capability → HIGH risk
- Relief depth not exceeding bend zone → HIGH risk
- Default CAD relief without validation → MEDIUM risk
