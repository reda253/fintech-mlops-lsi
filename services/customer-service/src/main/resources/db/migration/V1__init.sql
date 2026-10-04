-- customer-service schema v1 (owner: customer_user)
-- Sparkov customers are loaded by a later data migration (V2, S4).

CREATE TABLE customers (
    id                UUID PRIMARY KEY,
    card_fingerprint  CHAR(64)         NOT NULL UNIQUE,  -- HMAC-SHA256(cc_num) hex; the card number is never stored
    card_last4        CHAR(4)          NOT NULL,
    first_name        VARCHAR(64)      NOT NULL,
    last_name         VARCHAR(64)      NOT NULL,
    gender            CHAR(1)          NOT NULL CHECK (gender IN ('M', 'F')),
    dob               DATE             NOT NULL,
    job               VARCHAR(128)     NOT NULL,
    street            VARCHAR(128)     NOT NULL,
    city              VARCHAR(64)      NOT NULL,
    state             CHAR(2)          NOT NULL,
    zip               VARCHAR(10)      NOT NULL,
    city_pop          INT              NOT NULL CHECK (city_pop >= 0),
    latitude          DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude         DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    created_at        TIMESTAMPTZ      NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ      NOT NULL DEFAULT now(),
    version           BIGINT           NOT NULL DEFAULT 0
);
CREATE INDEX ix_customers_last_name ON customers (lower(last_name));
CREATE INDEX ix_customers_state_city ON customers (state, city);
CREATE INDEX ix_customers_card_last4 ON customers (card_last4);
