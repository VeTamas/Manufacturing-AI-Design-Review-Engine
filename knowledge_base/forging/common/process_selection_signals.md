# Forging: Process Selection Signals (Open vs Closed vs Hybrid)

Choosing between open-die, closed-die, and hybrid approaches depends on volume, shape complexity, and where precision is required.

## Closed-Die Signals

- Production volumes justify tooling
- Near-net external geometry desired
- Parting line and draft can be defined
- Features can be oriented to support material flow and ejection

## Open-Die Signals

- Large/simple shapes
- Low-to-medium volume where flexibility matters
- Part can be forged as a "blocky" preform, then machined

## Hybrid Signals

- Large cross-sections or large parts need open-die preforming
- Closed-die finishing for localized near-net details
- When reducing machining waste is valuable but full closed-die is impractical

## Design Notes

- If you cannot define a plausible parting line/draft/ejection plan, closed-die risk rises.
- If critical features are internal or inaccessible, plan to machine them (or consider another process).

## Agent Heuristics

- Closed-die chosen but parting/draft/ejection not discussed → MEDIUM to HIGH risk
- Open-die chosen but design expects near-net precision everywhere → HIGH risk
- Hybrid is often a cost lever when size is large and geometry is "mostly simple" → MEDIUM opportunity
