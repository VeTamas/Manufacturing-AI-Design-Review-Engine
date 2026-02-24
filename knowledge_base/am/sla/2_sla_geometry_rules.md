# SLA — Geometry & Design Rules

## Wall thickness
Guideline ranges vary by resin and printer, but practical design rules:

- **Supported walls:** prefer ≥ 0.5 mm (thin walls can print, but distort risk rises)
- **Unsupported walls:** prefer ≥ 0.8–1.0 mm
- **Large flat walls:** increase thickness or add ribs to reduce warping

### Why this matters
- Peel forces during layer separation can flex thin features
- Post-cure can introduce additional shrink/warp

## Ribs / stiffeners
- Prefer ribs over simply thickening large flat areas
- Fillet rib roots to reduce stress concentration and print artifacts

## Holes, pins, and thin posts
- **Small holes** can close partially due to curing + resin drainage issues
- Prefer:
  - oversize holes and ream/drill after
  - add chamfer entry to reduce support scarring
- Thin posts/pins are fragile: increase diameter or add temporary "break-away" braces

## Overhangs & bridges
SLA can "print" overhangs but quality drops quickly:

- **Down-facing surfaces** (surfaces facing the vat) tend to be rougher
- Flat/near-horizontal down-facing regions need supports and often show marks

**Practical rule:**
- Avoid large flat down-facing faces; orient them upward if surface quality matters
- Convert horizontal overhangs into angled/chamfered geometry

## Engraving / embossing
- Embossed text is usually cleaner than engraved (depends on orientation)
- Prefer stroke widths that survive sanding and support removal

## Sharp corners & stress
- Prefer fillets instead of sharp internal corners
- Resin parts are notch-sensitive: sharp corners crack easier
