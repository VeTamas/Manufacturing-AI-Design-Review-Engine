# Geometry Rules: Draft, Radii, Undercuts, Ribbing

Thermoformed parts must release from the mold and avoid stress concentration and thinning. Draft and radii are essential DFM levers.

## Key DFM Guidelines

- Draft (taper):
  - Increase mold draft where possible to improve release and reduce defects.
  - Insufficient draft contributes to difficult removal and surface marking.
- Fillets / corner radii:
  - Fillet radii are essential to reduce stress concentration.
  - Rule of thumb: radius at least equal to wall thickness; larger radii improve durability and reduce thinning risk.
- Undercuts:
  - Undercuts complicate tooling; may require split tooling/slides or alternative forming strategies.
- Ribbing:
  - Ribbing can add stiffness and allow thinner gauge sheet, reducing cost and heating time.

## Limitations / Risks

- Sharp corners and abrupt cross-section changes create stress concentration and can drastically reduce service life.
- Deep narrow cavities increase draw ratio locally, increasing thinning and webbing risk.

## Agent Heuristics

- Sharp inside corners / tiny radii + deep draw → HIGH risk; recommend larger radii and/or multi-step forming.
- Undercuts present + simple vacuum forming assumption → flag tooling complexity (split tool/matched molds).
- Stiffness required + thin gauge → recommend ribbing instead of simply increasing gauge.
