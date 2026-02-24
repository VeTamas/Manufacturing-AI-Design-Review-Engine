# FDM: Part Splitting and Orientation Strategies

Splitting parts can significantly improve both mechanical and visual quality in FDM.

## Benefits of Part Splitting

- Reduced support material
- Improved surface finish on critical areas
- Better layer orientation for strength

## Assembly Considerations

- Split surfaces should be accessible and flat
- Alignment features (pins, tabs) improve assembly accuracy
- Adhesive bonding strength often exceeds layer strength

## Orientation Trade-Offs

- Optimal print orientation may conflict with assembly simplicity
- Large flat bases reduce warping but increase Z-anisotropy
- Orientation decisions should prioritize functional loads

## Agent Heuristics

- Single-piece design causing heavy supports → MEDIUM risk
- No alignment features on split parts → MEDIUM risk
- Load path ignored in orientation → HIGH risk
