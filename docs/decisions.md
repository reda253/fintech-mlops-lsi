# Architecture decisions

Rule (§10.7): **every new architecture decision is added here**, in the PR that implements it. D1–D32 come from the architecture document v1.0 (§2.6), where the alternatives and full justifications are listed.

| # | Decision | Rejected alternatives | Why |
|---|---|---|---|
| D1 | Sparkov dataset | ULB, PaySim, IEEE-CIS | Customers, merchants and categories map onto our services; time split already provided |
| D2 | GitHub monorepo | One repo per service | Simpler for 5 people and Argo CD; one PR can change a contract and both sides |
| D3 | Local kind cluster | Managed cloud | Free; enough for replicas, HPA, probes, rollback |
| D4 | Sync REST + RabbitMQ for notification/audit | REST only, Kafka | Takes non-critical services off the payment path; lighter than Kafka |
| D5 | One PostgreSQL instance, one schema + user per service | One DB per service | Logical isolation kept, ~1 GB RAM saved |
| D6 | JWT validated at the gateway and re-validated by each service | Service tokens, mTLS | Enough for scope; defence in depth |
| D7 | Kubernetes-native service discovery | Eureka | DNS + Services are enough |
| D8 | GitHub Actions (CI) + Argo CD (CD) | Self-hosted runner, manual deploy | Cluster never exposed; rollback via Git |
| D9 | ML pipeline = GitHub Actions + MLflow | Prefect | One less tool |
| D10 | SonarCloud | Self-hosted SonarQube | Free for public repos, no RAM cost |
| D11 | Calibration + conformal prediction (MAPIE) | Ensembles, bootstrap | Statistical coverage guarantee justifies human review |
| D12 | Three-way decision | Two-way | Certain cases automated, uncertain ones go to a human |
| D13 | Preprocessing inside the model pipeline; ml-service gets raw fields | Features computed in Java | No train/serve skew |
| D14 | In-app notifications only (stored + SSE) | Email, logs | Light, visible in the demo |
| D15 | Transactional outbox | Publish after commit | No lost events when pods are killed |
| D16 | Notification and audit owned by P1 | Owned by P4 | All Spring code under one owner |
| D17 | No customer-history features (stateless model) | 24 h aggregates | Simpler; Sparkov already separable |
| D18 | Gender and age kept, with a fairness audit | Drop them | Synthetic data, transparent audit |
| D19 | Simulated chargebacks: delayed true labels | Analyst labels only | Real production precision/recall/coverage |
| D20 | Model version pinned in Git, promoted by auto-merged PR (`AUTO_MERGE`) | Manual PR, MLflow alias + hot reload | Git is the single source of truth |
| D21 | Traefik ingress controller | Ingress NGINX (retired 03/2026), Envoy Gateway | Maintained, light, standard `Ingress` |
| D22 | Sealed Secrets | Secrets created by script | Everything deployable from Git |
| D23 | kind with 3 nodes | Single node | Replica spread and node-failure test |
| D24 | Automatic rollback via Git after failed e2e | Argo Rollouts | Simple, consistent with D20 |
| D25 | Security bonuses (cosign, ZAP) postponed | Plan them now | Only if time remains after S12 |
| D26 | Alerts to Discord | Slack, Grafana only | Free, on phones during the demo |
| D27 | Loki + Grafana Alloy | kubectl logs | Search by correlationId (~0.6 GB RAM) |
| D28 | k6 on a second laptop | k6 on the cluster machine | Unbiased measurements |
| D29 | 3 runs per experiment, median + range | Single run | Robust results |
| D30 | Spring Boot 4.1 + Java 21 | Boot 3.5, Java 25 | 3.x out of OSS support since 06/2026 |
| D31 | Reactive Spring Cloud Gateway (WebFlux) | Gateway Server MVC | Best documented, fits SSE |
| D32 | Contract-first OpenAPI | Code-first | Unblocks P3/P4/P5 from S2; CI checks code against contract |

## New decisions (after v1.0)

