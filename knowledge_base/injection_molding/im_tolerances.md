# Injection Molding: Tolerances and Fit Expectations

Injection molding does not inherently guarantee tight tolerances.

## Reality Check

- Typical tolerances are looser than CNC machining
- Material, thickness, and tool quality dominate accuracy
- Environmental effects (humidity, temperature) matter

## Design Guidance

- Apply tight tolerances only where functionally required
- Avoid tolerance chains across multiple molded features
- Use post-machining for critical fits

## Agent Heuristics

- Tight tolerances specified globally → HIGH risk
- Press-fit assumed as-molded → HIGH risk
- No tolerance strategy described → MEDIUM risk

## Design Notes

- Typical achievable tolerances are tighter for small parts and looser for large parts; part size significantly affects tolerance capability
- Tolerance stack-ups across multiple features compound; avoid chaining tight tolerances
- Post-machining allowances should be added on surfaces requiring machining for critical fits
- Coating thickness can materially affect fit and tolerances; account for coating thickness in tolerance planning
