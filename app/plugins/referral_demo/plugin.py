# -*- coding: utf-8 -*-
"""A deliberately non-clinical demo plugin proving the registry slot works."""
from __future__ import annotations

import math

from app.config import DISCLAIMER
from app.plugins.base import RiskModelPlugin
from app.schemas import AlertSpec, PluginResult, ScoreRequest


class ReferralDemoPlugin(RiskModelPlugin):
    model_id = "referral_demo"

    def __init__(self) -> None:
        self.manifest = {
            "model_id": self.model_id,
            "disease": "general referral (DEMO ONLY)",
            "version": "0.1-demo",
            "status": "demo-not-for-clinical-use",
            "mode": "demo",
            "inputs": {"patient": ["age"], "labs": ["crp"]},
            "outputs": ["score", "flag"],
            "thresholds": {"single": 0.30},
            "alert_policy": {"default": "queue"},
            "disclaimer": "DEMO PLUGIN — replace with a validated model before any use.",
        }

    def score(self, request: ScoreRequest) -> PluginResult:
        age = float(request.patient.age)
        crp = float(request.labs.get("crp") or 0)
        z = -4.0 + 0.03 * age + 0.02 * crp
        p = 1.0 / (1.0 + math.exp(-max(min(z, 30), -30)))
        return PluginResult(
            model_id=self.model_id,
            model_version=self.manifest["version"],
            tier="single",
            score=p,
            calibrated_score=p,
            flag=p >= 0.30,
            threshold=0.30,
            reasons=[f"age={age}", f"crp={crp}", "demo-only inputs"],
            missing_inputs=[x for x in ["crp"] if x not in request.labs],
            disclaimer="DEMO PLUGIN — not a validated clinical model. " + DISCLAIMER,
        )

    def alert_policy(self, result: PluginResult, request: ScoreRequest) -> AlertSpec | None:
        if not result.flag:
            return None
        return AlertSpec(
            severity="medium",
            channel="queue",
            title="转诊风险提示（演示插件）",
            body="演示插件输出；不是临床模型。请替换为经过验证的模型后再使用。",
            actions=["review", "dismiss"],
            dedup_key=f"{self.model_id}:{request.encounter_id}",
            ttl_hours=24,
        )
