import pytest

from gen4 import KnowledgeBase, LLMClient, Memory
from service import PulseQueueService


@pytest.fixture
def svc():
    return PulseQueueService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def test_duplicate_and_invalid_arrivals_rejected(svc):
    svc.arrive("p", 3, at=0)
    with pytest.raises(ValueError):
        svc.arrive("p", 3, at=1)
    with pytest.raises(ValueError):
        svc.arrive("q", 7, at=0)


def test_now_before_arrival_is_an_error(svc):
    svc.arrive("p", 3, at=50)
    with pytest.raises(ValueError):
        svc.queue(now=10)


def test_seen_patients_leave_the_queue(svc):
    svc.arrive("p", 3, at=0)
    svc.seen("p", at=5)
    assert svc.queue(now=10)["queue"] == []


def test_red_flag_is_cited_and_in_handoff(svc):
    svc.arrive("p", 4, at=0)
    svc.add_vitals("p", {"sbp": 84}, at=1)
    out = svc.queue(now=2)
    assert out["queue"][0]["flagged"]
    assert any("red flags" in c["heading"].lower() for c in out["trace"]["retrieval"])
    assert "sbp 84 < 90" in out["handoff_summary"]


def test_accelerating_patient_detected_from_risk_history(svc):
    svc.arrive("p", 3, at=0)
    svc.add_vitals("p", {"hr": 80, "sbp": 130}, at=1)
    svc.queue(now=5)
    svc.add_vitals("p", {"hr": 110, "sbp": 105}, at=12)
    s = svc.queue(now=12)["queue"][0]
    assert s["accelerating"] and s["flagged"]


def test_high_load_tightens_recheck_interval(svc):
    for k in range(16):
        svc.arrive(f"p{k}", 5, at=0)
    assert svc.queue(now=1)["trace"]["context"]["recheck_interval_min"]["value"] == 15


def test_low_precision_flags_propose_slower_growth_after_approval_only(svc):
    for k in range(10):
        svc.arrive(f"p{k}", 2, at=0)
    svc.queue(now=60)                     # all ESI-2 patients flagged by time
    for k in range(10):
        svc.outcome(f"p{k}", upgraded=False)
    props = svc.learn()["new_proposals"]
    assert props and props[0]["proposed"] < props[0]["current"]
    from gen4 import feedback as fb
    fb.approve(svc.memory, "growth:esi2", "clinical-lead")
    assert svc.growth(2) == props[0]["proposed"]
