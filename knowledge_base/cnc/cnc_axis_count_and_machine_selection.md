# CNC: Axis Count and Machine Selection

Choosing the right machine configuration affects cost and feasibility.

## 3-Axis Machining

- Lowest cost and most widely available
- Limited to features accessible from orthogonal directions
- Requires multiple setups for complex parts

## 4- and 5-Axis Machining

- Allows access to complex geometry
- Reduces setup count
- Increases programming and machine cost

## Design Trade-Offs

- Designing for 3-axis reduces cost but may limit geometry
- Overusing 5-axis increases cost unnecessarily
- Axis count should align with part complexity

## Agent Heuristics

- Geometry implicitly requires 5-axis but not acknowledged → HIGH risk
- 5-axis chosen for simple geometry → MEDIUM risk
- Axis strategy undefined → MEDIUM risk
