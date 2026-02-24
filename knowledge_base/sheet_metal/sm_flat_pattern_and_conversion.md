# Sheet Metal: Flat Pattern and Solid-to-Sheet Conversion

Sheet metal parts must be manufacturable as flat patterns before forming.

## Flat Pattern Awareness

- Every sheet metal part originates as a flat blank
- Geometry must allow clean unfolding
- Closed shapes require rips or seams

## Solid-to-Sheet Conversion

- Uniform material thickness is mandatory
- Conversion tools rely on consistent wall thickness
- Non-uniform solids often fail to unfold correctly

## Design Implications

- Designs that only work in 3D may be impossible to fabricate
- Rips and seams must be planned, not accidental
- Conversion failures often indicate deeper design issues

## Agent Heuristics

- Non-uniform thickness solid → HIGH risk
- Flat pattern not considered → HIGH risk
- Rips/seams missing in closed geometry → HIGH risk
