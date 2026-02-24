# CNC: Tool Access and Reach Constraints

Tool accessibility defines what features can be machined reliably.

## Reach Limitations

- Long-reach tools are less rigid
- Increased stick-out amplifies chatter and deflection
- Deep features increase cycle time and tool wear

## Accessibility Considerations

- Features should be reachable with standard tools
- Hidden or recessed features increase risk
- Side-access features may require additional setups or 5-axis machining

## Design Implications

- Shallow, open features are cheaper and more reliable
- Tool reach should be minimized whenever possible
- Accessibility should be validated early in design

## Agent Heuristics

- Deep feature requiring long-reach tool → HIGH risk
- Feature inaccessible from standard orientations → HIGH risk
- Tool reach not considered → MEDIUM risk
