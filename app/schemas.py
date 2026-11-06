# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Patient(BaseModel):
    age: float = Field(..., ge=0, le=120, description="Age in years")


class ScoreRequest(BaseModel):
    request_id: str = Field(..., examples=["req-2026-001"])
    encounter_id: str = Field(..., examples=["enc-001"])
    patient: Patient
    labs: dict[str, Any] = Field(default_factory=dict, description="Friendly lab names and values")
    context: dict[str, Any] = Field(default_factory=dict)


class PluginResult(BaseModel):
    model_id: str
    model_version: str
    tier: Literal["T1", "T2", "single"]
    score: float
    calibrated_score: float
    flag: bool
    threshold: float
    reasons: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    disclaimer: str


class AlertSpec(BaseModel):
    severity: Literal["info", "medium", "high", "critical"]
    channel: Literal["queue", "banner", "modal"]
    title: str
    body: str
    actions: list[str] = Field(default_factory=list)
    dedup_key: str
    suppress_after_action: bool = True
    ttl_hours: int = 24


class Alert(BaseModel):
    alert_id: str
    encounter_id: str
    model_id: str
    tier: str
    severity: str
    channel: str
    title: str
    body: str
    actions: list[str]
    status: Literal["open", "acknowledged", "dismissed"] = "open"
    created_at: datetime
    dedup_key: str
    actor: str | None = None


class ScoreResponse(BaseModel):
    request_id: str
    encounter_id: str
    result: PluginResult
    alert: Alert | None = None


class AckRequest(BaseModel):
    actor: str | None = None
    reason: str | None = None


class EventRequest(ScoreRequest):
    model_id: str = "gist"
