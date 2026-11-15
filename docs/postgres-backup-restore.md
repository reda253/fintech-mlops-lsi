# PostgreSQL backup and restore rehearsal (Refs #40)

This is a logical backup of the `fintech` database and a restore into a new,
disconnected database on the same PostgreSQL 17 instance. It does not overwrite
the source or cover loss of the instance. Run only in an approved maintenance
window: the restore consumes CPU, disk and WAL on the shared instance. Prefer
a disposable separate instance for a full disaster recovery rehearsal.

## Preconditions

- Confirm the pod, source database, free disk space (including restore/WAL),
  and who may handle the backup. Suspend application and background writes
  from the source report through the dump and comparison. A dump is internally
  consistent even with concurrent writes, but separate counts can then differ.
- Use a new private, access-restricted directory on encrypted storage outside
  any checkout and outside the cluster. Keep a protected copy off the host
  according to team policy. Dumps include application data and password hashes;
  never upload them to Git, chat, or CI artifacts.
- This dump excludes global roles/passwords. Same-instance roles already exist.
  For a separate instance, provision roles using the matching bootstrap and
  approved Secrets before restoring; do not rerun bootstrap on the live database.
  Object owners and ACLs are restored, but database-level settings and CONNECT
  grants must be reviewed separately. Restore only a trusted archive.

## Backup and comparison (Windows CMD)

Run these commands from the repository root, one at a time. Stop on errors.
Use CMD redirection for the binary stream, not a PowerShell text pipeline.
Choose a new folder for each run. Stop if mkdir reports it already exists.

```cmd
set "BACKUP_DIR=%LOCALAPPDATA%\fintech-backups\before-first-sync-01"
mkdir "%BACKUP_DIR%"
kubectl --context kind-fintech -n data exec -i postgres-0 -- psql -XqAt -v ON_ERROR_STOP=1 -U postgres -d fintech < deploy\sql\verify_postgres_restore.sql > "%BACKUP_DIR%\source.txt"
kubectl --context kind-fintech -n data exec postgres-0 -- pg_dump -U postgres -Fc -d fintech > "%BACKUP_DIR%\fintech.dump.part"
kubectl --context kind-fintech -n data exec -i postgres-0 -- pg_restore --list < "%BACKUP_DIR%\fintech.dump.part" > "%BACKUP_DIR%\toc.txt"
ren "%BACKUP_DIR%\fintech.dump.part" fintech.dump
certutil -hashfile "%BACKUP_DIR%\fintech.dump" SHA256
```

A failed dump can leave a partial file: never rename it or treat it as a backup.
The table of contents is a format check, not proof of restoration. Record the
checksum privately and verify it after copying the archive.

## Restore and verify

Create the fixed scratch database only if it does not already exist. If
`createdb` fails, stop; never restore into or drop a pre-existing database.
No service should use this name. Revoking public CONNECT keeps ordinary
application roles out; the postgres superuser can still restore and verify.

```cmd
kubectl --context kind-fintech -n data exec postgres-0 -- createdb -U postgres -T template0 fintech_restore_test
kubectl --context kind-fintech -n data exec postgres-0 -- psql -X -v ON_ERROR_STOP=1 -U postgres -d postgres -c "REVOKE CONNECT ON DATABASE fintech_restore_test FROM PUBLIC;"
echo Restore start: %DATE% %TIME%
kubectl --context kind-fintech -n data exec -i postgres-0 -- pg_restore -U postgres --single-transaction --exit-on-error -d fintech_restore_test < "%BACKUP_DIR%\fintech.dump"
echo Restore end: %DATE% %TIME%
kubectl --context kind-fintech -n data exec -i postgres-0 -- psql -XqAt -v ON_ERROR_STOP=1 -U postgres -d fintech_restore_test < deploy\sql\verify_postgres_restore.sql > "%BACKUP_DIR%\restored.txt"
fc /b "%BACKUP_DIR%\source.txt" "%BACKUP_DIR%\restored.txt"
```

Never add `--clean`, `--create`, `--no-owner` or `--no-acl` to this restore.
Expect identical reports and exit code 0 from each SQL check and the comparison.
The report checks physical table counts, Flyway versions/checksums/status and
Auth account totals (including enabled admin and demo counts); D35 asserts
effective privileges on the audit table. An empty business dataset does not
prove content equality or predict a production recovery time.

When finished, after confirming this is the scratch database created by this
run, remove only that database. Do not use force:

```cmd
kubectl --context kind-fintech -n data exec postgres-0 -- dropdb -U postgres fintech_restore_test
```

Record the backup date, restore duration, and pass/fail evidence without raw
reports. A rehearsal is not the cutover backup: repeat on the final pre-sync
state and retain that verified archive. If rollback is needed, freeze writes,
agree on acceptable data loss since the dump and use a separately reviewed
recovery plan; do not overwrite the source using this runbook. Rehearse again
with representative data before experiments or the demo.

References: [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html)
and [pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html).

## Validation evidence

On 14 November 2026, a disposable PostgreSQL 17 container with synthetic data
restored a custom-format archive. The two SQL reports matched. Granting
column-level UPDATE to audit_user in the restored fixture made the audit
check fail as expected. The shared Kubernetes database and the CMD transfer
steps have not been rehearsed.
