"""Create one GitHub issue per planned task (architecture §10.4 / §10.5).

Idempotent: an issue whose title already exists is not recreated, only (re)assigned.
Re-run it after teammates accept their invitation to assign the remaining issues.

    python docs/planning/create_issues.py            # create + assign
    python docs/planning/create_issues.py --dry-run  # print only
"""
import json
import subprocess
import sys

REPO = "reda253/fintech-mlops-lsi"
DRY = "--dry-run" in sys.argv

TEAM = {
    "P1": ("reda253", "Reda", "backend"),
    "P2": ("Basmaabis", "Basma", "ml"),
    "P3": ("omar-aouichi", "Omar", "mlops"),
    "P4": ("ASSIL-Dev1", "Assil", "devops"),
    "P5": ("hakimafiach77-commits", "Hakima", "frontend"),
}

# milestone titles exactly as created in the UI
J = {
    1: "J1 Architecture & Contracs",
    2: "J2 MLflow, data, env ready",
    3: "J3 Base services, benchmark",
    4: "J4 Stats, K8s, 1st model",
    5: "J5 Pipeline, CI/CD, e2e",
    6: "J6 Experiments, alerts",
    7: "J7 Code freeze",
    8: "README + demo v1",
    9: "J9 Delivery",
}

# (role, title, start, end, milestone, handoff or None, extra labels, spec ref)
TASKS = [
    # ---- P1 backend + lead
    ("P1", "Architecture, OpenAPI contracts v1, DB schemas", "28/09", "11/10", 1, "#2 → Omar, Assil, Hakima", ["lead"], "§3, §3.9, §3.10"),
    ("P1", "Repo setup: ruleset on main, CODEOWNERS handles, Projects board, Discord", "28/09", "11/10", 1, None, ["lead"], "§7.2, §10.7"),
    ("P1", "common module v1: correlation id, Problem Details, resource-server security, JSON logs", "12/10", "18/10", 3, None, [], "§3.1, §3.10"),
    ("P1", "auth-service: users, BCrypt, RS256 JWT (access + refresh), JWKS, users CRUD", "12/10", "25/10", 3, None, [], "§3.4 auth-service"),
    ("P1", "api-gateway: routes, JWT validation, CORS, login rate limit, SSE route, 30 s pool lifetime", "12/10", "01/11", 3, None, [], "§3.4 api-gateway, §6.11"),
    ("P1", "customer-service: CRUD, HMAC card fingerprint, Sparkov customers seed, internal lookup + risk-profile", "19/10", "01/11", 3, None, [], "§3.4 customer-service, D33, D34"),
    ("P1", "transaction-service: idempotent POST on transNum, filters, EN_ATTENTE re-evaluation job", "19/10", "08/11", 3, None, [], "§3.4 transaction-service, §3.6"),
    ("P1", "Outbox + RabbitMQ topology + idempotent consumer in common", "26/10", "08/11", 3, None, [], "§3.5, contracts/events.md"),
    ("P1", "Freeze and announce stable REST endpoints", "02/11", "08/11", 3, "#7 → Assil, Hakima", ["lead"], "§10.5"),
    ("P1", "risk-service v1: decision policy, ml-service mock client, circuit breaker, fail-safe REVUE", "02/11", "15/11", 4, None, [], "§2.5, §3.6"),
    ("P1", "Review queue: @Version optimistic lock (409), review.completed, transaction consumes it", "09/11", "22/11", 4, None, [], "§3.7"),
    ("P1", "notification-service: store, fanout notifications.live, SSE stream", "09/11", "22/11", 4, None, [], "§3.4 notification-service"),
    ("P1", "audit-service: append-only log, test audit_user cannot UPDATE/DELETE", "16/11", "22/11", 4, None, [], "§3.4 audit-service, D35"),
    ("P1", "Observability in all services: probes, /actuator/prometheus, histograms, graceful shutdown", "16/11", "22/11", 4, None, [], "§6.7, §6.8, §8.2"),
    ("P1", "Feedback endpoint, production counters, /internal/risk/labels", "23/11", "29/11", 5, None, [], "§5.9"),
    ("P1", "e2e-tests project (7 scenarios) + Docker image for Argo CD PostSync", "23/11", "06/12", 5, "#14 → Assil", [], "§7.7"),
    ("P1", "Resilience tuning: bounded Tomcat queues, HikariCP sizing, Traefik retry, tolerationSeconds", "30/11", "06/12", 5, None, [], "§9.5, §9.6"),
    ("P1", "On call during experiments: fix outbox/idempotency/timeouts, check C4 and C6", "07/12", "20/12", 6, None, [], "§9.6"),
    ("P1", "README section: Architecture microservices", "14/12", "27/12", 8, None, ["documentation"], "§10.4"),
    ("P1", "README consolidation (style, TOC, how to run, limits)", "28/12", "03/01", 8, "#17 → everyone", ["documentation", "lead"], "§10.5"),
    # ---- P2 data science
    ("P2", "Exploratory analysis + preprocessing pipeline (sklearn Pipeline, features list)", "28/09", "18/10", 2, "#4 → Reda, Omar", [], "§4.1–4.4"),
    ("P2", "Hyperparameter tuning + benchmark 10×5 folds for the 5 models", "19/10", "08/11", 3, "#8 → Omar", [], "§4.5–4.7"),
    ("P2", "Statistical validation module ml/stats/validate.py (Friedman, Wilcoxon, Holm, CI, effect sizes)", "02/11", "22/11", 4, "#9 → Omar", [], "§4.8, §4.9"),
    ("P2", "Calibration, Mondrian conformal prediction, choice of alpha", "16/11", "29/11", 5, "#12 → Omar, Reda", [], "§4.10"),
    ("P2", "Fairness audit (gender, age bands)", "23/11", "29/11", 5, None, [], "§4.3"),
    ("P2", "README section: Machine learning", "14/12", "27/12", 8, None, ["documentation"], "§10.4"),
    # ---- P3 MLOps
    ("P3", "MLflow (Compose then K8s) + sample tracking script", "28/09", "18/10", 2, "#3 → Basma", [], "§5.2"),
    ("P3", "ML pipeline skeleton + smoke pipeline in CI", "19/10", "01/11", 3, None, [], "§5.1, §5.6"),
    ("P3", "ml-service mock mode + validate /predict contract (contracts/ml-service.yaml)", "26/10", "08/11", 3, "#6 → Reda", [], "§5.7"),
    ("P3", "Simulator: chronological replay + delayed labels (chargebacks)", "02/11", "29/11", 5, None, [], "§5.9, D19"),
    ("P3", "First real model in production + visualisations (PCA, t-SNE, UMAP)", "09/11", "22/11", 4, "#10 → Reda, Hakima", [], "§4.11, §5.12"),
    ("P3", "Full pipeline with quality gates + automatic promotion PR", "16/11", "06/12", 5, None, [], "§5.4, §5.5"),
    ("P3", "ml-service final: registry model, hostPath cache, metrics", "23/11", "06/12", 5, "#13 → Assil", [], "§5.7, §5.8"),
    ("P3", "README section: MLOps and model serving", "14/12", "27/12", 8, None, ["documentation"], "§10.4"),
    # ---- P4 DevOps
    ("P4", "Docker Compose + kind cluster (3 nodes) + CI skeleton", "28/09", "18/10", 2, "#5 → everyone", [], "§6.2, §7.4"),
    ("P4", "Validate CI-bot write on protected main + kindnet NetworkPolicies", "05/10", "11/10", 1, None, [], "§6.2, §7.6"),
    ("P4", "SonarCloud, Trivy, gitleaks in CI", "19/10", "08/11", 3, None, [], "§7.5"),
    ("P4", "Dockerfiles for the 10 images + Trivy image scans", "19/10", "08/11", 3, None, [], "§6.1"),
    ("P4", "Base K8s manifests: Deployments, Services, Ingress, probes, resources, ConfigMaps", "02/11", "22/11", 4, None, [], "§6.3–6.9"),
    ("P4", "Argo CD app of apps + Sealed Secrets + continuous deployment", "09/11", "22/11", 4, "#11 → Hakima", [], "§6.13, §7.6"),
    ("P4", "HPA, PodDisruptionBudgets, topology spread, NetworkPolicies", "16/11", "29/11", 5, None, [], "§6.6, §6.8, §6.12"),
    ("P4", "Automatic rollback + k6 and chaos scripts + make experiment", "23/11", "06/12", 5, None, [], "§7.7, §9.2"),
    ("P4", "Capacity test (C_min, C_max) + main scenario ×3", "30/11", "13/12", 6, None, [], "§9.4, §9.5"),
    ("P4", "Experiments C1–C9 ×3 + videos", "07/12", "20/12", 6, "#16 → everyone", [], "§9.6–9.9"),
    ("P4", "README section: Docker, Kubernetes, CI/CD, experiments", "14/12", "27/12", 8, None, ["documentation"], "§10.4"),
    # ---- P5 frontend + observability
    ("P5", "Mockups + React skeleton", "28/09", "18/10", 2, None, [], "§1.3"),
    ("P5", "Prometheus + Grafana in Docker Compose", "19/10", "08/11", 3, None, ["Observability"], "§8.8"),
    ("P5", "React business pages: customers, transactions, review queue, live notifications", "19/10", "22/11", 4, None, [], "§1.3, §3.7"),
    ("P5", "K8s monitoring (kube-prometheus-stack, ServiceMonitors) + Loki/Alloy", "16/11", "29/11", 5, None, ["Observability"], "§8.1, §8.6"),
    ("P5", "React ML pages: visualisations, model performance, uncertainty", "16/11", "06/12", 5, None, [], "§4.11, §8.4"),
    ("P5", "9 Grafana dashboards + Discord alerts + runbooks", "23/11", "13/12", 6, "#15 → Assil", ["Observability"], "§8.3–8.5"),
    ("P5", "Observe experiments: every alert fired at least once and captured", "07/12", "20/12", 6, None, ["Observability"], "§8.8"),
    ("P5", "README section: Frontend and observability", "14/12", "27/12", 8, None, ["documentation"], "§10.4"),
    ("P5", "Demo script (5 min max) + recording", "28/12", "03/01", 8, "#17 → everyone", [], "§10.8"),
    # ---- everyone
    ("ALL", "Code freeze: bug-fix PRs only", "21/12", "21/12", 7, None, ["lead"], "§10.6"),
    ("ALL", "Post-freeze fixes", "21/12", "03/01", 8, None, [], "§10.4"),
    ("ALL", "Final review, clean-machine test, tag v1.0, delivery", "04/01", "09/01", 9, None, ["lead"], "§10.6"),
]


