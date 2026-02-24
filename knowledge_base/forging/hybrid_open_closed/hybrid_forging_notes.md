# Hybrid Forging: Combining Open-Die and Closed-Die Steps

Hybrid forging uses open-die steps to shape a preform and closed-die steps to finish near-net features.

## When It Helps

- Large cross-sections or large parts need preforming
- Closed-die finishing reduces machining on critical external features
- Improves material utilization for expensive alloys

## Design Notes

- Think in stages: preform geometry → finish features → machining plan.
- Hybrid is a strong candidate when full closed-die tooling would be excessive but pure open-die would require too much machining.

## Agent Heuristics

- Large part + medium complexity → hybrid can reduce machining → MEDIUM opportunity
- Hybrid chosen but stage plan not described → MEDIUM risk (needs process plan)
- Critical features still inaccessible for machining/inspection → HIGH risk
