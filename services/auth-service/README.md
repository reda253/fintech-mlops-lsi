# auth-service

Owner: P1. Users, roles, RS256 JWT issuance and JWKS. Port 8081, schema `auth`. Contract: `contracts/auth-service.yaml`.

## Run locally

The signing key is never committed (`*.pem` is gitignored, D41). Create one once, from this folder:

```bash
mkdir -p secrets && openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out secrets/jwt-private.pem
cd .. && ./mvnw -pl auth-service spring-boot:run
```

In Kubernetes the PEM comes from the Secret exposed as `JWT_PRIVATE_KEY`.

## Demo accounts (Flyway `V2__seed_users.sql`)

| Username | Password | Role |
|---|---|---|
| `admin` | `admin-demo-2026` | ADMIN |
| `analyste1` | `analyste-demo-2026` | ANALYSTE |
| `simulateur1` | `simulateur-demo-2026` | SIMULATEUR (used by the simulator) |

Demo only: on a real deployment, change them through `PUT /api/v1/auth/users/{id}` (a new password revokes every open session).
