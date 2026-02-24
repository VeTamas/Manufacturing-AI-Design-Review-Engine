# Sheet Metal: Bend Reliefs and Corner Design

Bend reliefs prevent tearing and distortion during forming.

## Purpose of Bend Reliefs

- Allow material to deform locally during bending
- Prevent cracking at bend intersections
- Reduce unintended deformation

## Corner Conditions

- Adjacent bends require reliefs
- Sharp internal corners amplify stress
- Relief geometry must exceed tooling limits

## Design Implications

- Missing reliefs cause unpredictable deformation
- Overly small reliefs behave like no relief
- Corner geometry affects both strength and appearance

## Agent Heuristics

- Adjacent bends without relief → HIGH risk
- Sharp internal corners at bends → HIGH risk
- Relief geometry undefined → MEDIUM risk