| # | Date | Decision | Rejected alternatives | Why |
|---|---|---|---|---|
| D33 | 2026-10-04 | `POST /api/v1/transactions` carries the raw card number (`cardNumber` = Sparkov `cc_num`). transaction-service resolves it with `POST /internal/customers/lookup` on customer-service (cached), then stores only `customerId` + `cardLast4` | Simulator sends `customerId`; transaction-service computes the HMAC | The simulator cannot know internal ids, and the HMAC key must stay in customer-service only (§6.9). Adds the flow transaction → customer to the NetworkPolicies (P4) |
| D34 | 2026-10-04 | risk-service reads the customer through `GET /internal/customers/{id}/risk-profile` (only the 6 fields `/predict` needs), not the public `GET /api/v1/customers/{id}` | Public endpoint with the propagated token | The propagated token is SIMULATEUR, which has no customer-read right (§3.8). Also data minimisation |
| D35 | 2026-10-04 | The audit schema is owned by `audit_migrator` (Flyway only). The runtime `audit_user` gets INSERT + SELECT through default privileges | `audit_user` owns the schema | A schema owner can always UPDATE/DELETE, so append-only would not be enforced by the database |
| D36 | 2026-10-04 | Users CRUD lives under `/api/v1/auth/users` | `/api/v1/users` | Keeps the one-prefix-per-service routing rule (`/api/v1/{domain}/**`) |
| D37 | 2026-10-04 | SSE auth uses the `Authorization` header (frontend: `@microsoft/fetch-event-source`) | Token in the query string | Tokens in URLs end up in access logs |
| D38 | 2026-10-19 | `common` ships Spring Boot auto-configurations (correlation filter, Problem Details advice, resource-server `SecurityFilterChain`). Services add role rules through `AuthorizationRules` beans | A base class or `@Import` in every service; one hand-written `SecurityFilterChain` per service | One place to fix bugs (P1 plan, "write it once"). Same probe, 401/403 and JWT rules in every service. The gateway (WebFlux) is untouched: the web dependencies are optional and the configs are servlet-only |
| D39 | 2026-10-19 | JSON logs use Spring Boot's built-in ECS format (`service.name`, MDC → `correlationId`), set by `common`. `LOG_FORMAT=plain` turns it off for local runs | Logstash encoder dependency; per-service `logback-spring.xml` | No extra dependency, no per-service config. Loki/Alloy parse ECS as plain JSON (D27) |
| D40 | 2026-10-19 | An incoming `X-Correlation-Id` that is not a UUID is replaced with a new one | Trust any value | The header comes from the client and goes into every log line and event (log injection). The contract already declares `format: uuid` |
| D41 | 2026-10-29 | auth-service RS256 key: only the private key (PKCS#8 PEM) is configured, from the K8s Secret `JWT_PRIVATE_KEY`; the public key is derived from it and `kid` = RFC 7638 thumbprint. Rotation is manual: emergency = replace the Secret and restart auth; planned = publish old + new public keys in the JWKS for 15 min (access-token lifetime) | Key generated at startup; separate public-key secret; automatic scheduled rotation | Replicas generating their own key would publish different JWKS and cause random 401s. One secret cannot get out of sync. Refresh tokens are opaque DB tokens, not signed, so a rotation never forces users to log in again. Automatic rotation is out of scope |
| D43 | 2026-11-08 | `GET /actuator/prometheus` is open without a token in every Java service (`common`) and in the gateway. The rest of the actuator still needs a JWT, except the two probes. Keeping it internal is a network job. In place: the Ingress (`deploy/k8s/apps/ingress.yaml`) sends only `/api` to the gateway and `/` to the frontend, so no service port is reachable from outside the cluster. **Still required before production** (P4): a NetworkPolicy that lets only the `monitoring` namespace reach service ports; until then any pod inside the cluster can read the metrics | Keep the token and give Prometheus a JWT; separate management port for the actuator | Prometheus cannot get or refresh a 15-min JWT, and a long-lived token would be a secret to manage. A management port changes every Deployment, Service, probe and ServiceMonitor; it stays the upgrade path if the NetworkPolicy approach is not enough. Already enforced in code: the gateway never routes `/actuator/**` (NeverRoutedTest), and only `GET` on the exact path is open. Metrics hold no secrets |
| D42 | 2026-11-08 | Login rate limit (`POST /api/v1/auth/login`) is in memory, per gateway pod: GCRA token bucket per client IP, default burst 5 refilled over 1 min (`LOGIN_RATE_LIMIT_CAPACITY`, `LOGIN_RATE_LIMIT_PERIOD`). Client IP = last `X-Forwarded-For` entry (the one Traefik appends). Refusal = `429` Problem Details + `Retry-After` | Redis + Spring Cloud Gateway `RedisRateLimiter`; sticky sessions at Traefik; Traefik `RateLimit` middleware; first `X-Forwarded-For` entry | The goal is to slow brute force, not to enforce an exact quota, and the spec rules out Redis (§3.4). With N replicas the effective limit is about N times higher and a pod restart resets it; both are accepted. Sticky sessions would break the even balancing that the 30 s pool lifetime relies on. The first `X-Forwarded-For` entry is client-controlled, so a forged header would give a fresh limit on every request. Upgrade path: `RedisRateLimiter`, no route change |
| D44 | 2026-11-10 | **Post hoc**, Basma accepts alpha grid {0.01, 0.02, 0.03, 0.05, 0.10} and review capacity <= 2%; select the smallest eligible alpha using choice-block review rate only, without labels. The review rate is not monotonic because empty and ambiguous sets both require review. The previously observed evaluation block gives exploratory results after this change | Retain the previous grid; increase review capacity | Investigate the review-rate minimum while keeping the capacity gate; log the protocol-change reason before rerunning |
| D45 | 2026-11-09 | **Post hoc**, Basma sets the non-negligible PR-AUC effect threshold to 0.01; selection remains provisional and no champion is promoted automatically | Leave the threshold unspecified | Transparently record the decision made after benchmark results were observed |
| D46 | 2026-11-05 | **Post hoc** internal chronological splits: 50/50 for calibrator fit/comparison; 50/25/25 for conformal quantile fit/alpha choice/evaluation | Reuse the same observations for fitting and evaluation | Keep the comparisons and evaluations distinct; this precision was made after observing the benchmark |
| D47 | 2026-11-12 | Shared environments run with `AUTH_DEMO_ACCOUNTS=false`: at startup auth-service disables the three V2 demo accounts (sessions revoked) and creates a bootstrap ADMIN from a Sealed Secret (`AUTH_BOOTSTRAP_ADMIN_USERNAME`/`_PASSWORD`, created only if absent, never overwritten). It refuses to start if demo accounts are off and no enabled ADMIN exists. Then one personal account per member: ADMIN for Reda, Assil and Hakima, ANALYSTE for all five; one SIMULATEUR service account for the simulator and a separate one for k6. Local dev keeps the demo accounts | Edit `V2__seed_users.sql`; a V3 migration that disables them everywhere; keep the demo accounts with changed passwords | The V2 passwords are public in the README, including an ADMIN. Editing V2 breaks the Flyway checksum on databases that already ran it, and a V3 would also break local dev and the e2e tests. Creating users needs an ADMIN, so the first one must come from config. Separate service accounts keep simulator and load-test traffic apart in the audit log |
| D48 | 2026-11-12 | **Post hoc**, accord écrit d’Omar transmis par Basma : accord conditionnel pour une seule seconde mesure du candidat D44 figé : aucune exécution avant merge des correctifs, CI verte et intégration de l’option B. Seule la CLI `evaluate_final_candidate.py` lit la source finale ; le Job consomme ses artefacts vérifiés | Réévaluer avec réglage du modèle ; deux lecteurs officiels du jeu final ; relances par simple changement de motif | Compléter les IC bootstrap et l’audit d’équité absents le 10 novembre, sans nouvelle sélection ni promotion. Seconde mesure post hoc, non indépendante ; conditions détaillées ci-dessous |

## D48 — autorisation conditionnelle de seconde mesure

Accord d’Omar communiqué par Basma le **12 novembre 2026**. Cette entrée
consigne l’accord ; elle ne certifie ni le merge, ni la CI distante, ni
l’intégration ou le déploiement de l’option B. Aucun lancement n’est effectué
par cette décision documentaire.

- Modèle figé : SHA-256
  `aa1565caf7fed3af833a5613fd76416b6489c9a9f31ee8c523d65e5d9113da33`.
- Source finale : même SHA-256 que le 10 novembre,
  `7e50d0ce13f08b45ed1740127fe56f9c90c8eeec37a11288a372afcc61efe3b3`.
- Alpha = **0,02**, beta, calibrateur, preprocessing et quantiles inchangés :
  aucun entraînement, aucune calibration, sélection d’alpha ou modification de seuils.
- Objet : IC bootstrap et audit d’équité manquants lors de la mesure du
  10 novembre. D48 est une **seconde mesure post hoc, non indépendante**.
  Les résultats du 10 novembre sont conservés et identifiés dans le rapport ;
  ils ne sont ni écrasés ni présentés comme une confirmation indépendante.
- Définitions gelées par genre et tranche d’âge : fraude bloquée automatiquement
  = ensemble `[1]` ; fraude interceptée = blocage ou revue ; faux positif réel
  = légitime dans `[1]` ; revue = ensemble `[]` ou `[0,1]`. Les effectifs,
  dénominateurs et mesures indéfinies doivent être explicites. Les indicateurs
  au seuil ponctuel 0,5 sont secondaires.
- Bootstrap : 10 000 tirages, seed 42, IC percentile à 95 %, unité transaction,
  mêmes tirages pour les métriques et groupes ; hypothèse d’indépendance des
  transactions signalée comme limite.
- Préconditions : code corrigé mergé, tests et CI verts, option B intégrée et
  vérifiée, protocole exact approuvé et empreinte enregistrée, sauvegarde du
  premier résultat et du journal. Ces préconditions restent à confirmer avant exécution.
- Journal central configurable sur un volume monté, hors dépôt, réservé avant
  lecture ; liaison décision/source/modèle/texte du protocole. Une exécution
  complétée consomme D48, indépendamment du motif et du nom de révision. Toute
  autre exécution exige une nouvelle décision explicite.
- Prédictions sauvegardées immédiatement et atomiquement, SHA-256 dans le
  manifeste vérifié ; métriques, IC, équité, rapports et empreintes publiés dans
  MLflow. Les prédictions locales sensibles restent protégées ; leur publication
  éventuelle requiert un emplacement et des droits explicitement convenus.
- Option **B**, décidée par Omar : la CLI est le seul lecteur final ;
  `step_evaluate` consomme `final_metrics.json`, les portes et le hash du candidat,
  et refuse une absence ou incohérence. `run.py` ne charge plus `--test-path`
  pour l’évaluation finale. `final_metrics.py` demeure partagé. L’adaptation
  du pipeline revient à Omar ; cette décision ne prétend pas qu’elle est déjà intégrée.
- Tout problème d’équité est publié tel quel : aucun réglage des seuils ou
  changement post hoc des définitions après observation. XGBoost reste
  **provisional** ; aucune promotion n’est autorisée dans cette mesure.
