# CNC: Internal Radii and Fillets (Tooling & Cycle-Time)

Internal corners cannot be perfectly sharp in milling; tool radius dictates achievable geometry.

## Inside Corner Fillets

- Prefer larger internal radii for better tool rigidity and efficiency
- Avoid small, deep radii (high chatter and cycle-time risk)
- Avoid radii that exactly match common standard tool sizes (clearance issue)
- Recommended minimum internal radii: > 1/32"

### Practical Heuristic (Vendor Tip)

- Choose radius ~1.3× the radius of the closest standard tool size
- Aim for pocket radii-to-depth ratio ~1:4 (radius : depth)

## Floor Fillets

- Floor fillets are time-consuming; avoid unless necessary
- If floor radius meets a wall corner, make floor radius smaller than wall radius
  - enables single tool usage, improves smoothness
- Deep cuts (> ~2× tool diameter) often require slower feeds → higher cost

## Agent Heuristics

- Small internal corner radius in deep pocket → HIGH risk (tooling/cycle-time)
- Radius matches standard tool radius exactly → MEDIUM risk (clearance/chatter)
- Floor fillets on non-critical surfaces → MEDIUM risk
