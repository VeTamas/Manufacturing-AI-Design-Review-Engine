# AM: Tolerances and Fit Expectations

Additive manufacturing processes have inherent variability
that limits achievable tolerances.

## General Tolerance Reality

- AM tolerances are looser than CNC machining
- Repeatability varies by process and machine
- Shrinkage and distortion are process-dependent

## Fits and Assemblies

- Press fits are unreliable as-printed
- Clearance must be designed generously
- Post-machining improves fit reliability

## Design Recommendations

- Avoid tight tolerance chains in AM-only assemblies
- Design adjustment features where possible
- Validate fits with test prints

## Agent Heuristics

- Tight fit specified without post-processing → HIGH risk
- Multi-part assembly relying on as-printed tolerances → HIGH risk
- No tolerance discussion for mating parts → MEDIUM risk
