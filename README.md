# ACCORD-SL Alert API

Research-use, model-agnostic hospital alert API. The first plugin is the GIST T1/T2 model; a demo plugin (`referral_demo`) proves the slot for future disease models.

**Not a medical device. Not a diagnosis. Not for clinical use without local validation, ethics/governance approval and regulatory review.**

## Why this exists

Hospital HIS/front-end systems should not load Python models or call Hugging Face at runtime. They need an on-premise service with:

- a stable REST contract;
- input validation and unit mapping;
- model versioning/audit;
- alert routing and deduplication;
- a plugin slot for future diseases.

This service is that layer.

## Quick start (local)

```powershell
cd D:\pythonProject\v10\v11_t2_numeric_20261104\release_api
$env:ACCORD_API_KEY = "dev-key-change-me"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

By default the alert/pending store is in-memory. For PostgreSQL, set `ACCORD_DATABASE_URL` or run the full stack:

```powershell
docker compose up -d
```

The compose stack starts PostgreSQL, applies the schema on API startup, and exposes the API at `http://127.0.0.1:8000`.

Open:

- Swagger UI: `http://127.0.0.1:8000/docs`
- Health: `http://127.0.0.1:8000/health`

Every `/v1/*` call needs:

```text
X-API-Key: dev-key-change-me
```

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness and loaded models |
| GET | `/v1/models` | Plugin manifests |
| GET | `/v1/models/{model_id}` | One manifest |
| POST | `/v1/score/{model_id}` | Score one case |
| POST | `/v1/events/lab` | Lab-result event; auto-route to plugin |
| POST | `/v1/integrations/fhir` | FHIR R4 Observation bundle adapter |
| POST | `/v1/integrations/hl7` | HL7 v2 ORU^R01 adapter |
| GET | `/v1/pending/{encounter_id}` | T1-high, T2-pending state |
| GET | `/v1/alerts` | Alert queue |
| POST | `/v1/alerts/{alert_id}/ack` | Acknowledge |
| POST | `/v1/alerts/{alert_id}/dismiss` | Dismiss |
| GET | `/v1/audit/{encounter_id}` | Audit trail (no PHI values) |

## GIST example (T2)

```powershell
curl.exe -X POST "http://127.0.0.1:8000/v1/score/gist" `
  -H "Content-Type: application/json" `
  -H "X-API-Key: dev-key-change-me" `
  --data "@samples/score_t2.json"
```

Response shape:

```json
{
  "request_id": "req-t2-001",
  "encounter_id": "enc-t2-001",
  "result": {
    "model_id": "gist",
    "tier": "T2",
    "score": 0.62,
    "flag": true,
    "threshold": 0.05,
    "reasons": ["age=70", "PT=100.8", "CRP=35.03", "input descriptors, not causal explanations"],
    "disclaimer": "Research prototype only..."
  },
  "alert": {
    "alert_id": "alert-...",
    "channel": "queue",
    "severity": "high",
    "status": "open"
  }
}
```

T1 calls return `tier: "T1"` and `alert: null`; a T2-high result creates an alert.

## Models

| model_id | Status | Notes |
|---|---|---|
| `gist` | research | T1 r3 + T2 v11 **fast** experts (EBM+XGBoost / EBM+RandomForest) |
| `referral_demo` | demo only | Placeholder showing the plugin slot; not clinical |

The full five-expert GIST artifacts are larger and should be added as a separate optional plugin/profile after local performance testing.

## Plugin slot

A new disease model is a package with:

```text
app/plugins/<name>/
  __init__.py
  plugin.py        # subclass RiskModelPlugin
```

It declares:

- `model_id`, `manifest`;
- `score(request) -> PluginResult`;
- optional `alert_policy(result, request) -> AlertSpec | None`.

Then register it in `app/registry.py`. The API, alert engine, audit and front-end contract do not change.

See `PLUGIN_ARCHITECTURE.md` for the full contract.

## Tests\n\n```powershell\npip install -r requirements-dev.txt\npython -m pytest tests -q\n```

## Docker

```powershell
docker build -t accord-sl-api:0.1.0 .
docker run --rm -p 8000:8000 `
  -e ACCORD_API_KEY=change-me `
  -v "${PWD}/data:/data" `
  accord-sl-api:0.1.0
```

For hospital deployment details see `DEPLOYMENT.md`.

## Security notes

- Change `ACCORD_API_KEY`; never commit it.
- Put the service behind hospital TLS/reverse proxy and network policy.
- The reference alert store is in-memory; production must use a database with a unique `dedup_key`.
- Audit logs contain IDs and scores, not raw lab values.
- Do not expose `/docs` publicly without authentication in production.
