# FHIR / HL7 integration

This is a **reference adapter**, not a complete integration engine. In production, the hospital integration engine should normally do the mapping; these endpoints let a hospital test the full path quickly.

## FHIR R4

`POST /v1/integrations/fhir`

```json
{
  "bundle": { "resourceType": "Bundle", "entry": [ ... ] },
  "encounter_id": "enc-fhir-001",
  "model_id": "gist",
  "age": null
}
```

- Age is taken from `Patient.birthDate`; `age` is an optional override.
- `Observation.valueQuantity.value`, `valueString` or `valueCodeableConcept.text` are accepted.
- `encounter_id` is supplied by the caller (not inferred from `Encounter`).

### LOINC mapping used by the adapter

| LOINC | API field |
|---|---|
| 5902-2 | `pt_activity` |
| 30522-7 | `hs_crp` |
| 1988-5 | `crp` |
| 2823-3 | `potassium` |
| 17861-6 | `calcium` |
| 3173-2 | `aptt` |
| 2777-1 | `phosphate` |
| 1963-8 | `co2_binding` |
| 2075-0 | `chloride` |
| 19123-9 | `magnesium` |
| 2951-2 | `sodium` |
| 1742-6 | `alt` |
| 1751-7 | `albumin` |
| 706-2 | `basophil_pct` |

Local aliases (e.g. `PT`, `hs-CRP`, `K`, `Na`) are also accepted by display text.

Example: `samples/fhir_bundle.json`.

## HL7 v2 ORU^R01

`POST /v1/integrations/hl7`

```json
{
  "message": "MSH|^~\\&|LIS|H|HIS|H|202611061200||ORU^R01|1|P|2.5\rPID|...",
  "encounter_id": "enc-hl7-001",
  "model_id": "gist",
  "age": null
}
```

- Age comes from `PID-7` (birth date, `YYYYMMDD`); `age` is an optional override.
- Lab values come from `OBX-3` (code) and `OBX-5` (value).
- `OBX-3` may be `LOINC^text` or a local code/alias.

Example: `samples/hl7_oru.txt`.

## What is not included

- FHIR resource validation/profiles;
- HL7 ACK/NACK generation;
- MLLP transport (this endpoint is HTTP JSON; the integration engine terminates MLLP);
- terminology server integration;
- unit conversion beyond what the caller supplies;
- encounter/patient reconciliation.

These belong in the hospital integration layer. The API contract assumes the adapter has already produced canonical friendly fields and units.

## Recommended production path

```text
LIS -> MLLP/HL7 or FHIR -> integration engine
     -> validate/map units
     -> POST /v1/integrations/hl7 or /v1/integrations/fhir
     -> API -> alert queue -> HIS front-end
```

For PHI, keep everything inside the hospital network; do not send raw messages to a cloud service.
