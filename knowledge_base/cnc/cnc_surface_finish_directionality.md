# CNC: Surface Finish Directionality

Surface finish quality depends on toolpath direction and feature orientation.

## Toolpath Effects

- Parallel toolpaths produce directional marks
- Finish quality varies with tool approach angle
- Contoured surfaces amplify directional artifacts

## Design Implications

- Cosmetic surfaces should align with favorable tool directions
- Functional surfaces may require secondary finishing
- Orientation relative to spindle matters

## Agent Heuristics

- Cosmetic surface with unfavorable tool direction → MEDIUM risk
- Finish requirement without toolpath awareness → MEDIUM risk
