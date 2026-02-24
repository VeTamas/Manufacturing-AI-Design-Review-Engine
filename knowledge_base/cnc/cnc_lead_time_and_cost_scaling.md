# CNC: Lead Time and Cost Scaling

Design choices directly influence manufacturing speed and cost.

## Lead Time Drivers

- Setup count
- Tool changes
- Programming complexity
- Inspection requirements

## Cost Scaling Effects

- Tight tolerances scale cost non-linearly
- Complex geometry increases both programming and machining time
- Low volume magnifies setup cost impact

## Design Implications

- Simplifying geometry often reduces lead time more than material changes
- Early DFM decisions prevent late-stage delays

## Agent Heuristics

- High complexity for low-volume part → MEDIUM to HIGH risk
- Tight tolerance + low volume → HIGH risk
- Lead time target without design simplification → MEDIUM risk
