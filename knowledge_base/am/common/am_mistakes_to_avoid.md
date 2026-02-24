# AM: Common Design Mistakes to Avoid

Many AM failures come from ignoring process constraints and downstream steps.

## Frequent Mistakes

- Designing features that require trapped supports or trapped powder
- Ignoring anisotropy and load direction
- Over-optimizing for geometry freedom without manufacturability checks
- Assuming as-printed tolerances and surfaces are production-ready
- Underestimating post-processing and inspection needs

## Agent Heuristics

- Load-bearing part + orientation not discussed → HIGH risk
- Internal geometry + no cleaning/inspection plan → HIGH risk
- Tight tolerances assumed as-printed → HIGH risk