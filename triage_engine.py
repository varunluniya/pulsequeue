"""
PulseQueue — dynamic emergency-department triage re-scoring engine.

The standard way an ED orders its waiting room is static: assign an
acuity score (ESI 1 = most urgent, 5 = least urgent) at intake, then see
patients in acuity order (ties broken by arrival time). That score is
never revisited. PulseQueue's premise is simple: acuity alone answers
"how sick is this person right now," but it says nothing about "how much
worse could this person get while they keep waiting." A moderate-acuity
patient who has been sitting for two hours is not the same risk as one
who has been sitting for ten minutes, even though their intake score is
identical.

PulseQueue continuously re-scores every patient still in the waiting
room by combining their initial acuity with elapsed wait time, so a
patient whose risk is silently climbing gets pulled forward before a
doctor would otherwise reach them under a static, acuity-only queue.
"""

from dataclasses import dataclass


# Higher-acuity patients (lower ESI number) are assumed to deteriorate
# faster per minute of untreated waiting than lower-acuity patients --
# an ESI-1 patient left waiting is a very different situation than an
# ESI-4 patient left waiting the same amount of time.
RISK_PER_MINUTE_BY_URGENCY = {
    5: 2.6,  # ESI 1 (most urgent): urgency weight 5
    4: 1.8,  # ESI 2
    3: 1.1,  # ESI 3
    2: 0.55,  # ESI 4
    1: 0.25,  # ESI 5 (least urgent): urgency weight 1
}

BASE_RISK_PER_URGENCY_POINT = 10.0

# A patient is flagged for re-triage once their dynamic risk score
# crosses this threshold -- regardless of what their static acuity rank
# would otherwise imply.
RE_TRIAGE_RISK_THRESHOLD = 70.0


@dataclass
class Patient:
    patient_id: str
    esi: int  # Emergency Severity Index, 1 (most urgent) to 5 (least urgent)
    arrival_minute: float  # minute, relative to simulation start, the patient checked in

    def __post_init__(self):
        if not 1 <= self.esi <= 5:
            raise ValueError(f"ESI must be 1-5, got {self.esi}")
        if self.arrival_minute < 0:
            raise ValueError("arrival_minute cannot be negative")

    @property
    def urgency(self) -> int:
        """Higher urgency number = more urgent. ESI 1 -> urgency 5."""
        return 6 - self.esi


@dataclass
class ScoredPatient:
    patient: Patient
    elapsed_minutes: float
    dynamic_risk: float
    flagged: bool


def elapsed_minutes(patient: Patient, current_time: float) -> float:
    elapsed = current_time - patient.arrival_minute
    if elapsed < 0:
        raise ValueError(
            f"current_time ({current_time}) is before patient "
            f"{patient.patient_id}'s arrival ({patient.arrival_minute})"
        )
    return elapsed


def dynamic_risk_score(patient: Patient, current_time: float) -> float:
    """The core re-scoring formula: base acuity risk, plus a per-minute
    growth term that grows faster for higher-urgency patients. This is
    what lets a moderate-acuity patient who has waited a long time
    overtake a higher-acuity patient who just arrived."""
    elapsed = elapsed_minutes(patient, current_time)
    base = patient.urgency * BASE_RISK_PER_URGENCY_POINT
    growth = RISK_PER_MINUTE_BY_URGENCY[patient.urgency] * elapsed
    return base + growth


def score_patient(patient: Patient, current_time: float) -> ScoredPatient:
    risk = dynamic_risk_score(patient, current_time)
    return ScoredPatient(
        patient=patient,
        elapsed_minutes=elapsed_minutes(patient, current_time),
        dynamic_risk=risk,
        flagged=risk >= RE_TRIAGE_RISK_THRESHOLD,
    )


def dynamic_queue(patients: list[Patient], current_time: float) -> list[ScoredPatient]:
    """The PulseQueue ordering: continuously re-scored, highest risk first."""
    scored = [score_patient(p, current_time) for p in patients]
    return sorted(scored, key=lambda s: s.dynamic_risk, reverse=True)


def static_queue(patients: list[Patient]) -> list[Patient]:
    """The status-quo ordering every ED already uses: acuity first
    (lower ESI = seen sooner), ties broken by who arrived first. This
    never changes as time passes -- it's exactly the "recorded once,
    never re-analyzed" gap PulseQueue is built to close."""
    return sorted(patients, key=lambda p: (p.esi, p.arrival_minute))


def find_silent_risers(patients: list[Patient], current_time: float, watch_size: int = 3):
    """Patients the dynamic queue would call forward into the top
    `watch_size` slots, that the static queue would NOT -- the exact
    failure mode PulseQueue exists to catch: a patient whose risk has
    climbed past people who look more urgent on paper but have only
    just arrived."""
    dynamic_top_ids = {s.patient.patient_id for s in dynamic_queue(patients, current_time)[:watch_size]}
    static_top_ids = {p.patient_id for p in static_queue(patients)[:watch_size]}
    silent_riser_ids = dynamic_top_ids - static_top_ids
    scored_by_id = {s.patient.patient_id: s for s in dynamic_queue(patients, current_time)}
    return [scored_by_id[pid] for pid in silent_riser_ids]
