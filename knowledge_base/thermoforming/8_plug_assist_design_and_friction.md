# Plug Assist Design: Thickness Control, Friction, and Heat Transfer

Plug assistance pre-stretches the sheet and can reduce excessive thinning, especially for female cavity forming. Plug design must balance slip, chilling, marking, and thermal behavior.

## Key DFM Guidelines

- Use plug assist when deep draw causes excessive thinning, especially at bases/corners in female molds.
- Plug requirements:
  - Avoid chilling the sheet (cold plug → incomplete forming / non-uniform draw).
  - Surface must allow controlled sliding; too much friction can distort thickness distribution.
  - Plug must not mark the sheet surface; materials/coatings help.
- Plug materials:
  - Aluminum: requires smooth finish and heating close to sheet temperature to avoid chilling/sticking.
  - Wood/composite with insulating surfaces: can reduce chilling and marking; felt/fabric covers used in practice.
  - Skeleton/rod plugs with coatings for lower contact/marking in some cases.
- Keep consistent spacing between plug and tool around the part to steer distribution.

## Limitations / Risks

- Plug temperature too low → chilling, incomplete forming.
- Excessive plug friction + high plug temperature → sticking and thickness bias (bottom too thick, corners too thin).
- Plug shape (sharp leading radii) can tear the sheet during impact/deformation.

## Agent Heuristics

- Deep female cavity + "thin bottom/corners" complaint → recommend plug assist and tuning (plug temp, shape, slip).
- If user wants "thicker corners" → suggest plug advance timing and minimizing plug-to-mold gap.
- "Surface marks" complaint → suggest plug surface/cover changes and reduced friction.
