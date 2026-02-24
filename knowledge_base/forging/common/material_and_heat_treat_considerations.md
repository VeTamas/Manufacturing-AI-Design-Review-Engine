# Forging: Material and Heat-Treat Considerations

Forging performance depends strongly on alloy choice and downstream heat treatment. Many failures are not "geometry-only" issues; they arise from the interaction of geometry, flow, microstructure, and thermal processing.

## Material Behavior (Practical)

- **Aluminum alloys**
  - Sensitive to process windows; heat treatment often defines final properties.
- **Steels**
  - Broad forging applicability; heat treatment and cleanliness control matter for fatigue.
- **Titanium / nickel alloys**
  - High cost; forging can save machining waste but needs strict process control.

## Heat Treatment and Distortion

- Heat treat can change dimensions and introduce distortion.
- If a part needs tight tolerances, **design datum features** and a **machining sequence** that accounts for distortion risk.

## Design Notes

- Specify critical mechanical requirements (fatigue, impact, yield, hardness) so the process can be selected appropriately.
- If the alloy is notch-sensitive, prioritize generous radii and avoid sharp transitions.
- If corrosion or environment matters, define it early; it can change alloy selection and finishing steps.

## Agent Heuristics

- High mechanical performance requirement + no alloy/heat-treat intent stated → MEDIUM risk
- Tight tolerances + heat treat required + no machining/datum plan → HIGH risk
- Notch-sensitive alloy + small radii/sharp transitions → HIGH risk
