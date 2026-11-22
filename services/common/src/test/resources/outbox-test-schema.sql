-- Same DDL as the producers' and consumers' V1 migrations (outbox_events, processed_events).
DROP TABLE IF EXISTS outbox_events;
CREATE TABLE outbox_events (
    id            UUID PRIMARY KEY,
    event_type    VARCHAR(64)  NOT NULL,
    aggregate_id  VARCHAR(64)  NOT NULL,
    payload       JSONB        NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ,
    attempts      INT          NOT NULL DEFAULT 0,
    last_error    TEXT
);
CREATE INDEX ix_outbox_unpublished ON outbox_events (created_at) WHERE published_at IS NULL;
CREATE INDEX ix_outbox_published_at ON outbox_events (published_at) WHERE published_at IS NOT NULL;

DROP TABLE IF EXISTS processed_events;
CREATE TABLE processed_events (
    event_id      UUID PRIMARY KEY,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Business table of the fake producer, to show the event and the change commit or roll back together.
DROP TABLE IF EXISTS business_rows;
CREATE TABLE business_rows (id UUID PRIMARY KEY);
