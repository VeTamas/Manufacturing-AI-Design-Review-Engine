# SLS — Geometry & Design Rules

## Wall thickness
SLS minimum walls depend on size and function:

- **Thin cosmetic walls:** can exist, but risk warp and fragility
- **Structural walls:** prefer ≥ 1.0–1.5 mm (practical)
- **Large walls:** add ribs to reduce warp

## Feature resolution
- Sharp edges soften slightly due to powder granularity and heat

## Holes
- Small holes may partially fuse or finish undersized
- Critical holes: plan drilling/reaming

## Clearances for assemblies
To print parts that must move:

- **Minimum gap** typically needs to be ≥ 0.3–0.5 mm (practical, depends on scale)
- Include powder escape routes, otherwise parts "freeze"

## Internal cavities & powder trapping
Any enclosed volume becomes a powder trap.

Mitigation:
- Add powder escape holes
- Add multiple escape paths
- Avoid sealed labyrinth volumes unless you accept trapped powder

## Snap fits and living hinges
SLS nylon can flex, but:
- hinge thickness and radius matter
- repeated cycling depends on material grade
