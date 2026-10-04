-- auth-service schema v1 (owner: auth_user)

CREATE TABLE users (
    id             UUID PRIMARY KEY,
    username       VARCHAR(64)   NOT NULL UNIQUE,
    password_hash  VARCHAR(100)  NOT NULL,          -- BCrypt
    roles          VARCHAR(16)[] NOT NULL,          -- ADMIN, ANALYSTE, SIMULATEUR
    enabled        BOOLEAN       NOT NULL DEFAULT TRUE,
    created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT ck_users_roles CHECK (
        cardinality(roles) > 0
        AND roles <@ ARRAY['ADMIN', 'ANALYSTE', 'SIMULATEUR']::VARCHAR(16)[])
);

CREATE TABLE refresh_tokens (
    id          UUID PRIMARY KEY,
    user_id     UUID         NOT NULL REFERENCES users (id),
    token_hash  CHAR(64)     NOT NULL UNIQUE,       -- SHA-256 of the opaque token, never the token itself
    expires_at  TIMESTAMPTZ  NOT NULL,
    revoked_at  TIMESTAMPTZ,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX ix_refresh_tokens_user ON refresh_tokens (user_id);

-- Transactional outbox (D15, section 3.5): written in the same transaction as the business change,
-- published by the relay every 500 ms with SELECT ... FOR UPDATE SKIP LOCKED.
CREATE TABLE outbox_events (
    id            UUID PRIMARY KEY,                 -- = envelope eventId
    event_type    VARCHAR(64)  NOT NULL,            -- = routing key, e.g. transaction.decided.blocked
    aggregate_id  VARCHAR(64)  NOT NULL,
    payload       JSONB        NOT NULL,            -- full envelope
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ,
    attempts      INT          NOT NULL DEFAULT 0,
    last_error    TEXT
);
-- Relay scan and the outbox_pending gauge only touch unpublished rows.
CREATE INDEX ix_outbox_unpublished ON outbox_events (created_at) WHERE published_at IS NULL;
-- Purge job (published more than 7 days ago).
CREATE INDEX ix_outbox_published_at ON outbox_events (published_at) WHERE published_at IS NOT NULL;
