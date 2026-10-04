-- risk-service schema v1 (owner: risk_user)

CREATE TABLE assessments (
    id                 UUID PRIMARY KEY,
    transaction_id     UUID             NOT NULL UNIQUE,  -- idempotent /internal/risk/assess
    trans_num          VARCHAR(64)      NOT NULL UNIQUE,  -- join key for chargeback feedback
    customer_id        UUID             NOT NULL,
    amount             NUMERIC(12, 2)   NOT NULL,
    category           VARCHAR(32)      NOT NULL,
    trans_date_time    TIMESTAMP        NOT NULL,
    decision           VARCHAR(10)      NOT NULL CHECK (decision IN ('APPROUVER', 'REVUE', 'BLOQUER')),
    reason             VARCHAR(24)      NOT NULL CHECK (reason IN
                       ('MODELE_CONFIANT', 'MODELE_INCERTAIN', 'ML_INDISPONIBLE', 'CLIENT_INDISPONIBLE')),
    fraud_probability  DOUBLE PRECISION,                  -- null when ML_INDISPONIBLE
    prediction_set     SMALLINT[],
    uncertainty        DOUBLE PRECISION,
    uncertainty_level  VARCHAR(8)       CHECK (uncertainty_level IN ('FAIBLE', 'ELEVEE')),
    alpha              DOUBLE PRECISION,
    model_name         VARCHAR(64),
    model_version      VARCHAR(32),
    ml_latency_ms      DOUBLE PRECISION,
    assessed_at        TIMESTAMPTZ      NOT NULL DEFAULT now()
);
CREATE INDEX ix_assessments_assessed_at ON assessments (assessed_at);   -- /stats windows

CREATE TABLE reviews (
    id              UUID PRIMARY KEY,
    assessment_id   UUID          NOT NULL UNIQUE REFERENCES assessments (id),
    transaction_id  UUID          NOT NULL UNIQUE,
    status          VARCHAR(8)    NOT NULL DEFAULT 'OUVERTE' CHECK (status IN ('OUVERTE', 'TRAITEE')),
    analyst         VARCHAR(64),
    final_decision  VARCHAR(10)   CHECK (final_decision IN ('APPROUVEE', 'BLOQUEE')),
    comment         VARCHAR(1000),
    opened_at       TIMESTAMPTZ   NOT NULL DEFAULT now(),
    closed_at       TIMESTAMPTZ,
    version         BIGINT        NOT NULL DEFAULT 0,      -- JPA @Version: second analyst gets 409
    CONSTRAINT ck_reviews_closed CHECK ((status = 'TRAITEE') = (final_decision IS NOT NULL))
);
CREATE INDEX ix_reviews_status_opened ON reviews (status, opened_at);

-- Simulated chargebacks (D19). A label may arrive before its assessment: matched later.
CREATE TABLE feedback (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trans_num    VARCHAR(64)  NOT NULL UNIQUE,              -- idempotent feedback
    is_fraud     BOOLEAN      NOT NULL,
    reported_at  TIMESTAMPTZ,
    received_at  TIMESTAMPTZ  NOT NULL DEFAULT now(),
    matched_at   TIMESTAMPTZ
);
CREATE INDEX ix_feedback_unmatched ON feedback (received_at) WHERE matched_at IS NULL;
CREATE INDEX ix_feedback_received ON feedback (received_at);   -- /internal/risk/labels?since=

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

-- Idempotent consumer: an eventId already handled is skipped (at-least-once delivery).
CREATE TABLE processed_events (
    event_id      UUID PRIMARY KEY,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
