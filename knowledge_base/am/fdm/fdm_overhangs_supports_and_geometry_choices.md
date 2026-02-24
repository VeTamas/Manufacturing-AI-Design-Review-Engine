# FDM: Overhangs, Supports, and Geometry Choices

In FDM printing, geometry directly determines the need for supports and final surface quality.

## Overhang Behavior

- Overhangs above ~45° typically require supports
- Short bridges can often be printed without supports
- Smaller nozzle diameters reduce printable overhang angle tolerance

## Support Surface Quality

- Surfaces printed on supports have inferior finish
- Support-contact surfaces often require post-processing
- Visible surfaces should avoid support dependency

## Design Implications

- Reorient parts to minimize visible supported surfaces
- Split parts into multiple prints if it reduces support need
- Evaluate whether supported surfaces are functional or cosmetic

## Agent Heuristics

- Visible cosmetic surface requiring supports → MEDIUM to HIGH risk
- Long unsupported overhangs → HIGH risk
- Design assumes mid-air printing → HIGH risk
