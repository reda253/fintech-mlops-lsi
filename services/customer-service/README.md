# customer-service

Owner: P1. Cardholders from Sparkov. Port 8082, schema `customer`. Contract: `contracts/customer-service.yaml`.

The card number is never stored. The service keeps `HMAC-SHA256(cardNumber)` as the card identifier and the last 4 digits for display (§3.4). The HMAC key exists only here, so a leaked table cannot be matched back to card numbers. A plain SHA-256 would not protect them: there are few enough card numbers to hash them all.

## Endpoints

| Endpoint | Who | Notes |
|---|---|---|
| `GET /api/v1/customers` | ADMIN, ANALYSTE | Filters `name` (first or last, case-insensitive), `city`, `state`, `cardLast4`; paging `page`, `size`, `sort` on `lastName`, `firstName`, `city`, `state`, `createdAt` |
| `POST /api/v1/customers` | ADMIN | `409` if the card already belongs to a customer |
| `GET /api/v1/customers/{id}` | ADMIN, ANALYSTE | |
| `PUT /api/v1/customers/{id}` | ADMIN | Profile only, the card cannot change. `409` on a concurrent edit |
| `POST /internal/customers/lookup` | any valid JWT | Card number → `customerId` + `cardLast4` (transaction-service, D33). Not routed by the gateway |
| `GET /internal/customers/{id}/risk-profile` | any valid JWT | The 7 fields `/predict` needs (risk-service, D34). Not routed by the gateway |

## Configuration

| Env var | Required | Meaning |
|---|---|---|
| `CARD_HMAC_KEY` | yes | HMAC key, at least 32 bytes, from a K8s Secret. The service refuses to start without it. Changing it orphans every stored fingerprint |
| `CUSTOMER_SEED_PATH` | no | Comma-separated raw Sparkov CSV files loaded at startup (D50) |
| `DB_URL`, `DB_USER`, `DB_PASSWORD`, `JWKS_URI` | | As in every service |

## Sparkov seed (D50)

At startup, if `CUSTOMER_SEED_PATH` is set and the table is empty, the service reads the files and inserts one customer per `cc_num`. It reads the customer columns only and never `is_fraud`. The load is one transaction and uses `ON CONFLICT DO NOTHING`, so several replicas can start at the same time. It finishes before the readiness probe turns UP.

Seed with both files, so every card the simulator replays (`fraudTest.csv`) resolves:

```bash
export CARD_HMAC_KEY="$(openssl rand -base64 48)"    # local only; keep the same value between runs
export CUSTOMER_SEED_PATH=../ml/data/raw/fraudTrain.csv,../ml/data/raw/fraudTest.csv
cd .. && ./mvnw -pl customer-service spring-boot:run
```

To reload, empty the table first: the seed never overwrites existing customers.
