# -*- coding: utf-8 -*-
"""T1-ACCORD-SL scoring entry point (research use only)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

PKG = Path(__file__).resolve().parent
MODELS = PKG / "models"
LAYERS = MODELS / "t1_locked_layers.joblib"
EXPERTS = MODELS / "t1_experts"

T1_RAW = {
    "age": "s0_age_years_raw",
    "basophil_pct": "raw_lab_0cec714c90_first_result",
    "alt": "raw_lab_1494503ceb_first_result",
    "urine_ketone": "raw_lab_1fbbd9a452_first_result",
    "albumin": "raw_lab_2f3b472239_first_result",
    "urine_wbc_esterase_1": "raw_lab_30b906c640_first_result",
    "urine_sg": "raw_lab_510c4cbb3a_first_result",
    "urine_ph": "raw_lab_79e021be49_first_result",
    "urine_wbc_esterase_2": "raw_lab_83d85721fd_first_result",
    "urine_turbidity_1": "raw_lab_84319db108_first_result",
    "urine_bilirubin": "raw_lab_8cd6a20e76_first_result",
    "urine_turbidity_2": "raw_lab_a1818728f4_first_result",
    "urine_occult_blood_1": "raw_lab_b2cfee4c81_first_result",
    "urine_rbc": "raw_lab_ba778ae8ba_first_result",
    "urine_color": "raw_lab_c880bcdcd5_first_result",
    "urobilinogen": "raw_lab_ccca5ba650_first_result",
    "urine_protein": "raw_lab_ce5c34a1b2_first_result",
    "fecal_occult": "raw_lab_d1e4a02e39_first_result",
    "urine_nitrite": "raw_lab_e06ab6e8c4_first_result",
    "urine_glucose": "raw_lab_e7685e977d_first_result",
    "urine_occult_rbc": "raw_lab_efe8a63528_first_result",
}
FAST = ["ebm_ga2m_interpretable", "xgboost_hist_balanced"]


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out = out.rename(columns={k: v for k, v in T1_RAW.items() if k in out.columns})
    for v in T1_RAW.values():
        if v not in out.columns:
            out[v] = np.nan
    return out


def score(df: pd.DataFrame, mode: str = "fast") -> pd.DataFrame:
    layers = joblib.load(LAYERS)
    weights = layers["manifest"]["weights"]
    cal = layers["calibrator"]
    if not hasattr(cal, "multi_class"):
        cal.multi_class = "auto"
    X = prepare(df)
    names = FAST if mode == "fast" else list(weights)
    w = {k: float(weights[k]) for k in names}
    total = sum(w.values())
    w = {k: v / total for k, v in w.items()}
    probs = {}
    for name in names:
        art = joblib.load(EXPERTS / f"{name}.joblib")
        ncols, ccols = art["numeric_cols"], art["categorical_cols"]
        num = X[ncols].copy()
        for c in ncols:
            s = num[c].astype(str).str.strip().str.replace(r"^[<>]\s*", "", regex=True)
            num[c] = pd.to_numeric(s, errors="coerce")
        cat = X[ccols].astype(object)
        num_t = art["numeric_scaler"].transform(art["numeric_imputer"].transform(num))
        cat_t = art["cat_onehot"].transform(art["cat_imputer"].transform(cat))
        Xp = np.hstack([num_t, cat_t])
        probs[name] = art["estimator"].predict_proba(Xp)[:, 1]
    fused = np.zeros(len(X), dtype=float)
    for k, p in probs.items():
        fused += w[k] * p
    fused = np.clip(fused, 1e-6, 1 - 1e-6)
    logit = np.log(fused / (1 - fused)).reshape(-1, 1)
    calibrated = cal.predict_proba(logit)[:, 1]
    threshold = float(layers["manifest"]["threshold"])
    band = float(layers["manifest"]["deferral_band"])
    out = pd.DataFrame({
        "raw_score": fused,
        "calibrated_score": calibrated,
        "high_risk": (calibrated >= threshold).astype(int),
        "near_threshold": (np.abs(calibrated - threshold) <= band).astype(int),
    })
    for k, p in probs.items():
        out[f"{k}__probability"] = p
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--out", default="t1_scores.csv")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    args = ap.parse_args()
    df = pd.read_csv(args.input)
    scored = score(df, mode=args.mode)
    pd.concat([df.reset_index(drop=True), scored], axis=1).to_csv(args.out, index=False, encoding="utf-8-sig")
    print(json.dumps({
        "mode": args.mode,
        "n": len(df),
        "mean_calibrated_score": round(float(scored["calibrated_score"].mean()), 4),
        "high_risk_n": int(scored["high_risk"].sum()),
        "note": "Research use only. Fast mode is a two-expert demonstration approximation.",
    }, ensure_ascii=False, indent=2))
    print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
