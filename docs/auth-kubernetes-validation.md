# Auth signing in the GitOps lab (Refs #40)

The Docker upgrade test verifies the real V1-to-V2 upgrade. This complementary
test starts with an empty PostgreSQL instance in Kubernetes and exercises
the signing key delivery path: generated RSA key -> strict SealedSecret ->
controller-generated Secret -> Auth `secretKeyRef` -> Gateway JWT verification.
It uses the reviewed Auth, Gateway and PostgreSQL image digests from e17a493.

## Run In CMD

Prerequisites: the existing single-node fintech-gitops-lab cluster, its
Sealed Secrets controller, access to GHCR images from the lab, OpenSSL and
kubeseal v0.41.2. Run from the repository root:

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_auth_kubernetes_smoke.py
python -B deploy/bootstrap/auth_kubernetes_smoke.py --inventory "%USERPROFILE%\Downloads\registry-release\registry-release.json" --openssl "%ProgramFiles%\Git\usr\bin\openssl.exe" --kubeseal "%LOCALAPPDATA%\kubeseal-0.41.2\kubeseal.exe"
```

The script accepts no cluster selector. It uses the explicit
kind-fintech-gitops-lab context and checks its node identity before creating
resources. It generates a fresh namespace, creates PostgreSQL with emptyDir
storage, and isolates database and JWKS traffic to that namespace. It creates
no PVC, Ingress or external Service. It keeps the signing key in memory on
the client and submits only ciphertext for the signing key. Database Secrets
are temporary and sent via stdin, not written into Git. The Gateway is reached
through a loopback port-forward only. No tokens or response bodies are printed.

Expected results: SealedSecret Synced; PostgreSQL, Auth and Gateway roll out;
Flyway V1 and V2 are present; anonymous and invalid JWT requests return 401;
the test login works and the signed JWT returns HTTP 200 from /me. The script
checks namespace identity and ownership before deleting it, even on failure.

The signing key and demo account are strictly for this test. The script does
not adopt resources into Argo CD or make changes to the shared environment.
Shared rollout still needs a decision about demo accounts, a separate signing
key procedure and a reviewed first sync plan.

## Observed Result

The local GitOps lab run completed successfully on 12 November 2026. The
strict SealedSecret synchronized, Flyway V1 and V2 were recorded, Gateway
returned 401 for anonymous/invalid JWT requests and 200 for the signed JWT
on /me. The temporary namespace was deleted at the end of the run.
