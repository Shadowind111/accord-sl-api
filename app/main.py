# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app import audit
from app.adapters.fhir import fhir_to_event
from app.adapters.hl7 import hl7_to_event
from app.config import API_KEY, CORS_ORIGINS
from app.ingest_schemas import FhirIngestRequest, Hl7IngestRequest
from app.registry import registry
from app.schemas import AckRequest, EventRequest, ScoreRequest, ScoreResponse
from app.store import get_store

app = FastAPI(
    title="ACCORD-SL Alert API",
    version="0.1.0",
    description=(
        "Model-agnostic hospital alert API. The GIST T1/T2 model is the first plugin; "
        "additional disease models can be registered behind the same contract. "
        "Research prototype only; not a diagnosis."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

store = get_store()


def require_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "models": [m["model_id"] for m in registry.list()]}


@app.get("/v1/models", dependencies=[Depends(require_key)])
def list_models() -> list[dict]:
    return registry.list()


@app.get("/v1/models/{model_id}", dependencies=[Depends(require_key)])
def get_model(model_id: str) -> dict:
    try:
        return registry.get(model_id).manifest
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {model_id}")


@app.post("/v1/score/{model_id}", response_model=ScoreResponse, dependencies=[Depends(require_key)])
def score(model_id: str, request: ScoreRequest) -> ScoreResponse:
    try:
        plugin = registry.get(model_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {model_id}")
    try:
        result = plugin.score(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    spec = plugin.alert_policy(result, request)
    alert = store.create(request.encounter_id, result, spec) if spec else None
    audit.write({
        "event": "score",
        "request_id": request.request_id,
        "encounter_id": request.encounter_id,
        "model_id": result.model_id,
        "model_version": result.model_version,
        "tier": result.tier,
        "score": result.calibrated_score,
        "flag": result.flag,
        "alert_id": alert.alert_id if alert else None,
    })
    return ScoreResponse(request_id=request.request_id, encounter_id=request.encounter_id, result=result, alert=alert)


@app.post("/v1/events/lab", dependencies=[Depends(require_key)])
def lab_event(event: EventRequest) -> dict:
    """Event-driven entry: route a lab panel to the relevant plugin.

    T1 high -> silent backend pending state; no clinician alert.
    T2 high -> alert per plugin policy (queue by default).
    """
    try:
        plugin = registry.get(event.model_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown model_id: {event.model_id}")
    try:
        result = plugin.score(event)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    spec = plugin.alert_policy(result, event)
    alert = store.create(event.encounter_id, result, spec) if spec else None
    if result.tier == "T1" and result.flag:
        store.set_pending(event.encounter_id, event.request_id, result.calibrated_score)
    elif result.tier == "T2":
        store.clear_pending(event.encounter_id)
    audit.write({
        "event": "lab_event",
        "request_id": event.request_id,
        "encounter_id": event.encounter_id,
        "model_id": result.model_id,
        "tier": result.tier,
        "score": result.calibrated_score,
        "flag": result.flag,
        "alert_id": alert.alert_id if alert else None,
    })
    return {
        "request_id": event.request_id,
        "encounter_id": event.encounter_id,
        "result": result,
        "alert": alert,
        "pending_t2": store.get_pending(event.encounter_id) is not None,
    }


@app.post("/v1/integrations/fhir", dependencies=[Depends(require_key)])
def ingest_fhir(req: FhirIngestRequest) -> dict:
    try:
        event = fhir_to_event(req.bundle, req.encounter_id, req.model_id, req.age)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return lab_event(event)


@app.post("/v1/integrations/hl7", dependencies=[Depends(require_key)])
def ingest_hl7(req: Hl7IngestRequest) -> dict:
    try:
        event = hl7_to_event(req.message, req.encounter_id, req.model_id, req.age)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return lab_event(event)


@app.get("/v1/pending/{encounter_id}", dependencies=[Depends(require_key)])
def get_pending(encounter_id: str) -> dict:
    return {"encounter_id": encounter_id, "pending": store.get_pending(encounter_id)}


@app.get("/v1/alerts", dependencies=[Depends(require_key)])
def list_alerts(status: str | None = Query(default=None, pattern="^(open|acknowledged|dismissed)$")):
    return store.list(status=status)


@app.post("/v1/alerts/{alert_id}/ack", dependencies=[Depends(require_key)])
def ack_alert(alert_id: str, body: AckRequest):
    alert = store.acknowledge(alert_id, body.actor)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    audit.write({"event": "alert_ack", "encounter_id": alert.encounter_id, "alert_id": alert.alert_id, "actor": body.actor})
    return alert


@app.post("/v1/alerts/{alert_id}/dismiss", dependencies=[Depends(require_key)])
def dismiss_alert(alert_id: str, body: AckRequest):
    alert = store.dismiss(alert_id, body.actor)
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    audit.write({"event": "alert_dismiss", "encounter_id": alert.encounter_id, "alert_id": alert.alert_id, "actor": body.actor})
    return alert


@app.get("/v1/audit/{encounter_id}", dependencies=[Depends(require_key)])
def get_audit(encounter_id: str):
    return audit.read(encounter_id)
