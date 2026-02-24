# Wall Thickness Distribution and Thinning (Core Thermoforming DFM)

A fundamental thermoforming limitation is non-uniform wall thickness. The thickness distribution depends strongly on method (male vs female), draw depth, plug assist, and friction/heat transfer.

## Key DFM Guidelines

- Male vs Female thickness pattern:
  - Female molds tend to produce thick rims and thinner bottoms in deep containers.
  - Male molds tend to produce the opposite trend.
- Deep draw threshold:
  - When depth becomes large relative to opening width/diameter, plug assist is used to prevent excessive thinning in critical regions.
- Plug assist tuning:
  - Plug temperature and sheet temperature affect chilling, friction, and thickness distribution.
  - Too cold plug can chill sheet → incomplete forming or poor draw.
  - Excessively high friction can thicken bottom region and starve corners.

## Limitations / Risks

- Thickness distribution is never perfectly uniform; aim for "acceptable" distribution.
- Sharp radii and deep corners concentrate thinning and may tear.
- High stretch areas can show whitening, stress, or service cracking.

## Agent Heuristics

- Deep draw + female mold + no plug assist mentioned → HIGH risk of thin bottoms/corners.
- "Load bearing region" in deep part → suggest plug assist to bias thickness.
- Very thin fins/ribs + deep draw → HIGH tear/thinning risk (recommend design simplification or thicker sheet).
