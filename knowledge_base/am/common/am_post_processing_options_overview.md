# AM: Post-Processing Options and Design Implications

Post-processing often determines whether an AM part is production-ready.

## Typical Post-Processing Categories

- Surface finishing (e.g., blasting, sanding, polishing)
- Machining for precision features
- Heat treatment (especially metal AM)
- Support removal
- Inspection and documentation

## Design Implications

- Critical surfaces should be accessible for finishing/machining
- Cosmetic surfaces should avoid heavy support contact
- Internal features can become inaccessible for finishing or inspection

## Agent Heuristics

- Critical surface not accessible for post-processing → HIGH risk
- Cosmetic requirement on support-contact surface → MEDIUM to HIGH risk
- Internal channels needing finish without access → HIGH risk