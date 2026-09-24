#!/usr/bin/env python3
"""
Seed PulseQueue with 14 days of synthetic waiting-room history plus a live
waiting room.

    python seed.py [--reset] [--if-empty]

History: patients arrive (about 3 an hour, busier in the evening) with a
realistic ESI mix, get triage vitals, have vitals re-taken on nurse rounds
every hour, and are seen after an acuity-dependent wait. The real service
re-scores the room every 30 minutes, exactly as it would in production, so
flags, silent risers and risk histories come from the engine itself. About
1 in 8 patients is quietly deteriorating (vitals drift worse each round);
when seen, they are usually upgraded on re-triage, so the feedback metrics
have real signal.

Live room: 11 patients arriving over the 2 hours before the seed ran, a few
of them deteriorating, so GET /queue shows something meaningful at once.
Re-run with --reset to refresh the live room. All data is synthetic:
no real patients.
"""

import time
from pathlib import Path

from gen4 import Memory
from gen4.seedkit import already_seeded, args, mark
from service import PulseQueueService

DAYS = 14
ESI_MIX = [(1, 0.02), (2, 0.15), (3, 0.45), (4, 0.30), (5, 0.08)]
WAIT_MEAN = {1: 2, 2: 18, 3: 55, 4: 80, 5: 95}   # minutes until seen


def pick_esi(rng):
    x, acc = rng.random(), 0.0
    for esi, p in ESI_MIX:
        acc += p
        if x < acc:
            return esi
    return 3


def base_vitals(rng):
    return {"hr": rng.randint(66, 98), "sbp": rng.randint(108, 142), "rr": rng.randint(12, 20),
            "spo2": rng.randint(95, 99), "temp": round(rng.uniform(36.4, 37.6), 1)}


def drift(rng, v, worsening):
    if worsening:
        return {"hr": v["hr"] + rng.randint(8, 16), "sbp": v["sbp"] - rng.randint(7, 15),
                "rr": v["rr"] + rng.randint(1, 3), "spo2": v["spo2"] - rng.randint(1, 2), "temp": v["temp"]}
    return {"hr": v["hr"] + rng.randint(-4, 4), "sbp": v["sbp"] + rng.randint(-5, 5), "rr": v["rr"],
            "spo2": min(100, max(94, v["spo2"] + rng.randint(-1, 1))), "temp": v["temp"]}


def main():
    a, rng = args("data/pulsequeue.db", "Seed PulseQueue with synthetic ED history")
    Path(a.db).parent.mkdir(parents=True, exist_ok=True)
    mem = Memory(a.db)
    if a.if_empty and already_seeded(mem):
        print(f"{a.db} already has data -- skipping seed")
        return
    svc = PulseQueueService(memory=mem)
    now = time.time() / 60.0
    start = now - DAYS * 1440 - 180

    # plan arrivals
    patients, t, k = [], start, 0
    while t < now - 180:
        hour = int((t / 60) % 24)
        rate = 4.5 if 17 <= hour <= 23 else 2.2 if hour < 7 else 3.0      # per hour
        t += rng.expovariate(rate / 60)
        esi = pick_esi(rng)
        k += 1
        patients.append({"id": f"H-{k:05d}", "esi": esi, "arrive": t, "worsening": rng.random() < 0.12,
                         "seen": t + max(1, rng.expovariate(1 / WAIT_MEAN[esi])), "vitals": base_vitals(rng)})

    events = []
    for p in patients:
        events.append((p["arrive"], "arrive", p))
        r = p["arrive"] + 60
        while r < p["seen"]:
            events.append((r, "round", p))
            r += 60
        events.append((p["seen"], "seen", p))
    tick = start + 30
    while tick < now - 180:
        events.append((tick, "tick", None))
        tick += 30
    events.sort(key=lambda e: e[0])

    upgraded = flagged = 0
    for when, kind, p in events:
        if kind == "arrive":
            svc.arrive(p["id"], p["esi"], at=when)
            svc.add_vitals(p["id"], p["vitals"], at=when + 2)
        elif kind == "round":
            p["vitals"] = drift(rng, p["vitals"], p["worsening"])
            svc.add_vitals(p["id"], p["vitals"], at=when)
        elif kind == "tick":
            svc.queue(now=when)
        else:
            svc.seen(p["id"], at=when)
            up = rng.random() < (0.85 if p["worsening"] else 0.05)
            was_flagged = bool(mem.facts(f"patient:{p['id']}", "flag_decision"))
            svc.outcome(p["id"], upgraded=up)
            upgraded += up
            flagged += was_flagged
            d = mem.history(p["id"], limit=1)[0]
            ts = _iso(when)
            mem.backdate(d["id"], ts, ts)

    # live waiting room: arrived in the last 2 hours, not yet seen
    live = []
    for j in range(11):
        arr = now - rng.uniform(5, 120)
        esi = pick_esi(rng)
        pid = f"P-{j + 1:02d}"
        worsening = j in (2, 7)
        svc.arrive(pid, esi, at=arr, complaint=rng.choice(
            ["abdominal pain", "chest discomfort", "fever", "laceration", "shortness of breath", "dizziness",
             "back pain", "headache"]))
        v = base_vitals(rng)
        svc.add_vitals(pid, v, at=arr + 2)
        if worsening and now - arr > 45:
            svc.add_vitals(pid, drift(rng, drift(rng, v, True), True), at=now - 3)
        live.append(pid)

    counts = {"historical_patients": len(patients), "flagged": flagged, "upgraded_on_retriage": upgraded,
              "live_waiting": len(live)}
    mark(mem, "pulsequeue", a.seed, counts)
    perf = svc.learn()
    print(f"seeded {a.db}: {counts}")
    print("per-ESI flag performance:", {e: v for e, v in perf["per_esi"].items() if v["flagged"]})
    print("pending proposals:", [p["param"] for p in perf["new_proposals"]])


def _iso(epoch_min):
    from datetime import datetime, timezone
    return datetime.fromtimestamp(epoch_min * 60, tz=timezone.utc).isoformat()


if __name__ == "__main__":
    main()
