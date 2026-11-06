# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class FhirIngestRequest(BaseModel):
    bundle: dict[str, Any] = Field(..., description="FHIR R4 Bundle")
    encounter_id: str
    model_id: str = "gist"
    age: float | None = Field(default=None, ge=0, le=120, description="Optional age override")


class Hl7IngestRequest(BaseModel):
    message: str = Field(..., description="HL7 v2 ORU^R01 pipe message")
    encounter_id: str
    model_id: str = "gist"
    age: float | None = Field(default=None, ge=0, le=120, description="Optional age override")
