-- Read-only report. Keep output private; compare it byte for byte on both databases.
\set ON_ERROR_STOP on
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;

-- Count physical tables once, including partition leaves but not their parents.
SELECT format(
    'SELECT json_build_array(''rows'', %L, %L, count(*)) FROM ONLY %I.%I;',
    n.nspname, c.relname, n.nspname, c.relname
)
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
ORDER BY n.nspname COLLATE "C", c.relname COLLATE "C"
\gexec

SELECT format(
    'SELECT json_build_array(''flyway'', %L, installed_rank, version, checksum, success)
     FROM %I.flyway_schema_history ORDER BY installed_rank;',
    n.nspname, n.nspname
)
FROM pg_catalog.pg_class c
JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r' AND c.relname = 'flyway_schema_history'
  AND n.nspname !~ '^pg_' AND n.nspname <> 'information_schema'
ORDER BY n.nspname COLLATE "C"
\gexec

DO $$
BEGIN
    IF NOT has_table_privilege('audit_user', 'audit.audit_events', 'INSERT')
       OR NOT has_table_privilege('audit_user', 'audit.audit_events', 'SELECT')
       OR has_table_privilege('audit_user', 'audit.audit_events', 'UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER, MAINTAIN')
       OR has_any_column_privilege('audit_user', 'audit.audit_events', 'UPDATE, REFERENCES')
    THEN
        RAISE EXCEPTION 'D35: unexpected audit_user privileges';
    END IF;
END $$;

-- Check D47 state without exposing usernames or password hashes.
SELECT json_build_array('auth', count(*),
    count(*) FILTER (WHERE enabled AND 'ADMIN' = ANY(roles)),
    count(*) FILTER (WHERE enabled AND username IN ('admin', 'analyste1', 'simulateur1')))
FROM auth.users;
COMMIT;
