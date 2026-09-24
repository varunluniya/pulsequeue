import os
import tempfile

os.environ["GEN4_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
os.environ["GEN4_LLM_PROVIDER"] = "offline"

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

c = TestClient(app)


def test_waiting_room_flow():
    assert c.post("/patients", json={"patient_id": "a", "esi": 3, "at": 0}).status_code == 200
    assert c.post("/patients", json={"patient_id": "b", "esi": 5, "at": 0}).status_code == 200
    c.post("/patients/b/vitals", json={"spo2": 89, "at": 3})
    q = c.get("/queue", params={"now": 5}).json()
    assert q["queue"][0]["patient_id"] == "b"
    c.post("/patients/b/seen", params={"at": 6})
    assert [s["patient_id"] for s in c.get("/queue", params={"now": 7}).json()["queue"]] == ["a"]
    assert "per_esi" in c.post("/patients/b/outcome", json={"upgraded": True}).json()


def test_errors():
    assert c.post("/patients", json={"patient_id": "z", "esi": 9}).status_code == 422
    assert c.post("/patients/nope/vitals", json={"hr": 90}).status_code == 404
    c.post("/patients", json={"patient_id": "late", "esi": 3, "at": 500})
    assert c.get("/queue", params={"now": 100}).status_code == 422
