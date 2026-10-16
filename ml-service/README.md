# ml-service/ — Owner P3 (@omar-aouichi)

FastAPI service serving real-time fraud predictions and conformal uncertainty sets.

- **Port**: `8000` (FastAPI + single Uvicorn process per pod, §5.7)
- **Contract**: [`contracts/ml-service.yaml`](../contracts/ml-service.yaml)
- **Operational Mode**: `MODEL_MODE=mock` (development/testing) or `MODEL_MODE=real` (production)

---

## 1. Quick Start

### Local Development (Python)

```bash
# Create and activate virtual environment
python3.12 -m venv ml-service/.venv
source ml-service/.venv/bin/activate

# Install dependencies
pip install -r ml-service/requirements.txt -r ml-service/requirements-dev.txt

# Run server with hot reload
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Docker Compose

From repo root:

```bash
docker compose up -d ml-service
docker compose logs -f ml-service
```

---

## 2. API Endpoints

| Method | Endpoint | Routing / Auth | Description |
|---|---|---|---|
| `POST` | `/predict` | **Internal only** (risk-service), never routed by gateway | Evaluates transaction risk synchronously |
| `GET` | `/health/live` | Internal (Kubernetes) | Process liveness probe |
| `GET` | `/health/ready` | Internal (Kubernetes) | Readiness probe (model loaded + warm-up succeeded) |
| `GET` | `/metrics` | Internal (Prometheus) | Operational and ML drift metrics (text/plain) |
| `GET` | `/api/v1/ml/model` | Gateway (`ADMIN`, `ANALYSTE`) | Deployed model version and metadata |
| `GET` | `/api/v1/ml/performance` | Gateway (`ADMIN`, `ANALYSTE`) | Offline benchmark and statistical reports |
| `GET` | `/api/v1/ml/viz/{method}?view=` | Gateway (`ADMIN`, `ANALYSTE`) | PCA, t-SNE, UMAP 2D projection points |

---

## 3. Mock Mode Rules (`MODEL_MODE=mock`)

Deterministic heuristic driving the three-way decision for P1's `risk-service`:

- **Amount > 500.00**:
  - `prediction`: `1`
  - `prediction_set`: `[1]` (`BLOQUER`)
  - `fraud_probability`: `0.92`
  - `uncertainty_level`: `FAIBLE`
- **200.00 <= Amount <= 500.00**:
  - `prediction`: `0`
  - `prediction_set`: `[0, 1]` (`REVUE`)
  - `fraud_probability`: `0.45`
  - `uncertainty_level`: `ELEVEE`
- **Amount < 200.00**:
  - `prediction`: `0`
  - `prediction_set`: `[0]` (`APPROUVER`)
  - `fraud_probability`: `0.03`
  - `uncertainty_level`: `FAIBLE`

---

## 4. Testing

```bash
pytest ml-service/tests/ -v
```
