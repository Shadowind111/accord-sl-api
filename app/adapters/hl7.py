# -*- coding: utf-8 -*-
"""Minimal HL7 v2 ORU^R01 pipe parser -> EventRequest.

Supports the subset needed for a lab-result event: PID-7 birthdate, OBX-3 code,
OBX-5 value. Mapping aliases to API friendly names is intentionally explicit.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.schemas import EventRequest, Patient

HL7_MAP = {
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
    "PT": "pt_activity",
    "PT%": "pt_activity",
    "HS-CRP": "hs_crp",
    "HSCRP": "hs_crp",
    "CRP": "crp",
    "K": "potassium",
    "NA": "sodium",
    "CL": "chloride",
    "CA": "calcium",
    "P": "phosphate",
    "MG": "magnesium",
    "APTT": "aptt",
    "CO2CP": "co2_binding",
    "CO2": "co2_binding",
    "ALT": "alt",
    "ALB": "albumin",
    "BASO%": "basophil_pct",
}


def _age_from_hl7_date(value: str) -> int | None:
    value = value.strip()
    if len(value) < 8 or not value[:8].isdigit():
        return None
    try:
        d = date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return None
    today = date.today()
    return today.year - d.year - ((today.month, today.day) < (d.month, d.day))


def hl7_to_event(message: str, encounter_id: str, model_id: str = "gist", age_override: float | None = None) -> EventRequest:
    age = age_override
    labs: dict[str, Any] = {}
    for raw in message.replace("\n", "\r").split("\r"):
        if not raw.strip():
            continue
        fields = raw.split("|")
        seg = fields[0]
        if seg == "PID" and age is None and len(fields) > 6:
            age = _age_from_hl7_date(fields[6])
        if seg != "OBX" or len(fields) < 6:
            continue
        code_field = fields[3]
        code = code_field.split("^")[0].strip().upper()
        friendly = HL7_MAP.get(code)
        if not friendly:
            # Try the text/name component if the code is local.
            parts = code_field.split("^")
            if len(parts) > 1:
                friendly = HL7_MAP.get(parts[1].strip().upper())
        if not friendly:
            continue
        value = fields[5].strip()
        if value == "":
            continue
        labs[friendly] = value
    if age is None:
        raise ValueError("HL7 message has no PID-7 birthdate and no age override")
    return EventRequest(
        request_id=f"hl7-{encounter_id}",
        encounter_id=encounter_id,
        model_id=model_id,
        patient=Patient(age=float(age)),
        labs=labs,
        context={"source": "hl7"},
    )
