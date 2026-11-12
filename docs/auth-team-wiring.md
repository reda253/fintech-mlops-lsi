# Team Auth wiring (D47, Refs #40)

`deploy/overlays/team` is a renderable configuration for a future team release,
not an install command. It does not change the local/demo overlay. It sets
`AUTH_DEMO_ACCOUNTS=false` only in the generated Auth ConfigMap and adds three
required Secret references to the Auth container:

| Variable | Secret | Key |
| --- | --- | --- |
| JWT_PRIVATE_KEY | auth-signing | private-key |
| AUTH_BOOTSTRAP_ADMIN_USERNAME | auth-bootstrap-admin | username |
| AUTH_BOOTSTRAP_ADMIN_PASSWORD | auth-bootstrap-admin | password |

Signing and bootstrap credentials use separate strict SealedSecrets. No
ciphertext tied to a workstation, cleartext values, or real admin is committed.
This overlay inherits placeholder images: do not apply it to kind-fintech.
Do not deploy e17a493 Auth with this config: that image predates D47.

## Lab verification

In CMD at the repository root, use a local image built from the reviewed
b39e628 source. Build from that exact commit with an unchanged services tree;
never relabel an arbitrary image. The lab uses Auth from that local build and
the existing e17a493 GHCR digests for PostgreSQL and Gateway.

```cmd
git diff --exit-code b39e628 -- services
git status --short -- services
for /f %i in ('git rev-parse b39e628') do set "SOURCE_REV=%i"
docker build --label "org.opencontainers.image.revision=%SOURCE_REV%" -t "fintech-auth-service:%SOURCE_REV%" -f services/auth-service/Dockerfile services
kubectl kustomize deploy/overlays/team
python -B -m unittest discover -s deploy/bootstrap -p "test_auth*smoke.py"
python -B deploy/bootstrap/auth_kubernetes_smoke.py --team --inventory "%USERPROFILE%\Downloads\registry-release\registry-release.json" --openssl "%ProgramFiles%\Git\usr\bin\openssl.exe" --kubeseal "%LOCALAPPDATA%\kubeseal-0.41.2\kubeseal.exe"
```

Run the Docker build only if both Git checks have no output and succeed.

The team mode loads the local Auth image into the named GitOps lab and uses a
random namespace, a fresh PostgreSQL database without PVC, two synthetic
SealedSecrets and a loopback Gateway port-forward. It verifies V1/V2,
rejection of all three demo logins, a working JWT for the new ADMIN, password
change via the API, and successful login with the new password after restarting
Auth while its original bootstrap Secret remains configured. The initial
password must then fail. It deletes only its owned namespace.

Observed on 12 November 2026: both SealedSecrets synced in the lab, Flyway
recorded V1/V2, and all login and restart checks passed.

## Before any shared sync

Publish and review a new GHCR release that includes D47, plan the signing key
and named initial admin with the team, and use the target cluster's sealing
certificate and exact Secret names/namespace. Do not reuse either lab key.
Review the live diff, backups and API/UI access before promotion. No Argo CD
Application is pointed at this overlay yet. After confirming another enabled
ADMIN can log in, remove the bootstrap environment references in a reviewed
change before removing the separate bootstrap Secret; leave the signing Secret
in place. Do not rerun the database bootstrap.
