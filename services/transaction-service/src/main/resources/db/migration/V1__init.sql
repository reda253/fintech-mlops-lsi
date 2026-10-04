-- transaction-service schema v1 (owner: transaction_user)

CREATE TABLE transactions (
    id                 UUID PRIMARY KEY,
    trans_num          VARCHAR(64)      NOT NULL,
    customer_id        UUID             NOT NULL,   -- customer-service id, no FK (other schema)
    card_last4         CHAR(4)          NOT NULL,
    trans_date_time    TIMESTAMP        NOT NULL,   -- Sparkov local time
    amount             NUMERIC(12, 2)   NOT NULL CHECK (amount > 0),
    category           VARCHAR(32)      NOT NULL,
    merchant           VARCHAR(128)     NOT NULL,
    merch_lat          DOUBLE PRECISION NOT NULL,
    merch_long         DOUBLE PRECISION NOT NULL,
    status             VARCHAR(16)      NOT NULL DEFAULT 'EN_ATTENTE'
                       CHECK (status IN ('EN_ATTENTE', 'EN_REVUE', 'APPROUVEE', 'BLOQUEE')),
    decision_source    VARCHAR(10)      CHECK (decision_source IN ('AUTO', 'MANUELLE')),
    -- copy of the risk assessment (RiskSummary in the contract)
    risk_decision      VARCHAR(10)      CHECK (risk_decision IN ('APPROUVER', 'REVUE', 'BLOQUER')),
    risk_reason        VARCHAR(24),
    fraud_probability  DOUBLE PRECISION,
    prediction_set     SMALLINT[],
    uncertainty        DOUBLE PRECISION,
    model_version      VARCHAR(64),
    review_id          UUID,
    created_at         TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ      NOT NULL DEFAULT now(),
    version            BIGINT           NOT NULL DEFAULT 0,
    CONSTRAINT uq_transactions_trans_num UNIQUE (trans_num)   -- idempotency key
);
-- Listing by status / time window, and the 30 s EN_ATTENTE re-evaluation job.
CREATE INDEX ix_transactions_status_created ON transactions (status, created_at);
CREATE INDEX ix_transactions_customer ON transactions (customer_id);
CREATE INDEX ix_transactions_trans_date ON transactions (trans_date_time);

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
