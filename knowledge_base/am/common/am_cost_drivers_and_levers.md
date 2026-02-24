# AM: Cost Drivers and Cost-Reduction Levers

In many AM workflows, cost is driven by time, material, and post-processing effort.

## Common Cost Drivers

- Part volume (material use)
- Build time (layer count / machine time)
- Support structures (material + removal time)
- Post-processing (finishing, machining, inspection)

## Practical Levers

- Reduce volume without compromising function (lightweighting where valid)
- Orient to reduce supports, but not at the expense of strength/quality
- Design for easy support removal and accessible finishing
- Consolidate assemblies when it reduces labor and tolerance stack-up

## Agent Heuristics

- Support-heavy design + no removal access → HIGH risk (cost + feasibility)
- Cost target low + geometry drives long build time → MEDIUM to HIGH risk
- Post-processing ignored in cost discussion → HIGH risk