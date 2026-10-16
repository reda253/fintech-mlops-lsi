# ml/ — owner P2 (data science) + P3 (pipeline)

Preprocessing, benchmark, statistical validation (`ml/stats/validate.py`), pipeline. Sparkov CSVs go in `ml/data/` (git-ignored).

## MLflow (local dev)

Tracking server = the `mlflow` service in `docker-compose.yml`. Backend store is PostgreSQL (`mlflow` schema, D5); artifacts are served by MLflow itself to the `mlflow_artifacts` volume (no MinIO, §5.2).

Start it:
```bash
# one-time: create the schemas/users (see deploy/sql/00_schemas_users.sql)
docker compose up -d postgres
docker compose exec -T postgres psql -U fintech -d fintech -v ON_ERROR_STOP=1 \
  -v auth_pwd=auth -v customer_pwd=customer -v transaction_pwd=transaction \
  -v risk_pwd=risk -v notification_pwd=notification -v audit_pwd=audit \
  -v audit_migrator_pwd=audit_migrator -v mlflow_pwd=mlflow \
  < deploy/sql/00_schemas_users.sql

docker compose up -d mlflow
```

- UI: http://localhost:5000
- Tracking URI (from another container): `http://mlflow:5000`
- Tracking URI (from the host): `http://localhost:5000`

Log a run (template for pipeline steps):
```bash
python -m venv ml/.venv && . ml/.venv/bin/activate
pip install -r ml/requirements-dev.txt
python ml/tracking_smoke.py --tracking-uri http://localhost:5000 --experiment smoke
```

The reusable helper is `ml/tracking_smoke.py::log_smoke_run(tracking_uri, experiment)`.

> Not yet done here (later plans): the model registry entry `fraud-detector` with `champion`/`challenger` aliases, the pipeline with quality gates, and the Kubernetes deployment (namespace `ml`).
