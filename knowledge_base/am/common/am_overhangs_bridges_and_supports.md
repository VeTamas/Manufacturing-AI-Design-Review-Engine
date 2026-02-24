# AM: Overhangs, Bridges, and Support Dependency

Overhang and bridge behavior varies by AM process but remains a primary
driver of supports and surface quality.

## Overhang Behavior

- Overhang limits depend on material and process
- Downward-facing surfaces show worst surface finish
- Supports increase cost and post-processing effort

## Bridge Behavior

- Short bridges may print without supports
- Long bridges sag and reduce dimensional accuracy
- Cooling strategy affects bridge quality

## Design Implications

- Avoid long unsupported horizontal spans
- Place cosmetic surfaces away from support contact
- Reorient or split parts to reduce support need

## Agent Heuristics

- Long unsupported bridges → HIGH risk
- Cosmetic surface requiring heavy supports → MEDIUM to HIGH risk
- Support dependency ignored in design → HIGH risk
