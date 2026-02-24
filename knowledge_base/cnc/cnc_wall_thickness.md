# CNC: Wall Thickness and Chatter Risk

Thin walls reduce rigidity and can cause vibration (chatter), loss of accuracy, and breakthrough.

## Minimum Wall Thickness (Vendor Guidance)

- Metals: ≥ 0.030" (0.762 mm)
- Plastics & composites: ≥ 0.060" (1.52 mm)

## Design Implications

- Thin walls increase:
  - chatter and poor finish
  - dimensional inaccuracy
  - risk of deformation after machining

## Agent Heuristics

- Wall thickness below guidance → HIGH risk
- Tall thin walls with tight tolerances → HIGH risk
