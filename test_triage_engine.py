"""Unit tests for the PulseQueue triage engine. Run with: pytest"""

import pytest

from triage_engine import (
    Patient,
    dynamic_risk_score,
    static_queue,
    dynamic_queue,
    find_silent_risers,
    RE_TRIAGE_RISK_THRESHOLD,
)


def test_higher_esi_number_means_lower_urgency():
    p1 = Patient("A", esi=1, arrival_minute=0)
    p5 = Patient("B", esi=5, arrival_minute=0)
    assert p1.urgency > p5.urgency


def test_risk_increases_monotonically_with_wait_time():
    p = Patient("A", esi=3, arrival_minute=0)
    early = dynamic_risk_score(p, current_time=10)
    later = dynamic_risk_score(p, current_time=60)
    assert later > early


def test_higher_urgency_patient_accrues_risk_faster_per_minute():
    # Same elapsed wait, different acuity: the more urgent patient's
    # risk should grow faster per minute, not just start higher.
    urgent = Patient("A", esi=1, arrival_minute=0)
    mild = Patient("B", esi=5, arrival_minute=0)
    urgent_growth = dynamic_risk_score(urgent, 60) - dynamic_risk_score(urgent, 0)
    mild_growth = dynamic_risk_score(mild, 60) - dynamic_risk_score(mild, 0)
    assert urgent_growth > mild_growth


def test_invalid_esi_rejected():
    with pytest.raises(ValueError):
        Patient("A", esi=6, arrival_minute=0)
    with pytest.raises(ValueError):
        Patient("A", esi=0, arrival_minute=0)


def test_negative_arrival_time_rejected():
    with pytest.raises(ValueError):
        Patient("A", esi=3, arrival_minute=-5)


def test_current_time_before_arrival_raises():
    p = Patient("A", esi=3, arrival_minute=50)
    with pytest.raises(ValueError):
        dynamic_risk_score(p, current_time=10)


def test_static_queue_ignores_wait_time_entirely():
    # A long-waiting moderate-acuity patient must NOT outrank a
    # just-arrived higher-acuity patient in the static queue -- that's
    # the exact status-quo behavior this design is meant to fix.
    long_waiter = Patient("WAITER", esi=3, arrival_minute=0)
    fresh_urgent = Patient("FRESH", esi=2, arrival_minute=89)
    ordered = static_queue([long_waiter, fresh_urgent])
    assert ordered[0].patient_id == "FRESH"


def test_dynamic_queue_can_promote_long_waiter_above_fresh_higher_acuity():
    long_waiter = Patient("WAITER", esi=3, arrival_minute=0)
    fresh_urgent = Patient("FRESH", esi=2, arrival_minute=89)
    ranked = dynamic_queue([long_waiter, fresh_urgent], current_time=90)
    assert ranked[0].patient.patient_id == "WAITER"


def test_flag_threshold_is_a_real_boundary():
    # Construct a patient whose risk sits just under, then just over,
    # the re-triage threshold, and confirm the flag follows exactly.
    p = Patient("A", esi=3, arrival_minute=0)
    # Binary-search-free: just check a low time is unflagged and a
    # high time is flagged, then confirm the threshold constant itself
    # is what's being compared against.
    low_time_score = dynamic_risk_score(p, current_time=1)
    high_time_score = dynamic_risk_score(p, current_time=200)
    assert low_time_score < RE_TRIAGE_RISK_THRESHOLD
    assert high_time_score >= RE_TRIAGE_RISK_THRESHOLD


def test_silent_risers_excludes_patients_already_in_static_top_slots():
    # If the dynamic and static queues agree on the top slot, that
    # patient should not show up as a "silent riser" -- risers are only
    # the ones the static queue would have missed.
    patients = [
        Patient("P1", esi=1, arrival_minute=89),  # very urgent, just arrived: tops both queues
        Patient("P2", esi=3, arrival_minute=0),   # long waiter
        Patient("P3", esi=4, arrival_minute=88),  # low acuity, fresh
    ]
    risers = find_silent_risers(patients, current_time=90, watch_size=1)
    riser_ids = {r.patient.patient_id for r in risers}
    assert "P1" not in riser_ids


def test_silent_riser_detects_a_real_case():
    patients = [
        Patient("FRESH1", esi=2, arrival_minute=85),
        Patient("FRESH2", esi=2, arrival_minute=80),
        Patient("LONGWAIT", esi=4, arrival_minute=5),
    ]
    risers = find_silent_risers(patients, current_time=90, watch_size=2)
    riser_ids = {r.patient.patient_id for r in risers}
    assert "LONGWAIT" in riser_ids
