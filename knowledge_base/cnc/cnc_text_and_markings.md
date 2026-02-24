# CNC: Text, Engraving, and Markings

Machined markings add cost, especially when they require very small tools.

## Embossed vs Engraved

- Prefer engraved (recessed) text over embossed (raised)
  - engraving removes less material
  - embossing requires clearing material around raised features

## Alternatives

- If machining is not required, consider laser marking

## Font Guidance

- Use ~20-point sans serif fonts (practical readability and toolpath)
- Sharp internal corners of letters will be rounded due to tool radius

## Agent Heuristics

- Embossed text on metal part without necessity → MEDIUM risk (cycle-time)
- Small text with tight spacing → HIGH risk (tiny tools)
