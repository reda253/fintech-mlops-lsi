# Team GitOps adoption plan (Refs #40)

This is a candidate for manual adoption, not a deployment instruction.
The team-release overlay pins the eight application images from GHCR run
43243659942, attempt 1, source 64b1d7d. The Git revision containing the
adoption manifests is a separate revision from the image source commit.

The Argo CD project allows only the project repository and Deployments,
Services, ConfigMaps and Ingresses in the existing fintech namespace. The
Application has no auto-sync or cascading deletion finalizer, has pruning
disabled, and fails if another Application tracks a resource. These are
Application-level rules, not a replacement for controller RBAC. The candidate
does not include PostgreSQL, RabbitMQ, PVCs, Secrets, ingress-test, ML workloads
or the simulator. The existing Ingress and TLS reference remain unchanged.

## Read-only review (Windows CMD)

Run from the repository root:

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_team_adoption.py
python -B deploy/bootstrap/check_team_adoption.py --inventory "%USERPROFILE%\Downloads\registry-release (1)\registry-release.json"
kubectl kustomize deploy/gitops/team/bootstrap
```

The checker compares the rendered digests with the inventory, and checks
resource identities, Deployment/Service selectors, replica counts and existing
Argo tracking annotations or owner references. It does not read Secrets or
apply resources. It is a structural check, not the full Argo CD diff.

For the Kubernetes dry-run diff, if Windows cannot find diff.exe, temporarily
add Git for Windows' tools to the PATH in this CMD window:

```cmd
set "PATH=%ProgramFiles%\Git\usr\bin;%PATH%"
kubectl --context kind-fintech diff -k deploy/overlays/team-release
```

Exit 1 means differences; an exit code above 1 means the check failed.
On 12 November 2026 the structural and dry-run checks passed: the eight
Deployments change image, and Auth also switches ConfigMap and gains three
Secret references. A new Auth ConfigMap is rendered. Existing Services and
Ingress showed no change in the Kubernetes diff. The old Auth ConfigMap and
ingress-test were outside the candidate. No resources were changed.

## Before approval for the first sync

1. Agree with Reda on a maintenance window and keep team access restricted
   until the Auth and ingress checks pass. Verify PostgreSQL backups and a
   recovery procedure. Do not assume reverting only the image reverses
   Flyway V2 or the D47 account changes.
2. Install and verify Argo CD and Sealed Secrets separately on the intended
   cluster, with a private Argo CD API, and test backup of the new sealing
   key. Do not reuse keys from either lab.
3. Prepare the dedicated signing key and initial admin out of band. Use
   the target cluster's certificate, strict scope, and the exact names
   auth-signing and auth-bootstrap-admin in fintech. Verify the generated
   Secrets exist without displaying their values. The Application does not
   manage these Secrets. Do not reuse or disclose real credentials in Git,
   command logs or chat.
4. Register the project/Application only after the above gates. Review the
   full Argo CD diff at the exact approved manifest commit: no deletions,
   selector changes, unrelated resources or loss of ownership labels.
   Confirm GHCR pull access and node capacity for rolling updates.
5. With explicit approval, sync that revision manually, without Prune,
   Force or Replace. Stop on any rollout, migration or health failure.
   Verify the eight rollouts, frontend HTTPS, anonymous 401, all three demo
   logins denied, a working named ADMIN, and unchanged PostgreSQL/RabbitMQ
   resources and PVCs. Verify real frontend login separately; the Auth lab
   does not prove the frontend is configured for it.

Once the named admin is verified, arrange individual accounts and remove the
bootstrap references in a reviewed follow-up before removing their Secret.
Do not rerun the old first-install bundle on the adopted cluster. Continuous
sync, app-of-apps and rollback validation remain follow-up work for #40.
