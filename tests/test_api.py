# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "dev-key-change-me"}

T1 = {
    "age": 70,
    "basophil_pct": 0.9,
    "alt": "20",
    "albumin": "42.0",
    "urine_color": "黄褐色",
    "fecal_occult": "阴性(-)",
}
T2 = {
    "age": 70,
    "pt_activity": 100.8,
    "hs_crp": "> 10.00",
    "potassium": 4.15,
    "calcium": 2.5,
    "aptt": "23.9",
    "phosphate": 1.07,
    "co2_binding": "29",
    "chloride": 105.0,
    "crp": "35.03",
    "magnesium": 0.89,
    "sodium": 140.0,
}


def body(labs: dict, encounter: str = "enc-test-1") -> dict:
    return {
        "request_id": "req-test-1",
        "encounter_id": encounter,
        "patient": {"age": labs.pop("age")},
        "labs": labs,
        "context": {},
    }


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_auth_required():
    r = client.get("/v1/models")
    assert r.status_code == 401


def test_models_include_gist_and_slot():
    r = client.get("/v1/models", headers=HEADERS)
    assert r.status_code == 200
    ids = {m["model_id"] for m in r.json()}
    assert "gist" in ids
    assert "referral_demo" in ids


def test_t1_score_is_silent():
    r = client.post("/v1/score/gist", json=body(dict(T1), "enc-t1"), headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["tier"] == "T1"
    assert data["alert"] is None


def test_t2_score_creates_alert_and_deduplicates():
    r1 = client.post("/v1/score/gist", json=body(dict(T2), "enc-t2"), headers=HEADERS)
    assert r1.status_code == 200
    d1 = r1.json()
    assert d1["result"]["tier"] == "T2"
    assert d1["alert"] is not None
    assert d1["alert"]["channel"] in {"queue", "banner", "modal"}

    r2 = client.post("/v1/score/gist", json=body(dict(T2), "enc-t2"), headers=HEADERS)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2["alert"]["dedup_key"] == d1["alert"]["dedup_key"]

    alerts = client.get("/v1/alerts", headers=HEADERS).json()
    assert any(a["encounter_id"] == "enc-t2" for a in alerts)


def test_event_endpoint():
    payload = body(dict(T2), "enc-event")
    payload["model_id"] = "gist"
    r = client.post("/v1/events/lab", json=payload, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["tier"] == "T2"
    assert data["alert"] is not None


def test_demo_plugin_proves_slot():
    payload = body({"age": 60, "crp": 50}, "enc-demo")
    r = client.post("/v1/score/referral_demo", json=payload, headers=HEADERS)
    assert r.status_code == 200
    data = r.json()
    assert data["result"]["tier"] == "single"
    assert "demo" in data["result"]["disclaimer"].lower()
