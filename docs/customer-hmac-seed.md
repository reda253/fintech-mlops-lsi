# Customer HMAC and Sparkov wiring (Refs #40)

This prepares the deployment requirements from the new Customer implementation.
It does not generate a real key, import customer data, or update the running
cluster. The currently pinned 64b1d7d release predates the Customer implementation:
publish and review a new release after that PR is merged before enabling it.

## Stable HMAC key

The team overlay adds a required secretKeyRef:

| Environment variable | Secret in fintech | Data key |
| --- | --- | --- |
| CARD_HMAC_KEY | customer-hmac | key |

Provision this Secret through a strict-scope SealedSecret using the target
cluster's sealing certificate. No placeholder ciphertext or real key is
committed. The optional flag is not set: an absent Secret prevents startup.
The demo base is unchanged; a new Customer image still needs its key in any
local environment where it is used.

Before the FIRST import, generate at least 32 bytes with a cryptographic random
generator. Agree on the exact representation accepted by the service owner.
A string containing 64 hexadecimal characters generated from 32 random bytes
has 256 bits of entropy; hex text and decoded bytes are different key material.
Use exactly the same representation every time. Kubernetes Secret base64
encoding is transport encoding, not permission to change the application's key.

Back up the key separately from Git and keep it paired with the database
backup and a private key-identity/version record. Protect the Sealed Secrets
controller key as well if recovery relies on the ciphertext. Never regenerate
CARD_HMAC_KEY during a restart, restore, reseal or deployment. Changing the
controller's encryption key is not the same as changing the HMAC value.
Since raw cards are not stored, a lost HMAC key cannot be recovered from the
customer table. If customers already exist, stop and identify their original
key before any deployment; do not install a new one silently.

## Opt-in seed overlay

The normal team and team-release overlays do not enable seed or mount host
data. The separate deploy/overlays/team-sparkov overlay adds:

- CUSTOMER_SEED_PATH=/data/sparkov/fraudTrain.csv,/data/sparkov/fraudTest.csv
- hostPath /data/sparkov, type Directory (never DirectoryOrCreate)
- a read-only container mount at /data/sparkov
- nodeSelector fintech.local/sparkov=true
- a bounded 25-minute startup probe budget and 30-minute progress deadline.

Before labelling a node, confirm with P2/P3 that BOTH files exist there and
are readable by UID 10001, and that the directory contains only the intended
dataset. In kind a node is a container: files on Windows, another node or a
different cluster are not automatically present. Label only verified nodes,
and check that all selected nodes have the same approved files. Do not change
the existing kind cluster or copy data into a Git checkout to arrange a mount.
The image remains non-root, read-only, without init containers or API token.

A hostPath mount is local-node storage, not shared or highly available storage.
Read-only access prevents the container from modifying the dataset; it does
not make raw customer data non-sensitive. Keep access restricted. The longer
startup allowance is an initial explicit limit, not proof that a full Sparkov
seed fits in the existing 512 MiB memory limit or this time budget. Measure a
representative import and review resource requirements with the service owner.
Do not raise liveness/readiness privileges or expose CSVs publicly.

## Validation and release boundary

Run from the repository root in CMD:

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_customer_seed_wiring.py
kubectl kustomize deploy/overlays/team
kubectl kustomize deploy/overlays/team-sparkov
```

These commands do not deploy. The policy validator supports team_auth=True
and customer_seed=True for the seed overlay. It rejects writable mounts,
arbitrary host directories, automatic directory creation, missing node
selection and different seed paths. Existing default app policies remain.

Do not apply team-sparkov directly: it inherits image placeholders. The current
Argo CD team Application still points to team-release, not this seed overlay.
A reviewed release must explicitly choose seed, pin the NEW Customer image
and verify secret readiness and dataset locality before sync.

With the actual Customer PR/image, test a synthetic CSV in an isolated lab:
missing/short key refusal, successful seed, no stored raw card number,
authenticated lookup and preservation after restart with the SAME key.
Only then schedule the full seed after the backup/restore gate. The seed
only runs on an empty table; do not truncate a populated table to make it run.
Runtime Customer/CSV integration is not claimed by the manifest checks.

Reference: [Kubernetes hostPath volumes](https://kubernetes.io/docs/concepts/storage/volumes/#hostpath).
