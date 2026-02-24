# CNC Design Review + DFM Report

## Input summary

- Manufacturing process: AM

- Material: Steel
- Production volume: Proto
- Load type: Static
- Tolerance criticality: Medium

- Part size: Small
- Min internal radius: Small
- Min wall thickness: Medium
- Hole depth class: None
- Pocket aspect class: OK
- Feature variety: High
- Accessibility risk: High
- Has clamping faces: True


## Process recommendation

- Primary: **AM**

- Secondary: CNC

- Less suitable (given current inputs): SHEET_METAL, CASTING, FORGING, EXTRUSION, MIM

- Not applicable (hard gated): INJECTION_MOLDING (polymer process), THERMOFORMING (polymer process), COMPRESSION_MOLDING (polymer process)

- Tradeoffs:

  - Tooling lead time vs unit cost: IM/Sheet metal need tooling; CNC/AM suit low volume.

  - Tolerance and finish: Define critical interfaces; plan post-machining or inspection where needed.

  - Risk drivers: Warpage (IM/AM), supports (AM), setups (CNC/Sheet metal) affect feasibility.

  - Volume sensitivity: IM and sheet metal favor production runs; CNC/AM suit proto and small batch.

  - Documentation: 2D drawing and scale confirmation improve tolerance and process selection.



## Manufacturing confidence inputs

- CAD uploaded: yes

- CAD analysis status: none

- CAD evidence used in rules: no

- CAD Lite analysis: failed

- Extrusion Lite analysis: failed

- Extrusion likelihood: none (source=none)

- Sheet metal likelihood: low (source=none)

_Confidence inputs not provided._



## Top priorities

- [HIGH] Support structures required (metal LPBF) (LPBF1)

- [HIGH] Support or bridging (geometry) (AM2)

- [MEDIUM] Powder removal access (metal LPBF) (LPBF10)



## Findings (HIGH)

- **Support structures required (metal LPBF)** (LPBF1) — Metal LPBF requires supports for overhangs; supports add cost, time, and post-processing.
  - Recommendation: Design self-supporting geometry; minimize overhangs <45°; ensure support removal access; plan for EDM/saw removal.
- **Support or bridging (geometry)** (AM2) — Supports add material, time, and post-processing; bridging can sag. Poor removal access increases risk.
  - Recommendation: Design self-supporting where possible; limit support contact area. Ensure removal access for supports.
- **Low volume + MIM (tooling ROI risk)** (MIM1) — MIM has high upfront tooling cost; unit cost only becomes favorable at production volumes.
  - Recommendation: Consider CNC or AM for low volumes; MIM best for stable designs at production scale.

## Findings (MEDIUM)

- **Powder removal access (metal LPBF)** (LPBF10) — Trapped powder must be removed; poor access increases cleaning time and risk.
  - Recommendation: Design for powder removal access; add drain holes; plan cleaning procedures.
- **High feature variety (print time)** (AM8) — Many distinct features increase print time and failure risk.
  - Recommendation: Consolidate geometry where possible; use consistent wall thicknesses.
- **Low volume + casting (tooling risk)** (CAST1) — Casting has significant tooling cost; economics favor production runs.
  - Recommendation: Consider CNC or AM for low volumes; casting best at production scale.
- **Low volume + forging (tooling risk)** (FORG1) — Forging has significant die cost; economics favor production runs.
  - Recommendation: Consider CNC or AM for low volumes; forging best at production scale.

## Findings (LOW)

_None_

## Action Checklist

- [ ] Address HIGH and MEDIUM findings before release.
- [ ] Apply recommended design changes for critical features.
- [ ] Re-verify tolerances and interfaces after changes.

## Assumptions

- Inputs and part summary reflect current design intent.
- Manufacturing process and material choices are as specified.

## Usage (tokens & cost)

_Usage not available._


## LLM usage by node

_Not available._


## Agent confidence & limitations

_Not available._
