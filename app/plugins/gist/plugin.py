# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd

from app.config import DISCLAIMER
from app.plugins.base import RiskModelPlugin
from app.schemas import AlertSpec, PluginResult, ScoreRequest

# release_api is the working directory / package root; gist_runtime is a sibling.
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gist_runtime import predict_t1, predict_t2  # noqa: E402


class GistPlugin(RiskModelPlugin):
    model_id = "gist"

    def __init__(self) -> None:
        self.t1_fields = [k for k in predict_t1.T1_RAW if k != "age"]
        self.t2_fields = [k for k in predict_t2.FRIENDLY if k != "age"]
        self.t1_threshold = float(joblib.load(ROOT / "gist_runtime/models/t1_locked_layers.joblib")["manifest"]["threshold"])
        self.t2_threshold = float(joblib.load(ROOT / "gist_runtime/models/t2_locked_layers.joblib")["manifest"]["threshold"])
        self.manifest = {
            "model_id": "gist",
            "disease": "GIST",
            "version": "t1-r3+t2-v11-fast",
            "status": "research",
            "mode": "fast",
            "tiers": ["T1", "T2"],
            "inputs": {
                "patient": ["age"],
                "t1_labs": self.t1_fields,
                "t2_labs": self.t2_fields,
            },
            "outputs": ["score", "calibrated_score", "flag", "reasons", "missing_inputs"],
            "thresholds": {"T1": self.t1_threshold, "T2": self.t2_threshold},
            "alert_policy": {"default": "queue", "confirmed_high_risk": "banner", "critical": "modal"},
            "disclaimer": DISCLAIMER,
        }

    def _score_frame(self, request: ScoreRequest) -> tuple[str, pd.DataFrame]:
        labs = {k: v for k, v in request.labs.items() if v is not None and v != ""}
        if set(labs) & set(self.t2_fields):
            tier = "T2"
        elif set(labs) & set(self.t1_fields):
            tier = "T1"
        else:
            raise ValueError("No GIST T1 or T2 input fields were supplied")
        row = {"age": request.patient.age, **labs}
        return tier, pd.DataFrame([row])

    @staticmethod
    def _reasons(tier: str, request: ScoreRequest) -> list[str]:
        if tier == "T2":
            keys = [("age", "age"), ("pt_activity", "PT"), ("hs_crp", "hs-CRP"), ("crp", "CRP"), ("sodium", "Na"), ("potassium", "K")]
        else:
            keys = [("age", "age"), ("basophil_pct", "basophil"), ("albumin", "albumin"), ("urine_protein", "urine protein"), ("fecal_occult", "fecal occult blood")]
        out = []
        for key, label in keys:
            value = request.patient.age if key == "age" else request.labs.get(key)
            if value is not None and value != "":
                out.append(f"{label}={value}")
        out.append("input descriptors, not causal explanations")
        return out

    def score(self, request: ScoreRequest) -> PluginResult:
        tier, frame = self._score_frame(request)
        if tier == "T2":
            result = predict_t2.score(frame, mode="fast")
            threshold = self.t2_threshold
            missing = [x for x in self.t2_fields if x not in request.labs]
        else:
            result = predict_t1.score(frame, mode="fast")
            threshold = self.t1_threshold
            missing = [x for x in self.t1_fields if x not in request.labs]
        row = result.iloc[0]
        return PluginResult(
            model_id=self.model_id,
            model_version=self.manifest["version"],
            tier=tier,
            score=float(row["raw_score"]),
            calibrated_score=float(row["calibrated_score"]),
            flag=bool(row["high_risk"]),
            threshold=threshold,
            reasons=self._reasons(tier, request),
            missing_inputs=missing,
            disclaimer=DISCLAIMER,
        )

    def alert_policy(self, result: PluginResult, request: ScoreRequest) -> AlertSpec | None:
        if result.tier != "T2" or not result.flag:
            return None
        channel = "queue"
        if request.context.get("confirmed_high_risk"):
            channel = "banner"
        if request.context.get("critical") and request.context.get("clinician_available"):
            channel = "modal"
        return AlertSpec(
            severity="high",
            channel=channel,
            title="GIST 风险评估提示（研究）",
            body=(
                f"T2 高风险（{result.calibrated_score:.2f}，阈值 {result.threshold:.2f}）。"
                "建议优先评估；本提示不是诊断，不替代影像/内镜/病理。"
            ),
            actions=["refer_specialist", "order_imaging", "defer", "not_relevant"],
            dedup_key=f"gist:T2:{request.encounter_id}",
            suppress_after_action=True,
            ttl_hours=24,
        )
