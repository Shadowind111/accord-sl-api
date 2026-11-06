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
