# -*- coding: utf-8 -*-
"""Runtime configuration (environment-driven, no secrets in code)."""
from __future__ import annotations

import os
from pathlib import Path

API_KEY = os.getenv("ACCORD_API_KEY", "dev-key-change-me")
AUDIT_LOG = Path(os.getenv("ACCORD_AUDIT_LOG", "audit.jsonl"))
CORS_ORIGINS = [x.strip() for x in os.getenv("ACCORD_CORS_ORIGINS", "http://localhost").split(",") if x.strip()]
MODEL_MODE = os.getenv("ACCORD_MODEL_MODE", "fast")
DISCLAIMER = (
    "Research prototype only. This output is not a diagnosis, does not replace imaging, "
    "endoscopy, pathology or clinical judgement, and must not be used as the sole basis "
    "for referral, treatment or discharge."
)
