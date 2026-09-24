#!/usr/bin/env python3
"""
PulseQueue eval gate. Segments:
  v1_parity    with no vitals, v2 reproduces v1's ordering and silent risers
  red_flag     a red-flag vital puts a just-arrived low-acuity patient first
  trend        a worsening trend inside normal ranges flags earlier than the clock
  no_overflag  stable vitals never add risk
  governance   learning proposes growth-rate changes but never applies them
"""

from gen4 import KnowledgeBase, LLMClient, Memory
from gen4.evals import EvalCase, gate, print_and_exit, run_eval
from service import PulseQueueService
from simulate import PATIENTS
from triage_engine import dynamic_queue, find_silent_risers


def fresh():
    return PulseQueueService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))


def seed(svc):
    for p in PATIENTS:
        svc.arrive(p.patient_id, p.esi, at=p.arrival_minute)


def system(kind):
    svc = fresh()
    if kind == "order":
        seed(svc)
        return [s["patient_id"] for s in svc.queue(now=90)["queue"]]
    if kind == "risers":
        seed(svc)
        return sorted(s["patient_id"] for s in svc.queue(now=90)["queue"] if s["silent_riser"])
    if kind == "red_flag":
        seed(svc)
        svc.arrive("X", 5, at=89)
        svc.add_vitals("X", {"spo2": 88, "hr": 96}, at=89.5)
        return svc.queue(now=90)["queue"][0]["patient_id"]
    if kind == "trend":
        svc.arrive("T", 3, at=0)
        svc.add_vitals("T", {"hr": 82, "sbp": 126}, at=2)
        svc.add_vitals("T", {"hr": 104, "sbp": 104}, at=15)
        return svc.queue(now=15)["queue"][0]["flagged"]
    if kind == "stable":
        svc.arrive("S", 3, at=0)
        svc.add_vitals("S", {"hr": 80, "sbp": 125, "spo2": 98}, at=2)
        svc.add_vitals("S", {"hr": 84, "sbp": 122, "spo2": 97}, at=15)
        s = svc.queue(now=15)["queue"][0]
        return (s["flagged"], s["trend"])
    if kind == "governance":
        for k in range(5):
            svc.arrive(f"m{k}", 4, at=0)
            svc.outcome(f"m{k}", upgraded=True)
        out = svc.learn()
        return (bool(out["new_proposals"]), svc.growth(4) == 0.55)
    raise ValueError(kind)


V1_ORDER = [s.patient.patient_id for s in dynamic_queue(PATIENTS, 90)]
V1_RISERS = sorted(s.patient.patient_id for s in find_silent_risers(PATIENTS, 90, 3))
CASES = [
    EvalCase("order-matches-v1", "order", V1_ORDER, "v1_parity"),
    EvalCase("risers-match-v1", "risers", V1_RISERS, "v1_parity"),
    EvalCase("spo2-88-goes-first", "red_flag", "X", "red_flag"),
    EvalCase("trend-flags-at-15-min", "trend", True, "trend"),
    EvalCase("stable-not-flagged", "stable", (False, []), "no_overflag"),
    EvalCase("proposal-not-applied", "governance", (True, True), "governance"),
]

if __name__ == "__main__":
    report = run_eval(CASES, system, runs=3)
    ok, why = gate(report, min_accuracy=1.0, min_consistency=1.0)
    print_and_exit("PulseQueue", report, ok, why)
