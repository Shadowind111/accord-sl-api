# Smoke test record (2026-11-05)

## Local API

```text
python -m pytest tests -q
9 passed
```

## Docker

```text
image: accord-sl-api:0.1.0
size: 878 MB
health: 200 {"status":"ok","models":["gist","referral_demo"]}
```

## GIST T2 request

`samples/score_t2.json`:

```text
tier: T2
calibrated_score: 0.482
flag: true
alert.channel: queue
alert.title: GIST 风险评估提示（研究）
```

## FHIR/HL7

- `samples/fhir_bundle.json` -> `/v1/integrations/fhir`: T2, flag true, alert created;
- `samples/hl7_oru.txt` -> `/v1/integrations/hl7`: T2, flag true, alert created.

## PostgreSQL

Tested with `docker compose up -d`:

- `/health` 200;
- T2 score created `alert-da493a040ffb`;
- `/v1/alerts` returned the alert;
- `/v1/alerts/{id}/ack` set status `acknowledged`;
- after restarting the API, `/v1/alerts` still returned the acknowledged alert (durable store).

## Notes

- Docker image contains only CPU dependencies (`xgboost-cpu`, `interpret-core`).
- No API key is baked into the image; pass `ACCORD_API_KEY` at runtime.
- The reference alert store is in-memory; replace before production.
- Full five-expert GIST mode is not included in this image; the API currently uses fast mode.
