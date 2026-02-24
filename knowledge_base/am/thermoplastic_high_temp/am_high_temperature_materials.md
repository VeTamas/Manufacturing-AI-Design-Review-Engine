# High-Temperature Thermoplastic AM: Material Constraints

High-temperature thermoplastics introduce additional constraints compared to standard FFF materials.

## Glass Transition Temperature (Tg) Awareness

- Printing near or above Tg reduces warping and residual stress
- Parts printed far below Tg show poor interlayer adhesion
- High Tg materials require active thermal management

## Material Handling Challenges

- High-temperature polymers are sensitive to thermal gradients
- Inadequate temperature control leads to delamination
- Material degradation occurs if residence time at high temperature is excessive

## Functional Implications

- Improved high-temperature performance often trades off printability
- Mechanical properties depend strongly on process stability
- Inconsistent temperature profiles cause internal defects

## Agent Heuristics

- High-temp material without Tg control strategy → HIGH risk
- Functional thermal load + unknown material Tg → HIGH risk
- Material selection driven only by strength claims → MEDIUM risk
