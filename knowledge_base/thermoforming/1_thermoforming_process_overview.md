# Thermoforming: Process Overview (Vacuum / Pressure / Sheet Forming)

Thermoforming shapes a heated thermoplastic sheet by forcing it against a mold using vacuum, pressure, mechanical assists (plugs/rings), or combinations. It is widely used from packaging to durable large components. Compared to injection molding, thermoforming generally uses lower forming pressures and can enable cheaper tooling and large part sizes, but wall thickness control and tight tolerances are more difficult.

## Key DFM Guidelines

- Start from sheet: design assumes a constant starting gauge; final thickness varies with draw and contact sequence.
- Choose forming method based on which side needs detail:
  - Male (drape) forming tends to favor "inside" detail.
  - Female (straight vacuum) tends to favor "outside" detail.
- Expect trimming: thermoformed parts usually require edge trim and cutouts; account for trim access and fixturing.

## Limitations / Risks

- Wall thickness cannot be precisely controlled like injection molding; thinning is inherent, especially in deep draw areas.
- Tight tolerances are harder due to shrinkage, cooling gradients, and variable contact.
- One-side detail dominance: unless using matched tooling, detail reproduction is best on the mold-contact side.

## Agent Heuristics

- Large part + moderate volume + cosmetic one-side surface → THERMOFORMING candidate.
- Deep draw + thin gauge + sharp corners → HIGH thinning/webbing risk.
- Requirements for tight +/- tolerances on both sides → consider alternatives (IM, CNC, matched mold thermoforming with higher cost).
- Mention of "sheet", "vacuum forming", "pressure forming", "plug assist", "trim/CNC trim" → boost THERMOFORMING PSI score.
