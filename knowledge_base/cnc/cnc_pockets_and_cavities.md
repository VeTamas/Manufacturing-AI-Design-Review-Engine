# CNC: Pockets and Cavities (Tool Deflection & Access)

Deep pockets increase tool deflection, chip evacuation issues, and breakage risk.

## Depth vs Width

- Excessively deep cavities are high risk
- Rule of thumb:
  - Cavities deeper than ~6× their width are "too deep"
  - Ideal guideline: depth < 4 × width (D < 4W)

## Design Strategies for Deep Cavities

- Use variable cavity width:
  - wider at the top
  - improved tool access at the bottom

## Sharp Corner Requirement

- If a sharp internal corner is needed for assembly:
  - consider corner reliefs / dogbone cuts instead of tiny radii

## Agent Heuristics

- Pocket depth > 4× width → MEDIUM to HIGH risk
- Pocket depth > 6× width → HIGH risk
- “Sharp corner required” but no relief strategy → HIGH risk
