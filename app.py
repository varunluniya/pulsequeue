"""
PulseQueue API.   uvicorn app:app --reload    ->  http://127.0.0.1:8000/docs

Times are minutes on a shared clock. Omit them to use server time
(epoch minutes); pass them explicitly for simulation and replay.
Decision support only -- every re-triage call is made by a clinician.
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from gen4.api import common_router
from service import PulseQueueService

service = PulseQueueService()
app = FastAPI(title="PulseQueue", version="2.0.0",
              description="Live ED waiting-room re-scoring: acuity x wait, vital-sign red flags and "
                          "trends, accelerating patients, silent risers, and outcome-driven learning "
                          "under clinical-lead approval. Decision support only.")
app.include_router(common_router(service, "pulsequeue"))


class ArrivalIn(BaseModel):
    patient_id: str
    esi: int = Field(..., ge=1, le=5)
    at: float | None = None
    complaint: str = ""


class VitalsIn(BaseModel):
    hr: float | None = None
    sbp: float | None = None
    rr: float | None = None
    spo2: float | None = None
    temp: float | None = None
    at: float | None = None


class OutcomeIn(BaseModel):
    upgraded: bool = Field(..., description="Did re-triage raise this patient's acuity?")


def _guard(fn, *a, **k):
    try:
        return fn(*a, **k)
    except KeyError:
        raise HTTPException(404, "unknown patient")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/", tags=["ops"])
def root():
    return {"service": "PulseQueue", "docs": "/docs",
            "flow": "POST /patients -> POST /patients/{id}/vitals -> GET /queue -> POST /patients/{id}/seen "
                    "-> POST /patients/{id}/outcome"}


@app.post("/patients", tags=["waiting room"])
def arrive(body: ArrivalIn):
    return _guard(service.arrive, body.patient_id, body.esi, body.at, body.complaint)


@app.post("/patients/{pid}/vitals", tags=["waiting room"])
def vitals(pid: str, body: VitalsIn):
    d = body.model_dump()
    at = d.pop("at")
    return _guard(service.add_vitals, pid, d, at)


@app.post("/patients/{pid}/seen", tags=["waiting room"])
def seen(pid: str, at: float | None = None):
    return _guard(service.seen, pid, at)


@app.get("/queue", tags=["waiting room"])
def queue(now: float | None = None, watch: int = 3):
    return _guard(service.queue, now, watch)


@app.post("/patients/{pid}/outcome", tags=["feedback"])
def outcome(pid: str, body: OutcomeIn):
    return _guard(service.outcome, pid, body.upgraded)


@app.get("/metrics", tags=["feedback"])
def metrics():
    return service.learn()
