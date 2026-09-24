# PulseQueue

_A live emergency-department waiting-room monitor. It watches each patient's trajectory (acuity × wait, vital-sign red flags, worsening trends, acceleration) and learns from re-triage outcomes under clinical sign-off._

[![ci](https://github.com/varunluniya/pulsequeue/actions/workflows/ci.yml/badge.svg)](https://github.com/varunluniya/pulsequeue/actions/workflows/ci.yml)

> Decision support only. A clinician makes every re-triage call. Vital-sign thresholds in `knowledge/retriage_protocol.md` are example site defaults for clinical governance to set.

## What's new in v2: an intelligent, deployable service

| Layer | In PulseQueue |
|---|---|
| **Retrieval** | Site re-triage protocol. The rule behind every flag is cited |
| **Context** | Department load (waiting, arrivals per hour) → re-check interval. Latest vitals |
| **Memory** | Each patient's arrival, vitals readings, and 2-hour risk history |
| **Feedback** | Re-triage outcomes → per-ESI flag precision and misses → growth-rate proposals a clinical lead approves |

| Minutes until flagged | v1 (acuity × wait) | v2 |
|---|---|---|
| ESI 3, HR 84→106 and SBP 128→106 (each reading "normal") | 37 | **20** |
| ESI 4, SpO₂ 96→91 | 91 | **25** |
| Four stable patients | unchanged | unchanged (no alarm inflation) |

With no vitals entered, v2 reproduces v1's ordering and silent risers exactly (checked in the eval gate). Full framework write-up: [FRAMEWORK.md](FRAMEWORK.md).

## Run it

```bash
pip install -r requirements-dev.txt
uvicorn app:app --reload        # http://127.0.0.1:8000/docs
python -m pytest -q             # original 11 engine tests + service/API tests
python run_evals.py             # behavioural eval gate
python compare_v1_v2.py         # before/after proof
```

Docker: `docker build -t pulsequeue . && docker run -p 8000:8000 -v pulsequeue-data:/data pulsequeue` · Render: `render.yaml`.

```bash
curl -X POST localhost:8000/patients -H 'content-type: application/json' -d '{"patient_id":"P-11","esi":3}'
curl -X POST localhost:8000/patients/P-11/vitals -H 'content-type: application/json' -d '{"hr":104,"sbp":102,"spo2":95}'
curl localhost:8000/queue
```

| Endpoint | Purpose |
|---|---|
| `POST /patients` · `POST /patients/{id}/vitals` · `POST /patients/{id}/seen` | Waiting-room events |
| `GET /queue` | Ranked queue: risk, red flags, trends, accelerating, silent risers, static rank, handoff summary, trace |
| `POST /patients/{id}/outcome` · `GET /metrics` | Was re-triage an upgrade? Per-ESI precision and misses |
| `GET /proposals` · `POST /proposals/{param}/approve` | Clinical-lead approval of learned growth rates |

---

## The original engine (v1)

The v1 demo still runs unchanged; the service wraps it.

A dynamic re-scoring engine for emergency department waiting rooms.

### The problem

Emergency departments triage every patient on arrival with an acuity
score (ESI, 1–5) and then work the waiting room in acuity order. That
score is recorded once, at check-in, and never revisited — no matter
how long a patient then sits waiting. A moderate-acuity patient who has
been waiting two hours and a same-acuity patient who just walked in
look identical to that ordering. In practice, that gap is where risk
hides: the person quietly getting worse in the corner of the waiting
room, not the person a doctor already knows is sick.

The result, industry-wide, is a meaningful share of patients who leave
without being seen (LWBS) — driven less by total department capacity
than by exactly this blind spot: nobody is watching *how the risk of
already-triaged patients changes while they wait*.

### What PulseQueue does

PulseQueue continuously re-scores every patient still in the queue by
combining their original acuity with elapsed wait time, and flags
anyone whose risk has climbed enough to warrant being pulled forward
and re-triaged — before a doctor would otherwise reach them under the
static, acuity-only ordering. It doesn't replace the ESI score or add a
new sensor to the department; it uses two data points every ED already
records (acuity, check-in timestamp) and simply keeps recalculating
with them as time passes, instead of treating them as a one-time
snapshot.

Two data structures, one comparison:

- **Static queue** — what every ED already runs today: sort by acuity,
  break ties by arrival order, never touch it again.
- **Dynamic queue (PulseQueue)** — re-score every patient's risk live,
  as a function of acuity *and* how long they've been waiting, and
  re-sort continuously.

The engine then surfaces **silent risers**: patients the dynamic queue
would call into the front of the line that the static queue would
leave sitting further back — the specific failure mode this design
exists to catch.

### Running it

```bash
pip install pytest   # only needed to run the test suite
python3 simulate.py           # run the bundled sample scenario, narrated
python3 cli.py                # same scenario, compact queue-vs-queue view
python3 cli.py --time 120     # re-run the comparison at a different clock time
python3 -m pytest -v          # 11 tests, all passing
```

Sample output from `simulate.py` is captured in `run_output.txt` in this
repo — a moderate-acuity patient who has been waiting 80 minutes is
correctly promoted to the #1 slot by the dynamic queue, well above two
higher-acuity patients who simply arrived more recently, and two
patients the static queue ranks 4th and 6th are surfaced as silent
risers the acuity-only ordering would have missed.

### A real bug found and fixed while building this

The first version of `cli.py`'s `--time` flag let you point the
simulation at any clock time, including one earlier than some sample
patients' arrival minute. Running `python3 cli.py --time 60` didn't
just produce a wrong answer — it printed patients with a *negative*
wait time in the static-queue view, then crashed with an unhandled
traceback in the dynamic engine, which correctly rejects a `current_time`
before a patient's arrival. The fix was to validate `--time` against
the scenario's latest patient arrival up front and fail with a clear,
actionable message instead of a stack trace. Caught by actually running
the CLI with a boundary input, not by reading the code.

### Files

- `triage_engine.py` — the core engine: `Patient`, the dynamic risk
  formula, the static and dynamic queue builders, and silent-riser
  detection.
- `simulate.py` — a narrated sample scenario (7 patients, t = 90
  minutes) comparing both queues.
- `cli.py` — a small command-line wrapper around the same scenario,
  parameterized by clock time.
- `test_triage_engine.py` — 11 pytest tests covering the risk formula,
  input validation, the re-triage threshold boundary, and the
  silent-riser detection logic (including a case where it should
  correctly find nothing).
- `run_output.txt` — captured real output from `simulate.py`.

### Design note

This project started as a design exercise: reframe "reduce ED wait
time" away from a generic speed target and toward the specific,
measurable risk of patients whose condition is worsening unnoticed
while they wait. The reframing rests on three things: naming the real
payer and cost driver (administratively, this is a leakage problem —
lost revenue and penalty exposure from patients who leave without being
seen, not just a satisfaction metric), identifying data that already
exists but is never re-combined after intake (acuity score + live wait
time), and separating the *stated* ask ("faster queue") from the
*actual* one ("don't let anyone's risk climb unnoticed"). PulseQueue is
the working version of that reframing — not a queue that moves faster
for everyone, but one that watches for the specific patients the clock
is quietly endangering.
