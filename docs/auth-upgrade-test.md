# Isolated Auth upgrade validation (Refs #40)

This smoke test reproduces the Auth schema transition from the installed
e9a57d9 release to the reviewed e17a493 GHCR images. It does not connect to
Kubernetes. It uses a private Docker bridge, a temporary PostgreSQL filesystem
and an ephemeral RSA signing key. Application ports are published on loopback
only; PostgreSQL is not published. Do not point the script at a shared Docker
daemon. Use synthetic inputs only.

## Run In Windows CMD

Start Docker Desktop. Use the e17a493 inventory from GHCR run 42874954627,
attempt 2. The local e9a57d9 Auth image must still exist with its source
revision label (it was built for shared-release-01). If absent, rebuild from
the reviewed old source; do not retag an unrelated image.

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_auth_upgrade_smoke.py
python -B deploy/bootstrap/auth_upgrade_smoke.py --inventory "%USERPROFILE%\Downloads\registry-release\registry-release.json" --openssl "%ProgramFiles%\Git\usr\bin\openssl.exe"
```

Adjust paths if the inventory or OpenSSL lives elsewhere. The script pulls
only Auth, Gateway and derived PostgreSQL from the inventory. It checks
source labels as well as registry paths. No registry credentials are required
in the command; if the Docker host cannot pull the packages, arrange approved
read access rather than changing their visibility.

## What It Proves

- The old Auth container applies Flyway V1 and starts on a fresh test database.
- A disabled fixture user inserted in V1 survives the replacement of the Auth
  container and the application of V2 on that same database.
- The new Gateway rejects anonymous and invalid tokens, routes a demo login,
  and accepts the issued JWT on the protected Auth /me route.

No token, signing key, database password or response body is printed. The demo
account is only used on loopback with the fixture database. The script removes
only the containers and network it creates; it leaves pulled images cached.
An abrupt process termination can interrupt cleanup. Inspect the
fintech-auth-upgrade-* containers before cleaning up, and do not prune Docker.

This does not test Kubernetes Secret wiring, actual user data, production
credential policy, rollback after V2, the other services, or Argo CD adoption.
V2 includes known demo credentials: agree on a removal or disablement plan
before exposing a deployment using this image to the team. Do not run the
existing bootstrap again on the shared database.

## Observed Result

The Windows Docker Desktop run succeeded with the e9a57d9 local Auth image
and the three e17a493 GHCR digests from the reviewed inventory. The history
advanced from V1 to V1/V2, the disabled fixture survived, anonymous and invalid
JWT requests returned 401, and the issued JWT returned HTTP 200 from /me.
