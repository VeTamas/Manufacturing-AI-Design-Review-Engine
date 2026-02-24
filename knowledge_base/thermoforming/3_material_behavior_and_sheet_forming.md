# Material Behavior in Thermoforming (Sheet, Heating, Stretch, Shrinkage)

Thermoforming starts from extruded sheet which is heated into a forming window. Uniform heating is critical; non-uniform heat causes sag variation and thickness instability.

## Key DFM Guidelines

- Design expecting heat-driven stretch:
  - Areas that contact the mold first "freeze" earlier and keep more thickness.
  - Late-contact areas stretch more and become thinner.
- Manage shrinkage and thermal expansion:
  - Expect post-form shrinkage and in-service expansion effects to influence fit and assembly.
- Feedstock quality matters:
  - Sheet gauge uniformity, internal orientation/strain, moisture/contamination affect consistency.
- For thick-gauge durable products: heating and cooling cycles are longer → plan for warpage risk and cycle time.

## Limitations / Risks

- Moisture/contamination can produce bubbles/voids or surface defects.
- Variable gloss/texture can occur due to heating and contact variability.
- Regrind usage can impact forming consistency; uncontrolled regrind increases variability.

## Agent Heuristics

- "Consistent cosmetics" requirement → emphasize sheet quality + controlled heating zones.
- Thin gauge roll-fed packaging vs thick gauge durable parts → different expectations for tolerance and cycle time.
- If user demands "uniform thickness everywhere" → flag as unrealistic; propose thicker starting gauge or multi-step forming methods.
