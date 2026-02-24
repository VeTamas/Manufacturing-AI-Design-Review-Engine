# Tolerances, Surface Finish, and Detail Reproduction

Thermoforming can produce high-quality surfaces, but tolerance control is generally weaker than injection molding due to thickness variation, shrinkage, and thermal gradients.

## Key DFM Guidelines

- Detail reproduction:
  - Best on the mold-contact side; choose forming direction accordingly (male vs female).
  - Matched molds can reproduce fine detail (lettering/grain) with improved dimensional accuracy.
- Surface finish:
  - Mold surface quality matters; overly smooth tools can cause mark-off or release issues in some scenarios.
  - Variable contact and heating can shift gloss and texture.
- Tolerances:
  - Plan datums on the mold-contact side where repeatability is highest.
  - Use secondary ops (CNC trimming, drilling) for critical interfaces.

## Limitations / Risks

- Tight tolerances across large areas are difficult; warpage and shrinkage can dominate.
- Secondary operations add cost and require fixturing design.

## Agent Heuristics

- If user specifies close tolerances on multiple faces → flag risk; suggest matched molds or secondary machining.
- If user wants cosmetic A-surface + fine details → suggest pressure forming/matched molds and careful venting.
