# simulator/ — Owner P3 (@omar-aouichi)

Replays the Sparkov test dataset chronologically against the platform, generates unique `trans_num` identifiers for idempotency, and dispatches delayed true labels (`is_fraud`) to simulate chargebacks (**Decision D19**, §5.9).

---

## 1. Features

1. **Chronological Replay**: Reads `fraudTest.csv`, sorts strictly by `trans_date_trans_time`, and preserves chronological order.
2. **Idempotency Support**: Each transaction carries a unique `trans_num` (`CreateTransactionRequest` contract) required for Traefik retry testing and idempotent processing in `transaction-service`.
3. **Simulated Chargebacks**: Maintains an asynchronous schedule queue to dispatch true ground truth labels to `POST /api/v1/risk/feedback` after a configurable delay (default: 120s). This populates Grafana production metrics (`risk_feedback_total` and `risk_conformal_covered_total`).

---

## 2. Usage

### Local CLI (Dry Run)

```bash
# In virtual environment:
pip install -r simulator/requirements.txt -r simulator/requirements-dev.txt

# Run in dry-run mode (does not require running gateway):
python -m simulator.app.main --data-path ml/data/raw/fraudTest.csv --dry-run --limit 50
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--data-path` | `ml/data/raw/fraudTest.csv` | Path to Sparkov CSV file |
| `--tps` | `10.0` | Target transactions per second |
| `--feedback-delay` | `120.0` | Delay in seconds before sending simulated chargeback |
| `--dry-run` | `True` | Log generated requests without sending HTTP calls |
| `--limit` | `None` | Optional limit on number of replayed transactions |

---

## 3. Testing

```bash
cd simulator && pytest -v
```
