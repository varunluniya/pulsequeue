#!/usr/bin/env python3
"""
Prove-It: minutes until each patient is flagged for re-triage, v1 vs v2.

Six patients over a 120-minute window. Two are quietly deteriorating: their
vitals worsen while each reading is still inside, or only just outside,
normal limits. v1 sees only acuity and elapsed time, so it waits for the
clock. v2 also reads vital-sign red flags and the trend between readings.
"""

from gen4 import KnowledgeBase, LLMClient, Memory
from service import PulseQueueService
from triage_engine import Patient, score_patient

PATIENTS = [  # id, esi, arrival minute, [(minute, vitals)], truly deteriorating?
    ("A", 3, 0, [(5, {"hr": 84, "sbp": 128, "spo2": 97}), (20, {"hr": 106, "sbp": 106, "spo2": 96})], True),
    ("B", 4, 0, [(5, {"hr": 78, "sbp": 124, "spo2": 96}), (25, {"hr": 92, "sbp": 118, "spo2": 91})], True),
    ("C", 3, 0, [(5, {"hr": 80, "sbp": 130, "spo2": 98}), (35, {"hr": 82, "sbp": 128, "spo2": 98})], False),
    ("D", 4, 10, [(15, {"hr": 72, "sbp": 122, "spo2": 99})], False),
    ("E", 2, 30, [(32, {"hr": 96, "sbp": 140, "spo2": 97})], False),
    ("F", 5, 0, [], False),
]


def main():
    svc = PulseQueueService(Memory(), KnowledgeBase.from_dir("knowledge"), LLMClient(provider="offline"))
    first_v1, first_v2, why = {}, {}, {}
    for t in range(0, 121):
        for pid, esi, arr, vit, _ in PATIENTS:
            if t == arr:
                svc.arrive(pid, esi, at=arr)
            for m, v in vit:
                if t == m:
                    svc.add_vitals(pid, v, at=m)
        for s in svc.queue(now=t)["queue"]:
            if s["flagged"] and s["patient_id"] not in first_v2:
                first_v2[s["patient_id"]], why[s["patient_id"]] = t, "; ".join(s["reasons"])
        for pid, esi, arr, _, _ in PATIENTS:
            if t >= arr and pid not in first_v1 and score_patient(Patient(pid, esi, arr), t).flagged:
                first_v1[pid] = t
    print(f"{'pt':<4}{'ESI':<5}{'deteriorating':<15}{'v1 flag @min':<14}{'v2 flag @min':<14}v2 reason")
    for pid, esi, arr, _, bad in PATIENTS:
        f1 = first_v1.get(pid, "-")
        f2 = first_v2.get(pid, "-")
        print(f"{pid:<4}{esi:<5}{'yes' if bad else 'no':<15}{str(f1):<14}{str(f2):<14}{why.get(pid, '')}")
    gain = [first_v1[p[0]] - first_v2[p[0]] for p in PATIENTS if p[4]]
    print(f"\nDeteriorating patients flagged {', '.join(str(g) for g in gain)} minutes earlier by v2.")


if __name__ == "__main__":
    main()
