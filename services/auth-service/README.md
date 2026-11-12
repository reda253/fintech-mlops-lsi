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

These passwords are public, so the accounts are for local development only (D47).

## Shared environments (D47)

Set these on every shared deployment (kind cluster, demo). Values come from a Sealed Secret (D22), never from Git or chat.

| Variable | Value | Effect at startup |
|---|---|---|
| `AUTH_DEMO_ACCOUNTS` | `false` | Disables `admin`, `analyste1`, `simulateur1` and revokes their sessions |
| `AUTH_BOOTSTRAP_ADMIN_USERNAME` | personal username, not a demo one | Creates this ADMIN if it does not exist; never modifies an existing account |
| `AUTH_BOOTSTRAP_ADMIN_PASSWORD` | at least 12 characters | Initial password of that admin |

With `AUTH_DEMO_ACCOUNTS=false` and no enabled ADMIN, the service refuses to start (nobody could create users). Once the admin exists, the two bootstrap variables can be removed.

Then the admin creates the other accounts with `POST /api/v1/auth/users` and sends each password privately:

| Account | Roles |
|---|---|
| Reda, Assil | ADMIN, ANALYSTE |
| Basma, Omar | ANALYSTE |
| Hakima | ADMIN, ANALYSTE (builds the users and audit screens) |
| simulator service account | SIMULATEUR (transactions + chargeback feedback, D19); no human uses it |
| k6 service account | SIMULATEUR, separate so load-test traffic stands out in the audit log |

To change a password, or disable an account: `PUT /api/v1/auth/users/{id}` (either one revokes every open session).
