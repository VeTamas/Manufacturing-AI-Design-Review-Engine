# AM: Minimum Features and Geometric Limits

Across additive manufacturing technologies, minimum feature sizes
strongly influence print success, accuracy, and reliability.

## Walls

- Supported walls can be thinner than unsupported walls
- Tall, thin walls increase vibration and distortion risk
- Aspect ratio matters more than absolute thickness

## Pins and Columns

- Small diameter pins are prone to snapping
- Taller pins amplify layer anisotropy effects
- Load direction relative to layers is critical

## Embossed and Engraved Details

- Very small text or logos lose definition
- Engraving prints more reliably than embossing
- Depth matters more than line width

## Agent Heuristics

- High aspect ratio thin walls → HIGH risk
- Tall pins loaded parallel to layers → HIGH risk
- Decorative micro-features on functional parts → MEDIUM risk
