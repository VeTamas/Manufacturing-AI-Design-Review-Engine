# Open-Die Forging: Overview and Constraints

Open-die forging is flexible and well-suited for large/simple shapes and preforms. It typically does not create complex near-net geometry; machining is expected.

## Typical Outputs

- Billet-like preforms with improved structure
- Large components where closed-die tooling is impractical

## Constraints

- Limited ability to form deep/complex external details
- Dimensional precision typically relies on machining

## Design Notes

- Use open-die forging when the part can be represented as a "strong preform" plus machining.
- Consider hybrid if localized near-net features are needed later.

## Agent Heuristics

- Open-die selected but design expects near-net complexity → HIGH risk
- Critical interfaces not marked for machining → HIGH risk
- Large part + complex details → consider hybrid → MEDIUM opportunity
