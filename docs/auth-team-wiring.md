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

In CMD at the repository root, use the registry-release.json artifact for
64b1d7d (GHCR run 43243659942, attempt 1). Adjust the path below to its actual
location. The team smoke uses Auth, Gateway and PostgreSQL from that inventory
by digest. It rejects the earlier e17a493 inventory and does not load any local
image into kind. The smoke without --team still uses e17a493.

```cmd
kubectl kustomize deploy/overlays/team
python -B -m unittest discover -s deploy/bootstrap -p "test_auth*smoke.py"
python -B deploy/bootstrap/auth_kubernetes_smoke.py --team --inventory "%USERPROFILE%\Downloads\registry-release (1)\registry-release.json" --openssl "%ProgramFiles%\Git\usr\bin\openssl.exe" --kubeseal "%LOCALAPPDATA%\kubeseal-0.41.2\kubeseal.exe"
```

The team mode pulls from GHCR in the named GitOps lab and uses a
random namespace, a fresh PostgreSQL database without PVC, two synthetic
SealedSecrets and a loopback Gateway port-forward. It verifies V1/V2,
rejection of all three demo logins, a working JWT for the new ADMIN, password
change via the API, and successful login with the new password after restarting
Auth while its original bootstrap Secret remains configured. The initial
password must then fail. It deletes only its owned namespace.

On 12 November 2026, both the initial local-image rehearsal and the
64b1d7d GHCR rehearsal passed. The latter used all three reviewed digests
and removed the temporary namespace after the password restart check.

## Before any shared sync

Review the D47 GHCR release, plan the signing key and named initial admin with
the team, and use the target cluster's sealing certificate and exact Secret
names/namespace. Do not reuse either lab key.
Review the live diff, backups and API/UI access before promotion. No Argo CD
Application is pointed at this overlay yet. After confirming another enabled
ADMIN can log in, remove the bootstrap environment references in a reviewed
change before removing the separate bootstrap Secret; leave the signing Secret
in place. Do not rerun the database bootstrap.
