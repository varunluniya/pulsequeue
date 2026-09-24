"""
PulseQueue intelligent service — a live, stateful waiting-room monitor.

    Retrieval  site re-triage protocol; the rule behind every flag is cited
    Context    department load (waiting count, arrivals in the last hour), vitals
    Memory     each patient's trajectory: arrival, vitals readings, risk history
    Feedback   re-triage outcomes -> per-ESI flag precision and misses ->
               growth-rate proposals approved by the clinical lead

v1 re-scored a fixed list from acuity + wait. v2 is a running service that
also reads vital-sign red flags and *trends* (worsening between readings,
even inside normal ranges), detects accelerating patients from their own
risk history, and learns whether its flags were right.

Decision support only -- a triage nurse makes every re-triage call.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from gen4 import Context, KnowledgeBase, LLMClient, Memory, Trace
from gen4 import feedback as fb
from triage_engine import BASE_RISK_PER_URGENCY_POINT, RE_TRIAGE_RISK_THRESHOLD, RISK_PER_MINUTE_BY_URGENCY

SYSTEM = "pulsequeue"
HERE = Path(__file__).parent
RED_FLAGS = {  # example site defaults -- see knowledge/retriage_protocol.md
    "spo2": ("<", 92), "sbp": ("<", 90), "hr": (">", 130), "rr": (">", 30), "temp": (">", 39.5)}
TREND_RULES = {"hr": +20, "sbp": -20, "spo2": -3}
TREND_BONUS = 15.0
LOAD_WAITING, LOAD_ARRIVALS = 15, 12


def _now_min() -> float:
    return time.time() / 60.0


class PulseQueueService:
    def __init__(self, memory: Memory | None = None, kb: KnowledgeBase | None = None,
                 llm: LLMClient | None = None):
        self.memory = memory or Memory(os.environ.get("GEN4_DB", HERE / "data" / f"{SYSTEM}.db"))
        self.kb = kb or KnowledgeBase.from_dir(HERE / "knowledge")
        self.llm = llm or LLMClient()

    # -- learned parameters -------------------------------------------------------
    def growth(self, esi: int) -> float:
        urgency = 6 - esi
        return self.memory.get_param(f"growth:esi{esi}", RISK_PER_MINUTE_BY_URGENCY[urgency])

    # -- patient state (memory) ------------------------------------------------------
    def _state(self, pid: str) -> dict | None:
        return self.memory.fact(f"patient:{pid}", "state")

    def _save(self, pid: str, st: dict) -> None:
        self.memory.add_fact(f"patient:{pid}", "state", st, source="ed")

    def arrive(self, pid: str, esi: int, at: float | None = None, complaint: str = "") -> dict:
        if not 1 <= esi <= 5:
            raise ValueError("ESI must be 1-5")
        if self._state(pid):
            raise ValueError(f"patient {pid} already registered")
        st = {"id": pid, "esi": esi, "arrival": at if at is not None else _now_min(), "complaint": complaint,
              "vitals": [], "status": "waiting", "risk_history": []}
        self._save(pid, st)
        return st

    def add_vitals(self, pid: str, vitals: dict, at: float | None = None) -> dict:
        st = self._state(pid)
        if not st:
            raise KeyError(pid)
        st["vitals"].append({"at": at if at is not None else _now_min(),
                             **{k: v for k, v in vitals.items() if v is not None}})
        self._save(pid, st)
        return st

    def seen(self, pid: str, at: float | None = None) -> dict:
        st = self._state(pid)
        if not st:
            raise KeyError(pid)
        st["status"], st["seen_at"] = "seen", at if at is not None else _now_min()
        self._save(pid, st)
        return st

    def waiting(self) -> list[dict]:
        return [f["object"] for f in self.memory.facts(predicate="state")
                if f["subject"].startswith("patient:") and f["object"]["status"] == "waiting"]

    # -- scoring ---------------------------------------------------------------------
    @staticmethod
    def red_flags(v: dict) -> list[str]:
        out = []
        for k, (op, lim) in RED_FLAGS.items():
            if k in v and ((op == "<" and v[k] < lim) or (op == ">" and v[k] > lim)):
                out.append(f"{k} {v[k]} {op} {lim}")
        return out

    @staticmethod
    def trends(vitals: list[dict]) -> list[str]:
        if len(vitals) < 2:
            return []
        a, b = vitals[-2], vitals[-1]
        out = []
        for k, delta in TREND_RULES.items():
            if k in a and k in b:
                change = b[k] - a[k]
                if (delta > 0 and change >= delta) or (delta < 0 and change <= delta):
                    out.append(f"{k} {a[k]}->{b[k]}")
        return out

    def score(self, st: dict, now: float) -> dict:
        elapsed = now - st["arrival"]
        if elapsed < 0:
            raise ValueError(f"'now' is before patient {st['id']}'s arrival")
        urgency = 6 - st["esi"]
        latest = st["vitals"][-1] if st["vitals"] else {}
        flags, trend = self.red_flags(latest), self.trends(st["vitals"])
        risk = urgency * BASE_RISK_PER_URGENCY_POINT + self.growth(st["esi"]) * elapsed + TREND_BONUS * len(trend)
        hist = [h for h in st["risk_history"] if now - h["at"] <= 30]
        accel = False
        if hist:
            first = hist[0]
            dt = now - first["at"]
            if dt >= 5:
                accel = (risk - first["risk"]) / dt > self.growth(st["esi"]) * 1.5
        reasons = []
        if flags:
            reasons.append("vital-sign red flag: " + ", ".join(flags))
        if trend:
            reasons.append("worsening trend: " + ", ".join(trend))
        if risk >= RE_TRIAGE_RISK_THRESHOLD:
            reasons.append(f"risk {risk:.0f} crossed {RE_TRIAGE_RISK_THRESHOLD:.0f} after {elapsed:.0f} min")
        return {"patient_id": st["id"], "esi": st["esi"], "waited_min": round(elapsed, 1),
                "risk": round(risk, 1), "flagged": bool(flags) or risk >= RE_TRIAGE_RISK_THRESHOLD,
                "red_flags": flags, "trend": trend, "accelerating": accel, "reasons": reasons}

    # -- the queue --------------------------------------------------------------------
    def queue(self, now: float | None = None, watch: int = 3, record: bool = True) -> dict:
        now = now if now is not None else _now_min()
        pts = self.waiting()
        scored = [self.score(p, now) for p in pts]
        scored.sort(key=lambda s: (not s["red_flags"], not (s["flagged"] and s["accelerating"]),
                                   -s["risk"]))
        static = sorted(pts, key=lambda p: (p["esi"], p["arrival"]))
        static_rank = {p["id"]: i + 1 for i, p in enumerate(static)}
        top_dyn = {s["patient_id"] for s in scored[:watch]}
        top_static = {p["id"] for p in static[:watch]}
        for i, s in enumerate(scored, 1):
            s["rank"], s["static_rank"] = i, static_rank[s["patient_id"]]
            s["silent_riser"] = s["patient_id"] in top_dyn - top_static

        arrivals_60 = sum(1 for f in self.memory.facts(predicate="state")
                          if f["subject"].startswith("patient:") and 0 <= now - f["object"]["arrival"] <= 60)
        high_load = len(pts) > LOAD_WAITING or arrivals_60 > LOAD_ARRIVALS
        ctx = (Context().add("waiting", len(pts)).add("arrivals_last_60_min", arrivals_60)
               .add("recheck_interval_min", 15 if high_load else 30, "department load rule"))
        trace = Trace(context=ctx.as_dict(),
                      params={f"growth:esi{e}": self.growth(e) for e in range(1, 6)})
        q = "dynamic risk score silent risers"
        if any(s["red_flags"] for s in scored):
            q += " vital-sign red flags"
        if any(s["trend"] for s in scored):
            q += " worsening trend between readings"
        if any(s["accelerating"] for s in scored):
            q += " accelerating risk"
        if high_load:
            q += " department load"
        trace.cite(self.kb.search(q, k=3))
        trace.memory = {"patients_with_vitals": sum(1 for p in pts if p["vitals"])}

        if record:
            for s in scored:
                st = next(p for p in pts if p["id"] == s["patient_id"])
                st["risk_history"] = [h for h in st["risk_history"] if now - h["at"] <= 120] + \
                                     [{"at": now, "risk": s["risk"]}]
                self._save(st["id"], st)
                if s["flagged"] and not self.memory.facts(f"patient:{st['id']}", "flag_decision"):
                    did = self.memory.record_decision(SYSTEM, st["id"], {"esi": st["esi"]}, s)
                    self.memory.add_fact(f"patient:{st['id']}", "flag_decision", did)
        summary = self._handoff(scored)
        trace.model = {"provider": self.llm.last_provider}
        return {"now": now, "queue": scored, "handoff_summary": summary, "trace": trace.as_dict()}

    def _handoff(self, scored: list[dict]) -> str:
        def offline():
            flagged = [s for s in scored if s["flagged"]]
            if not flagged:
                return f"{len(scored)} waiting; no one flagged for re-triage."
            lines = [f"{len(scored)} waiting, {len(flagged)} flagged for re-triage:"]
            for s in flagged[:5]:
                tag = " (ACCELERATING)" if s["accelerating"] else ""
                lines.append(f"- {s['patient_id']} ESI {s['esi']}, {s['waited_min']:.0f} min{tag}: "
                             + "; ".join(s["reasons"]))
            return "\n".join(lines)
        return self.llm.complete("Write a 5-line charge-nurse handoff from this queue JSON: "
                                 f"{[{k: s[k] for k in ('patient_id','esi','waited_min','reasons')} for s in scored if s['flagged']]}",
                                 offline=offline, max_tokens=250)

    # -- feedback -----------------------------------------------------------------------
    def outcome(self, pid: str, upgraded: bool) -> dict:
        """Did re-triage actually upgrade this patient's acuity (or should it have)?"""
        st = self._state(pid)
        if not st:
            raise KeyError(pid)
        did = self.memory.fact(f"patient:{pid}", "flag_decision")
        if did:
            self.memory.record_outcome(did, {"upgraded": upgraded})
        else:  # never flagged: a miss if upgraded
            did = self.memory.record_decision(SYSTEM, pid, {"esi": st["esi"]}, {"flagged": False})
            self.memory.record_outcome(did, {"upgraded": upgraded})
        return self.learn()

    def learn(self, min_n: int = 10) -> dict:
        done = self.memory.decisions(system=SYSTEM, with_outcome=True)
        per_esi, proposals = {}, []
        for esi in range(1, 6):
            rows = [d for d in done if d["features"]["esi"] == esi]
            flagged = [d for d in rows if d["output"].get("flagged")]
            tp = sum(d["outcome"]["upgraded"] for d in flagged)
            missed = sum(1 for d in rows if not d["output"].get("flagged") and d["outcome"]["upgraded"])
            prec = fb.rate(tp, len(flagged))
            per_esi[esi] = {"flagged": len(flagged), "precision": prec, "missed_upgrades": missed}
            cur = self.growth(esi)
            if missed >= 3 and missed / max(1, len(rows)) > 0.2:
                proposals.append(fb.propose(self.memory, f"growth:esi{esi}", cur, round(cur * 1.1, 3),
                                            f"{missed} ESI-{esi} patients were upgraded without a flag",
                                            per_esi[esi]))
            elif len(flagged) >= min_n and prec is not None and prec < 0.2:
                proposals.append(fb.propose(self.memory, f"growth:esi{esi}", cur, round(cur * 0.9, 3),
                                            f"only {prec:.0%} of ESI-{esi} flags led to an upgrade",
                                            per_esi[esi]))
        self.memory.add_fact("model:pulsequeue", "flag_performance", per_esi)
        return {"per_esi": per_esi, "new_proposals": proposals}
