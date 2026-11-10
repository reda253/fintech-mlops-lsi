# Reviewed image publication (prerequisite for #40)

## Scope And Boundaries

The local cluster currently uses Docker images loaded into kind. This lot adds a
manual GHCR publication path for the ten application images and the derived
PostgreSQL image. RabbitMQ keeps its existing upstream digest and is not copied.
There are eleven matrix builds, at most three at once.

This does not install Argo CD or Sealed Secrets, adopt existing resources, change
image references in Git, bootstrap SQL, deploy ML workloads or enable CD. It never
connects to Kubernetes. The working shared-release-01 bundle remains unchanged.
Existing image scan and application integration workflows remain required: a
publication run is not a substitute for their tests or a business validation.

## Publication Contract

- Only a manually confirmed run from main is accepted. No arbitrary ref input.
- Checkout is the exact commit selected by GitHub, with credentials persistence off.
- Seven Java builds use the services reactor; frontend, Python and derived
  PostgreSQL use their existing Dockerfiles and contexts.
- Every image carries the source repository and full revision OCI labels.
- Linux AMD64 images are built, then Trivy scans the exact local image before push.
- Any CRITICAL vulnerability blocks that image, including unfixed findings.
  HIGH findings are not a blocking policy in this image-publication workflow.
  Scanner/database/network failures also block; do not disable the gate to retry.
- Only matrix publication jobs receive packages:write, using GITHUB_TOKEN.
  No new PAT, deploy App key, cluster kubeconfig or application Secret is needed.
- Authentication occurs after scan; logout runs on success or failure.
- Tags contain full commit, run ID and attempt, never latest. Tags are still
  registry tags, not technically immutable. Use the recorded repository@sha256
  references for future promotion.
- Complete inventory requires eleven distinct receipts with the same repository,
  commit, run ID and attempt and exact per-module registry paths.

Digest receipts are generated from Docker RepoDigests after a successful push.
They identify pushed content, but are not signatures, provenance attestations,
independent remote verification or proof of reproducible builds. Existing floating
base tags may resolve differently on later builds. Promotion must review the new
digests rather than assume that the same source SHA always produces the same image.

## Before First Publication

Ask Reda to approve publication into the repository owner's GHCR namespace and
check that repository/organization policy permits Actions package writes.
No package is deliberately made public by this workflow. Inspect actual package
visibility and inherited access after the first run. Do not assume teammates or
Kubernetes can pull a private package using their ordinary repository access.

The image.source label links each image to this repository. If a package name
already exists under the owner, its administrator may need to grant this
repository Actions access. A 403 should be investigated as a package/policy issue,
not fixed by creating an unnecessarily broad personal token.

## Run After Merge (GitHub UI)

1. Open Actions -> Publish reviewed images to GHCR -> Run workflow.
2. Select main and explicitly enable confirm_publish.
3. Run the workflow and wait for all eleven publication jobs and inventory.
4. Download the registry-release artifact, containing registry-release.json.
5. Record the run URL, source SHA and artifact in the issue; review package access.

The workflow is manual-only. It has no pull_request or automatic push trigger.
Merging this change does not publish anything or modify the running cluster.
Prerequisite: normal repository and image CI checks must have passed on the
reviewed source. This manual workflow does not query/enforce other workflows' status.

If one matrix job fails, other already-pushed images can remain in GHCR. There is
no registry rollback or complete inventory for that failed run. Fix the cause and
use Re-run all jobs (not only failed jobs): a new attempt changes all tags, and
mixed-attempt receipts are deliberately rejected. Do not combine partial runs or
delete packages that another team member might already use.

Artifacts expire after 30 days. Preserve the approved non-secret digest inventory
in the future GitOps release PR before expiry. Uploads contain only digest/identity
JSON, never docker config, credentials, local private bundles or build contexts.

## Next Stages (Not Implemented Here)

1. Test registry pull access from a disposable namespace; select public images or
   a scoped pull credential according to the team's access policy.
2. Pin controller/chart versions and install Argo CD / Sealed Secrets separately.
3. Back up and test restoration of the sealing key before relying on encryption.
4. Generate a reviewed GitOps candidate using the existing namespace/resource names,
   release ownership and app configuration, with the approved image digests.
5. Seal existing credentials without regenerating passwords, changing SQL roles
   or accidentally attaching deletion ownership to long-lived Secrets.
6. Review live diff and adopt applications manually first, without automatic prune
   or cascading Application deletion. Do not adopt data, PVCs, ML or team resources
   as an implicit side effect of installing a root Application.
7. Validate probes/HTTPS, then demonstrate a reviewed application-only update and
   rollback before enabling further automation.

The existing local verifier checks the old release's local image identities.
It will need an explicit registry/GitOps verification path before image promotion;
do not edit its private release hashes to make a new deployment pass.

## Local Tests

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_registry_release.py
```

These tests require no GHCR credentials, Docker daemon or cluster. They check all
build paths, strict identifiers, pushed digest extraction, missing/duplicate
receipts, mixed runs and unexpected registry references. Real GHCR publication and
pull access still require validation after merge; no successful registry run is
claimed by these unit tests.

References:
- [GitHub Actions package publishing](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions)
- [Argo CD sync options](https://argo-cd.readthedocs.io/en/stable/user-guide/sync-options/)
- [Sealed Secrets existing-Secret ownership](https://github.com/bitnami/sealed-secrets)
