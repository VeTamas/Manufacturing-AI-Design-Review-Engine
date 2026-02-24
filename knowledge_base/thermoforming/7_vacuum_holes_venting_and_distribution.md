# Vacuum Holes, Venting, and Vacuum Distribution (Avoiding Incomplete Forming)

Vacuum forming relies on evacuating trapped air between sheet and mold. Venting quality drives detail capture, defect risk, and consistency.

## Key DFM Guidelines

- Provide adequate vacuum holes/slots to pull sheet uniformly.
- Hole size tradeoff:
  - Too large → visible "nipples"/marks on the mold side and cosmetic issues.
  - Too small / clogged / insufficient → incomplete draw, trapped air, poor detail.
- Vacuum distribution:
  - Ensure vacuum reaches all critical areas; poor distribution causes unbalanced draw and inconsistent parts.
- Porous tooling strategies:
  - Porous tool surfaces can reduce visible vent marks and allow complex venting, but thickness/porosity and finishing affect airflow.

## Limitations / Risks

- Incomplete forming and poor detail often trace back to venting/vacuum rate issues.
- Very fast vacuum rates can contribute to defects; too slow can cause sag/bridging depending on heating.

## Agent Heuristics

- "Visible dots/bumps" on cosmetic face → suspect vacuum hole sizing/placement.
- "Poor detail" + "vacuum forming" → recommend vacuum distribution review + mold temperature + hole pattern.
- High cosmetic requirement on mold side → warn about vent mark risk and suggest mitigation (smaller holes, porous inserts, surface texture strategies).
