# Injection Molding: Undercuts and Tooling Complexity

Undercuts significantly increase mold cost and lead time.

## Tooling Implications

- Side actions and lifters increase mold complexity
- More moving parts reduce tool reliability
- Tool cost often dominates part economics

## Design Recommendations

- Avoid undercuts where possible
- Replace undercuts with snap features or assembly
- Align features with mold open direction

## Agent Heuristics

- Undercut without justification → HIGH risk
- Multiple side actions in low-volume part → HIGH risk
- Undercut in cosmetic surface → HIGH risk

## Design Notes

- Side actions significantly increase tool cost per action; limit the number of side actions for cost control
- Lifters are often preferred over side actions for internal undercuts; they tend to be simpler and more reliable
- Snap features can replace undercuts; design snaps with adequate clearance for deflection during assembly
- Threaded inserts: avoid overmolding metal inserts in low-volume parts; consider post-mold insertion instead
