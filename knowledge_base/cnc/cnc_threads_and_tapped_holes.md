# CNC: Threads and Tapped Holes

Threading is manufacturable, but small threads and deep threads increase risk and cost.

## Thread Depth Guidance

- Thread only as deep as needed
- Typical guidance in metals: thread depth ≤ ~2× hole diameter

## Thread Size and Manufacturability

- Prefer the largest thread size allowable
- Very small taps are fragile (notably below M2 / #0-80 class)

## Inserts

- Consider threaded inserts for softer materials (aluminum, plastics)

## Blind Holes

- Add unthreaded length ≥ ~0.5× hole diameter for tap lead + chip removal
- Specify thread details in drawings:
  - thread type, hole size, depth, and any countersinks/blends

## Agent Heuristics

- Thread depth > 2× diameter → MEDIUM to HIGH risk
- Tiny thread spec (≈ below M2) → HIGH risk
- Blind tapped hole without lead/chip allowance → HIGH risk
