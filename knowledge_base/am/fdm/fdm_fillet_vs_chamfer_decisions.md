# FDM: Fillet vs Chamfer Design Decisions

Fillets and chamfers behave differently depending on print orientation.

## Fillet Behavior

- Fillets facing the print bed create steep overhangs
- Downward-facing fillets often degrade surface quality
- Variable layer height can partially mitigate this

## Chamfer Behavior

- Chamfers print more predictably when facing downward
- Better surface quality on functional edges
- Preferred for visible or mating surfaces

## Design Recommendations

- Use chamfers instead of fillets on downward-facing edges
- Reserve fillets for upward-facing or vertical edges
- Consider print orientation during edge treatment selection

## Agent Heuristics

- Downward-facing fillet on functional surface → MEDIUM to HIGH risk
- Edge treatment chosen without orientation awareness → MEDIUM risk
