-- PostgreSQL bootstrap: one schema + one user per service (decision D5, §3.9).
-- Run once as superuser on database `fintech`. Passwords are psql variables, never committed:
--
--   psql -U postgres -d fintech -v ON_ERROR_STOP=1 \
--     -v auth_pwd=... -v customer_pwd=... -v transaction_pwd=... -v risk_pwd=... \
--     -v notification_pwd=... -v audit_pwd=... -v audit_migrator_pwd=... -v mlflow_pwd=... \
--     -f 00_schemas_users.sql
--
-- In Kubernetes the values come from the <service>-db SealedSecrets (P4).

-- Nobody creates objects in `public`.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- ---------------------------------------------------------------------------
-- Regular services: the user owns its schema (Flyway migrations + runtime).
-- No grant on any other schema (no cross-schema access).
-- ---------------------------------------------------------------------------
CREATE ROLE auth_user         LOGIN PASSWORD :'auth_pwd';
CREATE ROLE customer_user     LOGIN PASSWORD :'customer_pwd';
CREATE ROLE transaction_user  LOGIN PASSWORD :'transaction_pwd';
CREATE ROLE risk_user         LOGIN PASSWORD :'risk_pwd';
CREATE ROLE notification_user LOGIN PASSWORD :'notification_pwd';
CREATE ROLE mlflow_user       LOGIN PASSWORD :'mlflow_pwd';

CREATE SCHEMA auth         AUTHORIZATION auth_user;
CREATE SCHEMA customer     AUTHORIZATION customer_user;
CREATE SCHEMA transaction  AUTHORIZATION transaction_user;
CREATE SCHEMA risk         AUTHORIZATION risk_user;
CREATE SCHEMA notification AUTHORIZATION notification_user;
CREATE SCHEMA mlflow       AUTHORIZATION mlflow_user;

ALTER ROLE auth_user         SET search_path = auth;
ALTER ROLE customer_user     SET search_path = customer;
ALTER ROLE transaction_user  SET search_path = transaction;
ALTER ROLE risk_user         SET search_path = risk;
ALTER ROLE notification_user SET search_path = notification;
ALTER ROLE mlflow_user       SET search_path = mlflow;

-- ---------------------------------------------------------------------------
-- Audit: append-only, enforced by the database (§3.4).
--   audit_migrator owns the schema and runs Flyway (DDL).
--   audit_user is the runtime user: INSERT + SELECT only, so even a bug
--   cannot UPDATE or DELETE a trace.
-- ---------------------------------------------------------------------------
CREATE ROLE audit_migrator LOGIN PASSWORD :'audit_migrator_pwd';
CREATE ROLE audit_user     LOGIN PASSWORD :'audit_pwd';

CREATE SCHEMA audit AUTHORIZATION audit_migrator;
GRANT USAGE ON SCHEMA audit TO audit_user;

-- Applies to every table/sequence audit_migrator creates later (Flyway).
ALTER DEFAULT PRIVILEGES FOR ROLE audit_migrator IN SCHEMA audit
    GRANT SELECT, INSERT ON TABLES TO audit_user;
ALTER DEFAULT PRIVILEGES FOR ROLE audit_migrator IN SCHEMA audit
    GRANT USAGE ON SEQUENCES TO audit_user;

ALTER ROLE audit_migrator SET search_path = audit;
ALTER ROLE audit_user     SET search_path = audit;
