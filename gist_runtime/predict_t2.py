# -*- coding: utf-8 -*-
"""T2-ACCORD-SL scoring entry point (research use only).

The script loads the locked T2 v11 expert artifacts, computes the weighted
ensemble, applies the locked calibration and returns calibrated scores.

Two modes are available:
  --fast   EBM + random forest only (renormalised weights); quick demo, not the
           locked five-expert ensemble.
  --full   all five locked experts (EBM, TabPFN, TabDPT, AutoGluon, random forest).

The full mode requires the original project environment and model artifacts.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

# The expert artifacts were pickled with modules from the v7 code tree.
V7_CODE = Path(r"D:\pythonProject\GIST_project_v6\v7\scripts")
if V7_CODE.exists():
    sys.path.insert(0, str(V7_CODE))

PKG = Path(__file__).resolve().parent
_LOCAL_MODELS = PKG / "models"
if _LOCAL_MODELS.exists():
    DEFAULT_ROOT = _LOCAL_MODELS
    DEFAULT_LAYERS = _LOCAL_MODELS / "t2_locked_layers.joblib"
    DEFAULT_EXPERTS = _LOCAL_MODELS / "experts"
else:
    DEFAULT_ROOT = Path(os.environ.get("T2_ROOT", r"D:\pythonProject\v10\v11_t2_numeric_20261104\full_relock_v3"))
    DEFAULT_LAYERS = Path(os.environ.get("T2_LAYERS", str(DEFAULT_ROOT / "accord_sl" / "t2_original_accord_sl" / "t2_original_accord_sl_locked_layers.joblib")))
    DEFAULT_EXPERTS = Path(os.environ.get("T2_EXPERTS", str(DEFAULT_ROOT / "models" / "t2_expert_pool" / "expert_model_artifacts")))

FRIENDLY = {
    "age": "s0_age_years_raw",
    "pt_activity": "raw_lab_02b4c70e60_first_result",
    "hs_crp": "raw_lab_0e007fa586_first_result",
    "potassium": "raw_lab_15b244e231_first_result",
    "calcium": "raw_lab_1b2ae3b1ce_first_result",
    "aptt": "raw_lab_30ef0a2b99_first_result",
    "phosphate": "raw_lab_4d6eb6773c_first_result",
    "co2_binding": "raw_lab_50206d459c_first_result",
    "chloride": "raw_lab_6f82e52447_first_result",
    "crp": "raw_lab_9669c140d7_first_result",
    "magnesium": "raw_lab_a615156159_first_result",
    "sodium": "raw_lab_b7e6d36365_first_result",
}

FAST_EXPERTS = ["ebm_ga2m_interpretable", "random_forest_balanced"]


def load_assets(layers_path: Path = DEFAULT_LAYERS, experts_dir: Path = DEFAULT_EXPERTS):
    layers = joblib.load(layers_path)
    weights = layers["manifest"]["weights"]
    calibrator = layers["calibrator"]
    return layers, weights, calibrator, experts_dir


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Rename friendly columns to the locked raw feature names."""
    out = df.copy()
    rename = {k: v for k, v in FRIENDLY.items() if k in out.columns}
    out = out.rename(columns=rename)
    missing = [v for v in FRIENDLY.values() if v not in out.columns]
    if missing:
        for c in missing:
            out[c] = np.nan
    return out


def sanitize_numeric(df: pd.DataFrame) -> pd.DataFrame:
    """Strip < / > prefixes and coerce the locked features to numeric."""
    out = df.copy()
    for c in FRIENDLY.values():
        if c not in out.columns:
            continue
        s = out[c].astype(str).str.strip()
        s = s.str.replace(r"^[<>]\s*", "", regex=True).str.replace(r"[↑↓]", "", regex=True)
        out[c] = pd.to_numeric(s, errors="coerce")
    return out


def score(df: pd.DataFrame, mode: str = "fast", layers_path: Path = DEFAULT_LAYERS,
          experts_dir: Path = DEFAULT_EXPERTS) -> pd.DataFrame:
    layers, weights, calibrator, experts_dir = load_assets(layers_path, experts_dir)
    # sklearn 1.7 compatibility for calibrators pickled with 1.8
    if not hasattr(calibrator, "multi_class"):
        calibrator.multi_class = "auto"
    X = prepare(df)
    X = sanitize_numeric(X)
    names = FAST_EXPERTS if mode == "fast" else [k for k in weights]
    w = {k: float(weights[k]) for k in names}
    total = sum(w.values())
    w = {k: v / total for k, v in w.items()}

    probs = {}
    for name in names:
        artifact = joblib.load(experts_dir / f"{name}.joblib")
        cols = artifact["feature_names"]
        for c in cols:
            if c not in X.columns:
                X[c] = np.nan
        Xp = artifact["preprocessor"].transform(X[cols])
        probs[name] = artifact["estimator"].predict_proba(Xp)[:, 1]

    fused = np.zeros(len(X), dtype=float)
    for name, p in probs.items():
        fused += w[name] * p
    fused = np.clip(fused, 1e-6, 1 - 1e-6)
    logit = np.log(fused / (1 - fused)).reshape(-1, 1)
    calibrated = calibrator.predict_proba(logit)[:, 1]

    out = pd.DataFrame({
        "raw_score": fused,
        "calibrated_score": calibrated,
        "high_risk": (calibrated >= float(layers["manifest"]["threshold"])).astype(int),
        "near_threshold": (np.abs(calibrated - float(layers["manifest"]["threshold"])) <= float(layers["manifest"]["deferral_band"])).astype(int),
    })
    for name, p in probs.items():
        out[f"{name}__probability"] = p
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="CSV with 11 T2 items + age (friendly or raw names)")
    ap.add_argument("--out", default="t2_scores.csv")
    ap.add_argument("--mode", choices=["fast", "full"], default="fast")
    ap.add_argument("--layers", default=str(DEFAULT_LAYERS))
    ap.add_argument("--experts", default=str(DEFAULT_EXPERTS))
    args = ap.parse_args()

    df = pd.read_csv(args.input)
    scored = score(df, mode=args.mode, layers_path=Path(args.layers), experts_dir=Path(args.experts))
    out = pd.concat([df.reset_index(drop=True), scored], axis=1)
    out.to_csv(args.out, index=False, encoding="utf-8-sig")
    print(json.dumps({
        "mode": args.mode,
        "n": len(out),
        "mean_calibrated_score": round(float(out["calibrated_score"].mean()), 4),
        "high_risk_n": int(out["high_risk"].sum()),
        "note": "Research use only. Fast mode is a demonstration approximation, not the locked five-expert ensemble.",
    }, ensure_ascii=False, indent=2))
    print(f"saved {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
