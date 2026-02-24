# Injection Molding: Material-Specific Behavior (Nylon, POM)

Engineering plastics behave very differently from amorphous materials.

## Nylon (PA)

- Absorbs moisture → dimensional change
- Creep under load is significant
- Shrinkage and anisotropy are high

## POM (Delrin)

- Excellent dimensional stability
- Sensitive to sharp corners
- Requires uniform wall thickness

## Agent Heuristics

- Nylon used without moisture consideration → HIGH risk
- Creep-critical application without analysis → HIGH risk
- Sharp corners in POM → MEDIUM to HIGH risk
- Nylon + no mention of drying/conditioning → HIGH risk (dimensional instability)
- POM + sharp corners → HIGH risk (notch sensitivity)
- Long-term load + Nylon without creep analysis → HIGH risk

## Design Notes

- Nylon parts absorb significant moisture in ambient conditions, causing dimensional change; proper drying before molding and post-mold conditioning are critical
- Nylon exhibits significant creep under constant load; avoid long-term load without analysis
- POM is sensitive to sharp corners and notches, which substantially reduce impact strength; use generous radii
- POM requires uniform wall thickness; avoid thick sections that cause sink marks and warpage
- POM processing benefits from higher melt temperatures and fast fill to reduce warpage; gate size affects flow
