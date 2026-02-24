# Injection Molding: Shrinkage and Warpage

All thermoplastics shrink; the amount depends on material,
fiber content, wall thickness, and cooling rate.

## Key Facts

- Semi-crystalline plastics (e.g. Nylon, POM) shrink more
- Glass-filled materials shrink anisotropically
- Thick sections shrink more than thin ones

## Design Implications

- Dimensions are not equal in mold vs final part
- Warpage is driven by uneven shrinkage

## Agent Heuristics

- Tight tolerances without shrinkage discussion → HIGH risk
- Glass-filled material + asymmetric geometry → HIGH risk
- Large flat surfaces without ribs → HIGH risk

## Design Notes

- Shrinkage values vary significantly by material family; amorphous materials typically shrink less than semi-crystalline materials
- Glass-filled materials exhibit anisotropic shrinkage, shrinking less in flow direction but more perpendicular, causing dimensional variation
- Warpage is driven by differential shrinkage; thick-to-thin transitions and asymmetric geometry amplify risk
- Some materials like Nylon continue to shrink after molding due to moisture absorption, requiring additional dimensional allowance
