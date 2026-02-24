# Forging: Overview and When It Fits

Forging is a metal-forming process where material is plastically deformed to achieve a desired shape. Compared to machining-from-billet, forging can improve mechanical performance by aligning grain flow and reducing internal discontinuities, but it imposes strong design constraints (draft, parting, radii, and access).

## Common Forging Families

- **Closed-die (impression-die) forging**
  - Near-net shapes with dies; higher tooling cost; good repeatability.
- **Open-die forging**
  - Large/simple shapes and preforms; flexible but less near-net.
- **Hybrid approaches**
  - A preform produced by open-die steps followed by closed-die finishing for near-net features.

## Typical Reasons to Choose Forging

- High strength / fatigue-critical parts
- Demanding safety margins (impact, cyclic loads)
- Production runs where tooling cost amortizes
- When a near-net preform reduces machining waste for expensive alloys

## Typical Reasons Forging May Be a Poor Fit

- Very low quantity prototypes (tooling lead time/cost dominates)
- Shapes requiring deep enclosed cavities, severe undercuts, or inaccessible features
- Tight tolerance requirements without a clear machining plan
- Designs with abrupt section changes that drive defects or die wear

## Design Notes

- Forging creates a **preform**: most precision interfaces are typically machined after forging.
- Good forgings depend on **material flow**: smooth transitions and generous radii matter.
- Forging is not "free complexity": difficult shapes drive die cost, die wear, and quality risk.

## Agent Heuristics

- Tight tolerances assumed "as-forged" without machining plan → HIGH risk
- Small radii + abrupt thickness changes in load paths → HIGH risk
- No draft/parting discussion for closed-die forging → MEDIUM to HIGH risk
- High volume + simple geometry + forging chosen without rationale → MEDIUM risk (check CNC/casting alternatives)
