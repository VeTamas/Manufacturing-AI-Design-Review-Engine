# Common Defects: Webbing, Chill Marks, Warpage, Poor Detail (DFM Signals)

Defects often originate from geometry + heating + tooling temperature + vacuum rate interactions. Many issues can be predicted from DFM.

## Key DFM Guidelines

- Webbing/bridging/wrinkling risk increases when:
  - Sheet too hot in center / sag too large
  - Insufficient spacing between multiple molds (bridging between high points)
  - Poor mold layout or excessive draw ratio in local areas
- Chill marks / mark-off:
  - Mold or plug too cold; stretching stops when sheet contacts cold surfaces
  - Insufficient draft/radii aggravate marking and release issues
- "Nipples" on mold side:
  - Vacuum holes too large
  - Vacuum rate too high / sheet too hot can exacerbate

## Limitations / Risks

- Troubleshooting may require process tuning beyond design changes (heater zoning, vacuum restriction, mold temperature).
- Some defects are difficult to fully eliminate without changing forming method (e.g., moving from male to female mold, adding assists).

## Agent Heuristics

- Deep draw + multi-cavity layout + insufficient spacing → HIGH webbing risk.
- Cosmetic surface on mold side + many vacuum holes → HIGH "nipple/vent mark" risk.
- Thin gauge + cold tooling → HIGH chill mark and incomplete forming risk.
