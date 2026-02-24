# CNC: Undercuts and Special Tooling

Undercuts are features not reachable by standard axial tools, often requiring special cutters.

## Key Constraints

- Non-standard undercut dimensions may require custom form/keyseat tools
- Custom tooling increases cost and lead time (especially low volume)
- Shallower cuts are preferred to reduce deflection and maintain rigidity

## Accessibility

- Undercuts must be located where the tool can physically reach them
- Poor placement can make features non-machinable

## Agent Heuristics

- Undercut with non-standard dimensions → MEDIUM to HIGH risk
- Deep undercut with small tool → HIGH risk (deflection)
- Undercut placed in inaccessible region → HIGH risk
