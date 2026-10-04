-- audit-service schema v1 (owner: audit_migrator; runtime audit_user has INSERT + SELECT only)
-- Idempotency comes from the unique event_id + INSERT ... ON CONFLICT (event_id) DO NOTHING,
-- so no processed_events table is needed here.

CREATE TABLE audit_events (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id        UUID          NOT NULL UNIQUE,
    type            VARCHAR(64)   NOT NULL,
    producer        VARCHAR(32)   NOT NULL,
    entity_type     VARCHAR(16)   CHECK (entity_type IN ('TRANSACTION', 'REVIEW', 'USER')),
    entity_id       VARCHAR(64),
    actor           VARCHAR(64),
    model_version   VARCHAR(64),
    correlation_id  UUID,
    payload         JSONB         NOT NULL,
    occurred_at     TIMESTAMPTZ   NOT NULL,
    received_at     TIMESTAMPTZ   NOT NULL DEFAULT now()
);
CREATE INDEX ix_audit_type_occurred ON audit_events (type, occurred_at DESC);
CREATE INDEX ix_audit_occurred ON audit_events (occurred_at DESC);
CREATE INDEX ix_audit_entity ON audit_events (entity_id);
CREATE INDEX ix_audit_actor ON audit_events (actor);
CREATE INDEX ix_audit_correlation ON audit_events (correlation_id);
