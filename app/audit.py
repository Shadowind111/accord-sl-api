# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import AUDIT_LOG

_LOCK = threading.Lock()


def write(event: dict[str, Any]) -> None:
    event = dict(event)
    event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        with AUDIT_LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")


def read(encounter_id: str, limit: int = 100) -> list[dict[str, Any]]:
    if not Path(AUDIT_LOG).exists():
        return []
    out = []
    with AUDIT_LOG.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("encounter_id") == encounter_id:
                out.append(item)
    return out[-limit:]
