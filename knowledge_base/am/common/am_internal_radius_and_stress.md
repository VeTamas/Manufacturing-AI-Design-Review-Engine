# AM: Internal Radii and Stress Concentration

Internal geometry strongly affects stress, print quality, and durability.

## Internal Corners

- Sharp internal corners concentrate stress
- Small radii increase crack initiation risk
- Fillets improve both strength and printability

## Process Sensitivity

- Metal AM is especially sensitive to sharp corners
- Polymer AM shows layer separation at sharp edges
- Thermal stress amplifies corner sensitivity

## Design Recommendations

- Use generous internal fillets where possible
- Avoid sharp transitions in load paths
- Balance functional geometry with stress relief

## Agent Heuristics

- Sharp internal corners in load-bearing regions → HIGH risk
- Internal radius near process minimum → MEDIUM to HIGH risk
