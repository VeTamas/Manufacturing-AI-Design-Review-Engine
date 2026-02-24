# FDM: Thin Walls and Feature Resolution

Feature size must align with nozzle diameter and extrusion behavior.

## Wall Thickness Limits

- Walls thinner than nozzle width are unreliable
- Single-extrusion walls have reduced strength
- Thin vertical walls are prone to warping

## Small Features

- Small holes often print undersized
- Fine details increase print time and failure risk
- Circular features are approximated by polygonal paths

## Design Recommendations

- Wall thickness should be multiples of extrusion width
- Critical holes should be drilled post-print if precision is needed
- Avoid decorative micro-features on functional parts

## Agent Heuristics

- Wall thickness < nozzle width → HIGH risk
- Precision holes without post-processing plan → HIGH risk
- Micro-features on load-bearing parts → MEDIUM risk
