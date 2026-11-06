# -*- coding: utf-8 -*-
"""Minimal FHIR R4 Observation -> EventRequest adapter.

This is deliberately small: map LOINC/local codes to the API's friendly names.
Hospital integration engines normally do this mapping; this module is a reference.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.schemas import EventRequest, Patient

# LOINC and common local aliases -> API friendly name.
LOINC_MAP = {
    "2823-3": "potassium",
    "17861-6": "calcium",
    "3173-2": "aptt",
    "2777-1": "phosphate",
    "1963-8": "co2_binding",
    "2075-0": "chloride",
    "1988-5": "crp",
    "30522-7": "hs_crp",
    "19123-9": "magnesium",
    "2951-2": "sodium",
    "5902-2": "pt_activity",
    "1742-6": "alt",
    "1751-7": "albumin",
    "706-2": "basophil_pct",
}
LOCAL_ALIASES = {
    "pt": "pt_activity",
    "pt%": "pt_activity",
    "hs-crp": "hs_crp",
    "hscrp": "hs_crp",
    "crp": "crp",
    "k": "potassium",
    "na": "sodium",
    "cl": "chloride",
    "ca": "calcium",
    "p": "phosphate",
    "mg": "magnesium",
    "aptt": "aptt",
    "co2cp": "co2_binding",
    "co2": "co2_binding",
    "alt": "alt",
    "albumin": "albumin",
    "basophil": "basophil_pct",
}


def _age_from_birthdate(value: str) -> int | None:
    try:
        d = date.fromisoformat(value[:10])
    except ValueError:
        return None
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def _value(obs: dict[str, Any]) -> Any:
    if "valueQuantity" in obs:
        return obs["valueQuantity"].get("value")
    if "valueString" in obs:
        return obs["valueString"]
    if "valueCodeableConcept" in obs:
        cc = obs["valueCodeableConcept"]
        return cc.get("text") or (cc.get("coding") or [{}])[0].get("display")
    return None


def fhir_to_event(bundle: dict[str, Any], encounter_id: str, model_id: str = "gist", age_override: float | None = None) -> EventRequest:
    entries = bundle.get("entry") or []
    age = age_override
    labs: dict[str, Any] = {}
    for entry in entries:
        res = entry.get("resource") or {}
        rtype = res.get("resourceType")
        if rtype == "Patient" and age is None and res.get("birthDate"):
            age = _age_from_birthdate(res["birthDate"])
        if rtype != "Observation":
            continue
        code = None
        for coding in (res.get("code") or {}).get("coding") or []:
            candidate = str(coding.get("code") or "")
            display = str(coding.get("display") or "").lower()
            if candidate in LOINC_MAP:
                code = LOINC_MAP[candidate]
                break
            if display in LOCAL_ALIASES:
                code = LOCAL_ALIASES[display]
                break
        if code:
            val = _value(res)
            if val is not None:
                labs[code] = val
    if age is None:
        raise ValueError("FHIR bundle has no Patient.birthDate and no age override")
    return EventRequest(
        request_id=f"fhir-{encounter_id}",
        encounter_id=encounter_id,
        model_id=model_id,
        patient=Patient(age=float(age)),
        labs=labs,
        context={"source": "fhir"},
    )
