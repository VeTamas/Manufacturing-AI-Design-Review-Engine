# Metal AM: Tolerances and Surface Finish Reality

As-built metal AM parts rarely meet tight tolerance or surface finish requirements.

## Dimensional Accuracy

- As-built tolerances are looser than CNC machining
- Orientation and support strategy affect accuracy
- Thin features distort more easily

## Surface Finish Limitations

- Powder bed processes produce rough surfaces
- Downward-facing surfaces are typically worst
- Cosmetic surfaces usually require finishing

## Design Recommendations

- Avoid relying on as-built critical dimensions
- Provide machining allowance for precision features
- Separate cosmetic and functional requirements

## Agent Heuristics

- Tight tolerances without machining allowance → HIGH risk
- Cosmetic requirement on as-built surface → MEDIUM to HIGH risk
- Precision fit relying on unsupported surfaces → HIGH risk
