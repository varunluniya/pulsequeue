"""
Incremental-loading fix: learn() used to re-pull and re-group every decision+outcome
pair into per-ESI stats on every call. These tests prove the incremental
replacement accumulates correctly across repeated calls and never
double-counts already-processed rows.
"""
from gen4 import Memory
from service import SYSTEM, PulseQueueService


def _flagged_decision(mem, pid, esi, upgraded):
    did = mem.record_decision(SYSTEM, pid, {"esi": esi}, {"flagged": True})
    mem.record_outcome(did, {"upgraded": upgraded, "waited_min": 30})
    return did


def test_learn_accumulates_per_esi_across_calls_without_double_counting():
    svc = PulseQueueService(memory=Memory())
    for i in range(5):
        _flagged_decision(svc.memory, f"p-{i}", esi=3, upgraded=(i % 2 == 0))
    first = svc.learn()
    assert first["per_esi"][3]["flagged"] == 5

    second = svc.learn()  # nothing new -- must be a no-op
    assert second["per_esi"][3]["flagged"] == 5

    for i in range(5, 8):
        _flagged_decision(svc.memory, f"p-{i}", esi=3, upgraded=True)
    third = svc.learn()
    assert third["per_esi"][3]["flagged"] == 8
