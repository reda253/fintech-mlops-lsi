# Synthetic Customer seed validation

This rehearsal uses only `kind-fintech-gitops-lab`, in a random owned namespace
that is removed on success or failure. It does not change `kind-fintech`, load
real Sparkov files, or prepare the stable shared HMAC key.

The Customer image is built from reviewed commit
`9a51fcfb3568c7657a0e3cc325c7fa11509b6279` (Customer implementation and PR #128
wiring). The existing reviewed `64b1d7d` registry inventory supplies Auth,
Gateway and PostgreSQL by digest. Its old Customer image is not used.

## Run from Windows CMD

Open CMD in the repository root. Docker Desktop must be running. The lab must
already have the Sealed Secrets controller and one Ready node. Use the existing
private inventory file; do not commit it or any generated credentials.

```cmd
docker build --label org.opencontainers.image.revision=9a51fcfb3568c7657a0e3cc325c7fa11509b6279 -t fintech-customer-service:9a51fcfb3568c7657a0e3cc325c7fa11509b6279 -f services/customer-service/Dockerfile services
python -B -m unittest discover -s deploy/bootstrap -p test_customer_kubernetes_smoke.py
python -B deploy/bootstrap/customer_kubernetes_smoke.py --inventory "%USERPROFILE%\Downloads\registry-release (1)\registry-release.json" --openssl "C:\Program Files\Git\usr\bin\openssl.exe" --kubeseal "%LOCALAPPDATA%\kubeseal-0.41.2\kubeseal.exe"
```

The script loads the local Customer image into the lab, then reuses the isolated
Auth fixture. PostgreSQL uses temporary `emptyDir` storage, not shared PVCs.
The random HMAC key is sealed with strict namespace/name scope and exposed through
the team overlay's `customer-hmac/key` reference. The key remains in memory and
temporary Kubernetes resources; no key or token is printed or saved to Git.

Two tiny generated CSVs contain three rows representing two fictional cards.
They have no `is_fraud` column and include a quoted comma in a job field.
A read-only ConfigMap volume supplies these fixtures at the configured seed paths.

## Assertions

- Startup and readiness succeed with the sealed key and synthetic CSVs.
- Two distinct customers are stored despite a duplicate across files.
- Stored fingerprints match independently calculated HMAC-SHA256 values;
  the fixture card numbers are absent from stored rows and public responses.
- An anonymous internal lookup returns 401. A JWT from the isolated Auth/Gateway
  fixture permits lookup and a public customer read. Invalid and unknown cards
  return 400 and 404 respectively.
- Restarting Customer with the same key preserves both customer identities and
  the lookup result; the seed does not create another copy.
- The reused D47 fixture also verifies demo account rejection and preservation
  of a changed admin password across an Auth restart.

CI runs the Python fixture tests. The Kubernetes rehearsal is a separate manual
run; adding its unit tests to CI does not make the live rehearsal automatic.
Missing/short-key rejection is covered by Customer's Java tests, rather than by
this successful-startup rehearsal.

On 22 November 2026, the manual lab run passed both the Customer assertions and
the reused Auth D47 checks with the revisions listed above. The temporary
namespace was deleted at the end. The five Python fixture tests also passed.

## Before shared deployment

This tiny import does not establish full Sparkov memory needs, import duration,
node file availability, or persistence through node loss. It does not exercise
the real `hostPath` mount or replace the database backup/restore gate.

Follow [Customer HMAC and seed wiring](customer-hmac-seed.md): retain one stable
shared key, back it up with the database recovery material, verify dataset access
on selected nodes, publish and review a new Customer image digest, and complete
the backup rehearsal before the first shared sync. Never truncate customer data
or replace an existing HMAC key to trigger the seed.
