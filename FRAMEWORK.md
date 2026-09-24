# PulseQueue — FDE Framework Build Notes

> Decision support only. Every re-triage call is made by a clinician. Vital-sign thresholds are example site defaults to be set by clinical governance.

## Part 1 — Problem Reframing

| Step | Output |
|---|---|
| Ordinary problem | "Reduce ED wait times." |
| Lever 1: Data liquidity | Acuity and check-in time are recorded once and never recombined. Repeat vitals taken in the waiting room are charted but never compared with each other. |
| Lever 2: Network effect | Every re-triage outcome (upgraded or not) grades the flag that triggered it. Across many shifts, the per-ESI growth rates tune to how this department's patients actually deteriorate. |
| Lever 3: Algorithmic leverage | Trajectory scoring: acuity × wait, plus the trend between readings, plus acceleration measured against the patient's own risk history. |
| Lever 4: First principles × JTBD | The charge nurse's job is "don't let anyone get worse unnoticed in my waiting room", not "move the queue faster". |
| Extraordinary problem | **Watch every waiting patient's trajectory, not their intake snapshot**: flag red-flag vitals at once, flag worsening trends before any single reading looks abnormal, and learn from re-triage outcomes under clinical sign-off. |
| Rating | 4 / 5 |

## Part 2 — Design the Eval

**Outcome of intelligence**
- Deteriorating patients are flagged earlier than the clock alone would flag them. Stable patients are not flagged any earlier.
- With no vitals present, the system reproduces v1 exactly (no regression).
- Per-ESI flag precision and missed upgrades are tracked from outcomes (`GET /metrics`).

**EQ(PRE)**
| Angle | Hypothesis |
|---|---|
| Causal | Elapsed time stands in for deterioration. A patient can deteriorate in 15 minutes or be stable for 2 hours. |
| Context | Vitals are taken but not read by the ordering. |
| Consistency | Fixed growth rates flag too early for some ESI levels and too late for others. |

**EQ(POST), cheapest first**
1. Prompt: the handoff summary may only restate computed reasons. The offline template is the floor.
2. Context/retrieval: red flags, trends, department load, and the protocol cited per flag.
3. Feedback: outcomes → per-ESI precision and misses → growth-rate proposals → clinical-lead approval.

**Executable:** `python run_evals.py` runs 6 behavioural cases × 3 runs (v1 parity, red flag, trend, no over-flag, governance).

## Part 3 — Gen-4 Architecture

| Layer | What PulseQueue does |
|---|---|
| Retrieval | `knowledge/retriage_protocol.md` (site configuration). The sections behind the current flags (red flags, trends, acceleration, load) are cited on every queue read. |
| Context | Waiting count, arrivals in the last 60 minutes, and the resulting re-check interval (15 or 30 minutes). Latest vitals per patient. |
| Memory | Patient state: arrival, all vitals readings, and a 2-hour risk history used for acceleration. Flag decisions are linked to outcomes. |
| Feedback | `POST /patients/{id}/outcome` feeds per-ESI flag precision and missed upgrades. Growth-rate proposals go to `/proposals`, and a clinical lead approves them. |

The model writes the charge-nurse handoff summary from the computed reasons. A deterministic template is used offline.

## Part 4 — Implementation Plan

| Component | Priority | Estimate | Status |
|---|---|---|---|
| Stateful waiting room (arrive, vitals, seen) in memory | MVP | 0.5 day | done |
| Red flags + trend rules + trend bonus | MVP | 0.5 day | done |
| Acceleration from risk history | MVP | 0.25 day | done |
| Load-aware context + protocol citations | MVP | 0.25 day | done |
| Outcome feedback, precision/miss metrics, governed proposals | MVP | 0.5 day | done |
| API, Docker, CI | MVP | 0.5 day | done |
| HL7/FHIR feed from the ED tracking board | future | 3–5 days | future |
| Wall display / nurse tablet UI | nice-to-have | 2 days | future |
| Calibrated deterioration model trained on local outcomes | future | 2+ weeks | future |

## Part 5 — Prove It

**Visible change** (`python compare_v1_v2.py`, output in `run_output_v1_vs_v2.txt`): minute at which each patient is first flagged over a 120-minute window.

| Patient | ESI | Deteriorating? | v1 flags at | v2 flags at | Why v2 flagged |
|---|---|---|---|---|---|
| A | 3 | yes | 37 min | **20 min** | HR 84→106, SBP 128→106: trend while both readings look normal |
| B | 4 | yes | 91 min | **25 min** | SpO₂ 96→91: red flag + trend |
| C | 3 | no | 37 | 37 | clock only, same as v1 |
| D | 4 | no | 101 | 101 | same as v1 |
| E | 2 | no | 47 | 47 | same as v1 |
| F | 5 | no | — | — | — |

The two deteriorating patients are flagged **17 and 66 minutes earlier**. The four stable patients are flagged exactly as before, so there is no alarm inflation.
