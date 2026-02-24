# Secondary Operations: Trimming, Cutting, Joining, Finishing

Thermoformed parts typically require trimming and cutouts; durable parts often rely on CNC trimming for accuracy.

## Key DFM Guidelines

- Design for trimming:
  - Provide trim flanges where practical.
  - Ensure tool access for routers, knives, presses, dies.
- CNC trimming:
  - Common for heavy gauge parts; plan locating features and fixturing surfaces.
- Joining options:
  - Mechanical fastening (snap fits, inserts)
  - Solvent/adhesive bonding
  - Ultrasonic bonding (material-dependent)
- Decoration:
  - Printing, labeling, painting, metallizing are used depending on resin and surface requirements.

## Limitations / Risks

- Trim scrap can be significant; plan recycling/regrind strategy where relevant.
- Poor trim access increases cost and defect rate.

## Agent Heuristics

- Complex perimeter + many cutouts + tight location tolerances → expect CNC trim and fixture complexity.
- If user ignores trimming in cost discussion → raise MED/HIGH risk (hidden cost driver).
