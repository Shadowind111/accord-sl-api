# -*- coding: utf-8 -*-
from __future__ import annotations

from abc import ABC, abstractmethod

from app.schemas import AlertSpec, PluginResult, ScoreRequest


class RiskModelPlugin(ABC):
    """Contract every disease/model plugin must implement."""

    model_id: str
    manifest: dict

    @abstractmethod
    def score(self, request: ScoreRequest) -> PluginResult:
        raise NotImplementedError

    def alert_policy(self, result: PluginResult, request: ScoreRequest) -> AlertSpec | None:
        """Return an alert specification, or None for a silent/backend-only result."""
        return None
