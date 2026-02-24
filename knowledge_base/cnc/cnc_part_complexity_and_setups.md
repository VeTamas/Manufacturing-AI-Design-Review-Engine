# CNC: Part Complexity and Setup Count

Complexity is often driven by tool access, number of faces, and contoured geometry.

## Cost Drivers

- Multi-face machining increases setup time and cost
- Contoured/organic geometry requires small tools and many passes
- Small tools mean slower feeds and longer cycle time

## Simplification Strategies

- Design features on-axis planes where possible
- Avoid unnecessary draft angles (unless functionally needed)
- Avoid organic surfaces unless necessary
- Minimize variations in internal corner radii and thread sizes

## Agent Heuristics

- Multiple faces/features requiring many setups → MEDIUM risk
- Organic/freeform surfaces without necessity → MEDIUM to HIGH risk
- Many different internal radii / thread sizes → MEDIUM risk
