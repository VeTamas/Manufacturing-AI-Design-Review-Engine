# CNC: Tolerances and GD&T Cost Reality

Tolerance choices strongly affect cost, scrap rate, and inspection effort.

## Typical Tolerance Baselines

- General CNC tolerances: ±0.005"
- Tight tolerances commonly achievable: ±0.001" (often with special setups)
- Plastics/composites typically have ~2× the tolerance of metals (rule of thumb)

## Tight Tolerance Trade-Offs

- Tighter tolerances can:
  - increase scrap rate
  - require special fixturing and measurement tools
  - slow cycle time
  - increase cost significantly (can more than double vs standard in some cases)

## Communication Requirements

- Tight tolerances must be called out only on critical features
- Drawings/spec sheets are the best way to communicate tolerance intent
- GD&T is possible but increases inspection time and cost

## Agent Heuristics

- Global tight tolerance blanket → HIGH risk (cost + lead time)
- GD&T applied without inspection plan → MEDIUM risk
- Tight tolerance required but critical dimensions not identified → HIGH risk
