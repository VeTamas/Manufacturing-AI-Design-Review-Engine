# CNC: Fixturing and Datum Strategy

Good fixturing reduces setup count, improves accuracy, and lowers scrap risk.

## Datum Selection Principles

- Prefer large, flat, stable surfaces as primary datums
- Avoid datums on thin, flexible, or cosmetic features
- Datums should reflect functional requirements, not convenience

## Fixturing Constraints

- Parts must be rigidly clamped without deformation
- Small contact areas increase vibration and inaccuracy
- Complex geometry often requires custom fixturing

## Design Implications

- Poor datum choice propagates error through all operations
- Lack of clear datums increases setup time and inspection effort
- Fixturing constraints should be considered during CAD design

## Agent Heuristics

- No clear primary datum → MEDIUM to HIGH risk
- Datums on thin features → HIGH risk
- Complex part + no fixturing concept → HIGH risk
