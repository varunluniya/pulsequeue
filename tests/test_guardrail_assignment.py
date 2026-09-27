"""
Guide 4 Assignment 2 ("RAG with Guardrails") applied to PulseQueue's own
charge-nurse handoff generator: one query that passes cleanly, one that
fires the guardrail, and one genuine edge case.
"""
import pytest

from gen4 import KnowledgeBase, LLMClient, Memory
from service import PulseQueueService


@pytest.fixture
def svc():
    return PulseQueueService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def _scored(*, accelerating_p1=False):
    return [
        {"patient_id": "p1", "esi": 3, "flagged": True, "accelerating": accelerating_p1,
         "waited_min": 40, "reasons": ["rising risk"]},
        {"patient_id": "p2", "esi": 2, "flagged": False, "accelerating": False,
         "waited_min": 10, "reasons": []},
    ]


def test_passing_query_handoff_mentions_every_accelerating_patient(svc):
    scored = _scored(accelerating_p1=True)
    draft = "2 waiting, 1 flagged for re-triage:\n- p1 ESI 3, 40 min (ACCELERATING): rising risk"
    out = svc._guarded(draft, scored, draft, passages=[])
    assert out == draft
    assert "guardrail replaced" not in out


def test_guardrail_fires_when_draft_drops_an_accelerating_patient(svc):
    """The one failure this system exists to catch: a flagged, accelerating
    patient silently missing from the note a nurse actually reads."""
    scored = _scored(accelerating_p1=True)
    bad_draft = "2 waiting; queue looks stable, no urgent re-triage needed right now."
    fallback = "2 waiting, 1 flagged for re-triage:\n- p1 ESI 3, 40 min (ACCELERATING): rising risk"
    out = svc._guarded(bad_draft, scored, fallback, passages=[])
    assert out != bad_draft
    assert "guardrail replaced" in out
    assert "p1" in out


def test_edge_case_flagged_but_not_accelerating_is_not_required_by_name(svc):
    """Genuine edge case: p1 is flagged but NOT accelerating here, so a terse
    draft that doesn't name p1 individually is still acceptable -- the guardrail
    should not be so strict it fires on every omission, only on the dangerous one
    (a flagged AND accelerating patient going unmentioned)."""
    scored = _scored(accelerating_p1=False)
    terse_draft = "2 waiting, 1 flagged for re-triage (see queue detail for names)."
    out = svc._guarded(terse_draft, scored, terse_draft, passages=[])
    assert out == terse_draft
    assert "guardrail replaced" not in out
