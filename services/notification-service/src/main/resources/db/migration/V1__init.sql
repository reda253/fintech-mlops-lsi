-- notification-service schema v1 (owner: notification_user)

CREATE TABLE notifications (
    id               UUID PRIMARY KEY,
    source_event_id  UUID           NOT NULL UNIQUE,   -- one notification per event
    type             VARCHAR(8)     NOT NULL CHECK (type IN ('BLOCAGE', 'REVUE')),
    transaction_id   UUID           NOT NULL,
    amount           NUMERIC(12, 2),
    reason           VARCHAR(24),
    message          VARCHAR(500)   NOT NULL,
    read             BOOLEAN        NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ    NOT NULL DEFAULT now(),
    read_at          TIMESTAMPTZ
);
CREATE INDEX ix_notifications_created ON notifications (created_at DESC);
CREATE INDEX ix_notifications_unread ON notifications (created_at DESC) WHERE NOT read;

-- Idempotent consumer: an eventId already handled is skipped (at-least-once delivery).
CREATE TABLE processed_events (
    event_id      UUID PRIMARY KEY,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
