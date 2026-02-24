# SLA (Stereolithography) — Process Overview

SLA is a vat photopolymerization process where a UV laser (or projected UV image) cures liquid resin layer-by-layer.

## What SLA is best at
- Very fine detail resolution (small features, crisp edges)
- Smooth surfaces vs powder processes
- Good for cosmetic prototypes, fit-checks, small fixtures, master patterns
- Transparent/clear parts possible (with finishing)

## Common constraints that matter in design
- Supports are almost always required
- Orientation strongly affects:
  - support quantity
  - surface quality on "down-facing" regions
  - risk of distortion due to peel forces
- Post-processing (wash + UV post-cure) changes dimensions and properties

## Typical post-processing steps
1. Drain resin
2. Solvent wash (IPA or similar)
3. Support removal
4. UV post-cure (can add shrink/warp risk)
5. Optional sanding/polish/clear coat

## Key "engineering reality"
SLA excels at appearance and detail, but resin parts are typically:
- more brittle than thermoplastics (depending on resin)
- sensitive to UV/heat/chemicals
- less predictable for long-term load-bearing designs (especially thin features)
