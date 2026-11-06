# -*- coding: utf-8 -*-
"""Durable alert/pending stores.

Default: in-memory (tests, single-process demo).
Set ACCORD_DATABASE_URL=postgresql://... to use PostgreSQL.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Protocol

from app.schemas import Alert, AlertSpec, PluginResult

try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    from psycopg_pool import ConnectionPool
except Exception:  # pragma: no cover - optional dependency
    psycopg = None
    ConnectionPool = None
    Jsonb = None
    dict_row = None


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS accord_alerts (
    alert_id TEXT PRIMARY KEY,
    encounter_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    tier TEXT NOT NULL,
    severity TEXT NOT NULL,
    channel TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    actions JSONB NOT NULL DEFAULT '[]'::jsonb,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    dedup_key TEXT NOT NULL UNIQUE,
    actor TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS accord_alerts_status_idx ON accord_alerts(status);
CREATE INDEX IF NOT EXISTS accord_alerts_encounter_idx ON accord_alerts(encounter_id);

CREATE TABLE IF NOT EXISTS accord_pending_t2 (
    encounter_id TEXT PRIMARY KEY,
    request_id TEXT,
    score DOUBLE PRECISION,
    flag BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


class AlertStore(Protocol):
    def create(self, encounter_id: str, result: PluginResult, spec: AlertSpec) -> Alert: ...
    def list(self, status: str | None = None) -> list[Alert]: ...
    def get(self, alert_id: str) -> Alert | None: ...
    def acknowledge(self, alert_id: str, actor: str | None = None) -> Alert | None: ...
    def dismiss(self, alert_id: str, actor: str | None = None) -> Alert | None: ...
    def set_pending(self, encounter_id: str, request_id: str, score: float) -> None: ...
    def get_pending(self, encounter_id: str) -> dict | None: ...
    def clear_pending(self, encounter_id: str) -> None: ...


class MemoryStore:
    def __init__(self) -> None:
        self._alerts: dict[str, Alert] = {}
        self._dedup: dict[str, str] = {}
        self._pending: dict[str, dict] = {}

    def create(self, encounter_id: str, result: PluginResult, spec: AlertSpec) -> Alert:
        existing = self._dedup.get(spec.dedup_key)
        if existing and existing in self._alerts and self._alerts[existing].status == "open":
            return self._alerts[existing]
        alert = Alert(
            alert_id=f"alert-{uuid.uuid4().hex[:12]}",
            encounter_id=encounter_id,
            model_id=result.model_id,
            tier=result.tier,
            severity=spec.severity,
            channel=spec.channel,
            title=spec.title,
            body=spec.body,
            actions=spec.actions,
            status="open",
            created_at=datetime.now(timezone.utc),
            dedup_key=spec.dedup_key,
        )
        self._alerts[alert.alert_id] = alert
        self._dedup[spec.dedup_key] = alert.alert_id
        return alert

    def list(self, status: str | None = None) -> list[Alert]:
        values = list(self._alerts.values())
        if status:
            values = [a for a in values if a.status == status]
        return sorted(values, key=lambda a: a.created_at, reverse=True)

    def get(self, alert_id: str) -> Alert | None:
        return self._alerts.get(alert_id)

    def acknowledge(self, alert_id: str, actor: str | None = None) -> Alert | None:
        alert = self._alerts.get(alert_id)
        if alert is None:
            return None
        alert.status = "acknowledged"
        alert.actor = actor
        return alert

    def dismiss(self, alert_id: str, actor: str | None = None) -> Alert | None:
        alert = self._alerts.get(alert_id)
        if alert is None:
            return None
        alert.status = "dismissed"
        alert.actor = actor
        return alert

    def set_pending(self, encounter_id: str, request_id: str, score: float) -> None:
        self._pending[encounter_id] = {"request_id": request_id, "score": score, "flag": True}

    def get_pending(self, encounter_id: str) -> dict | None:
        return self._pending.get(encounter_id)

    def clear_pending(self, encounter_id: str) -> None:
        self._pending.pop(encounter_id, None)


class PostgresStore:
    def __init__(self, dsn: str) -> None:
        if psycopg is None:
            raise RuntimeError("psycopg is not installed; install requirements.txt")
        self._pool = ConnectionPool(dsn, min_size=1, max_size=5, open=True)
        with self._pool.connection() as conn:
            conn.execute(SCHEMA_SQL)

    @staticmethod
    def _row_to_alert(row: dict[str, Any]) -> Alert:
        return Alert(
            alert_id=row["alert_id"],
            encounter_id=row["encounter_id"],
            model_id=row["model_id"],
            tier=row["tier"],
            severity=row["severity"],
            channel=row["channel"],
            title=row["title"],
            body=row["body"],
            actions=list(row["actions"] or []),
            status=row["status"],
            created_at=row["created_at"],
            dedup_key=row["dedup_key"],
            actor=row.get("actor"),
        )

    def create(self, encounter_id: str, result: PluginResult, spec: AlertSpec) -> Alert:
        alert_id = f"alert-{uuid.uuid4().hex[:12]}"
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    INSERT INTO accord_alerts
                      (alert_id, encounter_id, model_id, tier, severity, channel, title, body, actions, status, dedup_key)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'open',%s)
                    ON CONFLICT (dedup_key) DO NOTHING
                    RETURNING *
                    """,
                    (alert_id, encounter_id, result.model_id, result.tier, spec.severity, spec.channel,
                     spec.title, spec.body, Jsonb(spec.actions), spec.dedup_key),
                )
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT * FROM accord_alerts WHERE dedup_key=%s", (spec.dedup_key,))
                    row = cur.fetchone()
                return self._row_to_alert(row)

    def list(self, status: str | None = None) -> list[Alert]:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                if status:
                    cur.execute("SELECT * FROM accord_alerts WHERE status=%s ORDER BY created_at DESC", (status,))
                else:
                    cur.execute("SELECT * FROM accord_alerts ORDER BY created_at DESC")
                return [self._row_to_alert(r) for r in cur.fetchall()]

    def get(self, alert_id: str) -> Alert | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM accord_alerts WHERE alert_id=%s", (alert_id,))
                row = cur.fetchone()
                return self._row_to_alert(row) if row else None

    def acknowledge(self, alert_id: str, actor: str | None = None) -> Alert | None:
        return self._set_status(alert_id, "acknowledged", actor)

    def dismiss(self, alert_id: str, actor: str | None = None) -> Alert | None:
        return self._set_status(alert_id, "dismissed", actor)

    def _set_status(self, alert_id: str, status: str, actor: str | None) -> Alert | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "UPDATE accord_alerts SET status=%s, actor=%s, updated_at=now() WHERE alert_id=%s RETURNING *",
                    (status, actor, alert_id),
                )
                row = cur.fetchone()
                return self._row_to_alert(row) if row else None

    def set_pending(self, encounter_id: str, request_id: str, score: float) -> None:
        with self._pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO accord_pending_t2 (encounter_id, request_id, score, flag)
                VALUES (%s,%s,%s,true)
                ON CONFLICT (encounter_id) DO UPDATE
                  SET request_id=EXCLUDED.request_id, score=EXCLUDED.score, flag=true, updated_at=now()
                """,
                (encounter_id, request_id, score),
            )

    def get_pending(self, encounter_id: str) -> dict | None:
        with self._pool.connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM accord_pending_t2 WHERE encounter_id=%s", (encounter_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def clear_pending(self, encounter_id: str) -> None:
        with self._pool.connection() as conn:
            conn.execute("DELETE FROM accord_pending_t2 WHERE encounter_id=%s", (encounter_id,))


def get_store() -> AlertStore:
    import os

    dsn = os.getenv("ACCORD_DATABASE_URL", "").strip()
    if dsn:
        return PostgresStore(dsn)
    return MemoryStore()
