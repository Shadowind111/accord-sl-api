# Hospital deployment guide

## 1. What this service is

An on-premise REST service that:

1. accepts a lab panel / encounter;
2. routes it to the relevant disease plugin;
3. returns a score, flag and reasons;
4. creates an alert according to a policy (queue / banner / modal);
5. stores an audit trail.

The GIST T1/T2 plugin is first. Future disease models are additional plugins behind the same contract.

## 2. Recommended architecture

```text
HIS front-end / doctor workstation
   │ reads alert table or calls HIS BFF
   ▼
HIS backend / BFF
   │ internal HTTPS + API key/mTLS
   ▼
ACCORD-SL API (Docker, hospital intranet)
   ├─ plugin registry
   ├─ GIST plugin
   ├─ future disease plugins
   └─ alert + audit store
```

Lab flow:

```text
LIS / integration engine
   │ HL7 ORU^R01, FHIR Observation, or DB event
   ▼
integration adapter
   │ POST /v1/events/lab
   ▼
T1 high -> silent pending state
T2 high -> alert (queue by default)
   │
HIS front-end reads /v1/alerts or an alert table
```

## 3. Prerequisites

- Docker 24+ or a Python 3.12 runtime;
- 2 CPU / 4 GB RAM minimum for fast mode;
- internal DNS/TLS certificate;
- API key or mTLS between HIS and API;
- outbound internet **not required** at runtime;
- no patient data leaves the hospital network.

## 4. Build and run

```powershell
docker build -t accord-sl-api:0.1.0 .
docker run -d --name accord-sl-api `
  -p 8000:8000 `
  -e ACCORD_API_KEY="<strong-random-key>" `
  -e ACCORD_AUDIT_LOG="/data/audit.jsonl" `
  -v "D:\accord-sl-api\data:/data" `
  accord-sl-api:0.1.0
```

Health check:

```powershell
curl.exe http://127.0.0.1:8000/health
```

With PostgreSQL (recommended):

```powershell
docker compose up -d
```

This starts `db` and `accord-api`, applies `migrations/001_init.sql` at API startup, and persists alerts/pending state in the `data/postgres` volume.

## 5. Environment

| Variable | Default | Meaning |
|---|---|---|
| `ACCORD_API_KEY` | `dev-key-change-me` | Required for `/v1/*`; change in production |
| `ACCORD_AUDIT_LOG` | `audit.jsonl` | Audit file path; mount a persistent volume |
| `ACCORD_CORS_ORIGINS` | `http://localhost` | Only needed if browser calls directly; hospital BFF should call server-to-server |
| `ACCORD_MODEL_MODE` | `fast` | Current API ships fast models; full mode is a separate optional package |
| `ACCORD_DATABASE_URL` | empty | PostgreSQL DSN; if empty, in-memory store (tests/demo only) |

## 6. Input mapping

Do not send raw LIS column names directly. The hospital adapter must map:

- local lab code → friendly API field;
- local unit → contract unit;
- `<` / `>` / text values → numeric or categorical;
- missing values → omit the field (the model has its own imputation);
- encounter ID → pseudonymous ID.

Example T2 fields:

```json
{
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
  "sodium": 140.0
}
```

The full field list is in `GET /v1/models/gist`. `missing_inputs` in the response tells the caller what was absent.

## 7. HIS integration patterns

### A. Alert table (recommended)

- API writes alerts to a table (`accord_alert`) or exposes `/v1/alerts`.
- HIS front-end polls/reads the table and renders queue/banner/modal.
- Doctor actions call `/ack` or `/dismiss`.
- No synchronous model call in the doctor's UI.

### B. Server-to-server call

- HIS backend calls `/v1/score/gist` when labs arrive.
- Response is stored/rendered by HIS.
- Must implement timeout, retry and idempotency using `request_id`.

### C. FHIR/HL7 adapter

Reference HTTP adapters are included:

- `POST /v1/integrations/fhir` for a FHIR R4 Bundle of Observations;
- `POST /v1/integrations/hl7` for an HL7 v2 ORU^R01 pipe message.

They perform minimal code/value mapping only. In production, the hospital integration engine should validate FHIR/HL7, reconcile patient/encounter identity, convert units, handle MLLP/ACK, and write back a FHIR `RiskAssessment`/`Flag`/`Task` if required. See `INTEGRATION_FHIR_HL7.md`.

## 8. Alert policy

The GIST plugin currently:

- T1 high → **no clinician alert**, silent `pending_t2`;
- T2 high → **queue** by default;
- `context.confirmed_high_risk=true` → **banner**;
- `context.critical=true` + `clinician_available=true` → **modal** (use sparingly).

The 12-clinician usability study supports this tiering: queue was preferred 8/12; modal was clearest but most intrusive; repeat alerts should be suppressed.

## 9. Production hardening checklist

- [x] PostgreSQL store available (`ACCORD_DATABASE_URL`), with `migrations/001_init.sql`; production should add backups/retention.
- [x] Durable `accord_pending_t2` table replaces the in-memory pending dict.
- [ ] Put API behind TLS reverse proxy (nginx/Traefik) and network policy.
- [ ] Use mTLS or OIDC in addition to API key.
- [ ] Add rate limiting per ward/model.
- [ ] Add request size limits and schema validation.
- [ ] Add structured logs without lab values or patient identifiers.
- [ ] Add backup/retention policy for audit logs.
- [ ] Add model/plugin signing and a deployment approval step.
- [ ] Add monitoring: latency, error rate, alert volume, ack rate.
- [ ] Run silent mode for 2–4 weeks before any pop-up.
- [ ] Complete local ethics, data-protection and regulatory review.

## 10. Model/plugin onboarding

A new disease model must provide:

1. a plugin class implementing `RiskModelPlugin`;
2. a manifest with input schema, units, threshold and alert policy;
3. local calibration and validation report;
4. alert copy and actions;
5. version, owner and rollback plan;
6. evidence that it works in the hospital's own data.

The platform slot makes integration uniform; it does **not** remove the need for local validation.

## 11. Limitations of this reference build

- Fast mode only;
- PostgreSQL support is included; in-memory store remains for tests/demo.
- API-key auth only;
- reference FHIR/HL7 adapters only; no full validation, ACK/MLLP or write-back;
- no database;
- no rate limiting;
- not a medical device.

These are deliberate: the goal is a deployable reference contract, not a finished regulated product.
