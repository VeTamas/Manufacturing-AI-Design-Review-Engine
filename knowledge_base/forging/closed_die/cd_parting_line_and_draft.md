# Closed-Die Forging: Parting Line and Draft

Closed-die forging requires a clear concept of how the part opens from the die and how it will be ejected/handled.

## Parting Line Concepts

- Favor parting lines that minimize undercuts and reduce die complexity.
- Place parting line away from critical functional surfaces where possible.
- Expect a flash region near the parting line; plan downstream trimming and machining as needed.

## Draft and Release

- Draft supports release and reduces surface damage risk.
- Draft direction must align with die opening; conflicting draft directions increase complexity.

## Design Notes

- If a feature cannot be formed without trapping the part in the die, it must be redesigned or moved to machining.
- Consider how the part will be oriented for forging and how flow reaches thin/extreme regions.

## Agent Heuristics

- No parting line / draft concept for closed-die forging → HIGH risk
- Undercuts implied by geometry without a die strategy → HIGH risk
- Critical cosmetic/functional surface on/near parting line without plan → MEDIUM to HIGH risk
