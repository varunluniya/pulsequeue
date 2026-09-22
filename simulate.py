"""
Runs a sample ED waiting-room scenario at the 90-minute mark (the average
wait time this whole design is meant to address) and compares the
static acuity-only queue against PulseQueue's dynamic re-scoring --
showing the specific patient(s) the static queue would silently miss.
"""

from triage_engine import Patient, static_queue, dynamic_queue, find_silent_risers

# A representative ED waiting room, 90 minutes into the shift.
# Mostly realistic mix: a couple of high-acuity patients who just
# arrived, and a cluster of ESI-3 (moderate) patients who have been
# sitting for a while.
PATIENTS = [
    Patient(patient_id="P-01", esi=2, arrival_minute=85),  # high acuity, just arrived
    Patient(patient_id="P-02", esi=2, arrival_minute=80),  # high acuity, just arrived
    Patient(patient_id="P-03", esi=3, arrival_minute=10),  # moderate acuity, waited 80 min
    Patient(patient_id="P-04", esi=3, arrival_minute=45),  # moderate acuity, waited 45 min
    Patient(patient_id="P-05", esi=3, arrival_minute=88),  # moderate acuity, just arrived
    Patient(patient_id="P-06", esi=4, arrival_minute=5),   # low-moderate, waited 85 min
    Patient(patient_id="P-07", esi=5, arrival_minute=20),  # low acuity, waited 70 min
]

CURRENT_TIME = 90  # minutes since simulation start


def describe_patient(p: Patient, current_time: float) -> str:
    elapsed = current_time - p.arrival_minute
    return f"{p.patient_id} (ESI {p.esi}, waited {elapsed:.0f} min)"


def main():
    print("=" * 78)
    print(f"ED waiting room snapshot at t = {CURRENT_TIME} minutes")
    print("=" * 78)
    for p in PATIENTS:
        print(f"  {describe_patient(p, CURRENT_TIME)}")

    print("\n--- STATIC queue (today's status quo: acuity only, never re-scored) ---")
    static = static_queue(PATIENTS)
    for rank, p in enumerate(static, start=1):
        print(f"  {rank}. {describe_patient(p, CURRENT_TIME)}")

    print("\n--- PULSEQUEUE dynamic queue (acuity + elapsed wait, re-scored live) ---")
    dynamic = dynamic_queue(PATIENTS, CURRENT_TIME)
    for rank, s in enumerate(dynamic, start=1):
        flag = "  <-- FLAGGED for re-triage" if s.flagged else ""
        print(
            f"  {rank}. {s.patient.patient_id} (ESI {s.patient.esi}, "
            f"waited {s.elapsed_minutes:.0f} min, risk score {s.dynamic_risk:.1f}){flag}"
        )

    print("\n" + "=" * 78)
    print("SILENT RISERS: patients PulseQueue calls into the top 3, that the")
    print("static acuity-only queue would NOT -- exactly the failure mode this")
    print("system exists to catch.")
    print("=" * 78)
    risers = find_silent_risers(PATIENTS, CURRENT_TIME, watch_size=3)
    if not risers:
        print("  (none in this snapshot)")
    for s in risers:
        static_rank = [p.patient_id for p in static].index(s.patient.patient_id) + 1
        print(
            f"  {s.patient.patient_id}: ESI {s.patient.esi}, waited "
            f"{s.elapsed_minutes:.0f} min, risk {s.dynamic_risk:.1f} -- "
            f"static queue ranks them #{static_rank}, dynamic queue moves "
            f"them into the top 3."
        )
    print(
        "\nThis is the core reframe from the design write-up: rather than a "
        "faster version of the same acuity-only queue, continuously "
        "re-scoring by acuity + elapsed wait catches the specific patients "
        "the clock is quietly endangering -- using data (ESI score, "
        "check-in timestamp) the ED already records, just never "
        "re-analyzes as time passes."
    )


if __name__ == "__main__":
    main()