def gh(*args, check=True):
    r = subprocess.run(["gh", *args], capture_output=True, text=True, encoding="utf-8")
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r


def year(d):  # dd/mm → dd/mm/yyyy (Sep–Dec = 2026, Jan = 2027)
    return f"{d}/{'2027' if d.endswith('/01') else '2026'}"


def body(role, start, end, handoff, ref):
    who = "everyone" if role == "ALL" else f"{TEAM[role][1]} ({role}, @{TEAM[role][0]})"
    lines = [
        f"**Owner:** {who}",
        f"**Planned:** {year(start)} → {year(end)}",
        f"**Spec:** {ref} — `docs/specs/Architecture_Plateforme_FinTech_MLOps_1.pdf`",
    ]
    if handoff:
        lines.append(f"**Handoff:** deliverable {handoff} (§10.5)")
    lines += [
        "",
        "## Definition of done",
        "- [ ] Documented",
        "- [ ] Tested",
        "- [ ] Demonstrated to the team",
        "",
        "_Split into sub-issues when you start it. Close it from the PR with `Closes #<this issue>`._",
    ]
    return "\n".join(lines)


def main():
    existing = {i["title"]: i["number"] for i in json.loads(
        gh("issue", "list", "-R", REPO, "--state", "all", "-L", "500", "--json", "title,number").stdout)}
    created = skipped = 0
    unassigned = []
    for role, title, start, end, ms, handoff, extra, ref in TASKS:
        labels = list(extra)
        if role != "ALL":
            labels.insert(0, TEAM[role][2])
        if handoff:
            labels.append("handoff")
        assignees = [t[0] for t in TEAM.values()] if role == "ALL" else [TEAM[role][0]]

        if title in existing:
            number = existing[title]
            skipped += 1
        elif DRY:
            print(f"[dry] {J[ms]:30} {role:3} {title}  labels={labels}")
            continue
        else:
            args = ["issue", "create", "-R", REPO, "-t", title, "-b", body(role, start, end, handoff, ref), "-m", J[ms]]
            for lb in labels:
                args += ["-l", lb]
            url = gh(*args).stdout.strip()
            number = int(url.rsplit("/", 1)[1])
            created += 1
            print(f"#{number:<3} {role:3} {title}")

        if DRY:
            continue
        for a in assignees:  # one by one: a pending invitee must not block the others
            if gh("issue", "edit", str(number), "-R", REPO, "--add-assignee", a, check=False).returncode != 0:
                unassigned.append((number, a))

    if not DRY:
        print(f"\ncreated={created} already-existing={skipped}")
        if unassigned:
            people = sorted({a for _, a in unassigned})
            print(f"could not assign {len(unassigned)} issue/person pairs (invitation not accepted yet?): {', '.join(people)}")
            print("re-run this script once they accept.")


if __name__ == "__main__":
    main()
