# CNC: Holes, Drilling, and Depth-to-Diameter

Holes are fastest when drilled with standard drill sizes; otherwise helical milling/reaming increases time.

## Standard Drill Sizes

- Favor standard drill sizes (inch fractions or whole mm steps)
- Non-standard holes may require custom tooling or extra passes

## Depth-to-Diameter (D:D) Guidance

- Keep hole depth-to-diameter as low as possible
- Manufacturable guidance: keep D:D below ~1:10
- Time/cost-saving target: ~1:4

## Other Hole Design Tips

- Avoid partial holes; keep at least ~75% of hole within part edge
- Keep holes/pockets at least ~1/32" (~0.030") from walls (metals)
  - double this distance for plastics/composites (rule of thumb)
- Design holes perpendicular to surfaces; add flats on curved surfaces for drill entry
- Prefer through holes over blind holes
- For blind holes: add ~25% extra depth to allow drill point + chip evacuation
- Avoid hole-cavity intersections; if unavoidable, offset drill axis from cavity center

## Agent Heuristics

- D:D > 1:10 without special process callout → HIGH risk
- Blind hole with no extra depth allowance → MEDIUM risk
- Partial hole near edge → HIGH risk (breakout)
- Hole intersects cavity with no offset strategy → MEDIUM risk
