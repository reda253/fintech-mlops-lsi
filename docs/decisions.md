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
| D49 | 2026-11-21 | Outbox and idempotent consumer in `common` use plain JDBC (`JdbcClient`), not a JPA entity. The relay sends the stored envelope bytes unchanged (`message_id`, `X-Correlation-Id`, persistent, publisher confirm awaited before marking). Every AMQP service declares the whole durable topology of `contracts/events.md` (exchanges, queues, DLQs, bindings). Retry/DLQ rules (3 attempts, then reject → `fintech.dlx`) and `publisher-confirm-type=correlated` are lowest-priority defaults set by `common`. The relay is opt-in (`fintech.outbox.enabled=true`: auth, transaction, risk). Services pin `spring.datasource.hikari.schema` so plain JDBC hits their schema | JPA `OutboxEvent` entity; re-serialize at publish time; each consumer declares only its own queue; retry settings copied into every `application.yml` | Native `FOR UPDATE SKIP LOCKED`, `jsonb` and `ON CONFLICT` with no `@EntityScan` across packages, and the insert still joins the JPA transaction. A queue that does not exist yet makes the topic exchange drop the event while the confirm still says ack, so producers must declare it too. One place for delivery rules ("write it once") |
| D50 | 2026-11-22 | customer-service loads the Sparkov cardholders at startup from the raw CSV files named in `CUSTOMER_SEED_PATH` (one customer per `cc_num`, customer columns only, never `is_fraud`), computing the HMAC fingerprint with `CARD_HMAC_KEY`. It runs only when the table is empty, in one transaction, with `ON CONFLICT DO NOTHING`, before readiness. The card-number pattern is widened to 11–19 digits in the customer and transaction contracts | Flyway SQL data migration; admin CSV import endpoint; one-shot K8s Job | A SQL migration cannot compute the HMAC without the key, and committing card numbers or a key-dependent seed is out of the question. An import endpoint needs a manual step after every fresh deploy. A Job adds a manifest for the same result. Sparkov has 11-digit card numbers, which the old 12–19 pattern rejected |
| D48 | 2026-11-12 | **Post hoc**, accord écrit d’Omar transmis par Basma : accord conditionnel pour une seule seconde mesure du candidat D44 figé : aucune exécution avant merge des correctifs, CI verte et intégration de l’option B. Seule la CLI `evaluate_final_candidate.py` lit la source finale ; le Job consomme ses artefacts vérifiés | Réévaluer avec réglage du modèle ; deux lecteurs officiels du jeu final ; relances par simple changement de motif | Compléter les IC bootstrap et l’audit d’équité absents le 10 novembre, sans nouvelle sélection ni promotion. Seconde mesure post hoc, non indépendante ; conditions détaillées ci-dessous |
| D51 | 2026-11-22 | Reprise `--resume` d'une exécution D48 interrompue après `predictions_saved` : métriques et IC reconstruits depuis `predictions.csv` vérifié, manifeste complété, `completed` enregistré avec le même `launch_id`, sans relire le jeu final | Relancer la mesure (seconde lecture) ; éditer le journal ; laisser la réservation bloquer D48 | La source finale reste lue une seule fois ; le protocole approuvé est inchangé |
| D52 | 2026-11-28 | **Constat d'équité D48 documenté et modèle conservé** : les écarts mesurés (blocage automatique F 94,42 % vs M 98,17 % ; légitimes bloqués 1,60 % vs 1,06 % ; revue 0,84 % vs 0,51 % ; 7 506 légitimes bloqués pour 2 062 fraudes, précision 21,55 % ; 60 fraudes approuvées automatiquement, 2,80 %) sont publiés tels quels, sans réglage post-mesure. La future évaluation indépendante utilisera des **données nouvelles** (trafic de production avec étiquettes de chargeback, D19, ou jeu acquis séparément), avec protocole pré-enregistré avant toute remédiation, développée sur le développement uniquement | Régler les seuils sur le test final ; réutiliser `fraudTest.csv` pour valider la remédiation ; retirer les attributs | Le test final a été lu deux fois (10 novembre et D48) et aucun bloc n'en reste inutilisé ; toute remédiation validée sur ce même jeu serait circulaire. Le constat reste descriptif : causes non établies, indépendance des transactions supposée, comparaisons d'âge exploratoires |
| D53 | 2026-11-28 | **Dérogation unique** pour une nouvelle tentative après interruption : document signé ciblant un `launch_id`, l'état constaté et les empreintes modèle/source/protocole/journal ; consommée sous `journal_lock` (clôture `failed` si nécessaire, puis réservation avec `supersedes`), compteur dans le journal, rejeu impossible. Garde renforcée : toute tentative D48 antérieure bloque, `completed` refuse toujours | Contourner le blocage par un nouveau `decision_id` ; expiration automatique ; réutiliser la dérogation | Préserve la lecture unique et l'immutabilité du journal ; une interruption entre `failed` et `reserved` reste bloquante et exige une nouvelle revue. Proposée, non implémentée |

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
  premier résultat et du journal.
  État au 20 novembre 2026 : code mergé (`bc30b93`, PR #117) et CI verte ;
  option B intégrée et vérifiée ; journal du 10 novembre et son dossier
  `previous_evaluation/` à fournir ; autorisation `approved: true` à produire
  après réception du hash du journal. La source finale normalisée en LF donne
  `7e50d0ce…` et le joblib gelé `aa1565ca…`, conformes à D44.
- Protocole D48 enregistré : texte `docs/final_evaluation_protocol.md` au commit
  `bc30b93` (inchangé sur `main`), SHA-256
  `b0bfaf9ba5b9c3b40dc91c52d34281227846fce4d11b24ff6bf9a166550adc24`. Toute
  modification du texte change cette empreinte et exige une nouvelle autorisation.
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
  pour l’évaluation finale. `final_metrics.py` demeure partagé. L’intégration
  (PR #117) exige en plus le joblib gelé (`--candidate-model`) : son empreinte
  doit être celle du candidat D44, la source doit être celle approuvée pour D48,
  et le modèle servi par MLflow doit produire les mêmes probabilités sur une
  sonde fixe. Les métriques sont bornées et cohérentes avec leurs effectifs.
- Tout problème d’équité est publié tel quel : aucun réglage des seuils ou
  changement post hoc des définitions après observation. XGBoost reste
  **provisional** ; aucune promotion n’est autorisée dans cette mesure.

## D51 — Résolution d'une exécution D48 interrompue

Décision du **22 novembre 2026**, après incident.

**Contexte.** L'exécution D48 a été lancée une fois puis interrompue : le journal
contient `reserved` et `predictions_saved`, sans entrée terminale, et le dossier
de sortie ne contient que `predictions.csv` (555 719 lignes, empreinte conforme
au manifeste) et un manifeste `status=predictions_saved`. Cause identifiée : le
bootstrap de 10 000 rééchantillonnages prenait environ 99 minutes sans aucune
sortie, et la machine a été interrompue. Le jeu final a donc déjà été lu une
fois ; une relance normale serait une seconde lecture, interdite par D48.

**Décision.** Ajouter une reprise `--resume <dossier>` à la CLI officielle. Elle
vérifie le manifeste et l'empreinte de `predictions.csv`, reconstruit les
métriques, les IC et l'équité à partir des prédictions sauvegardées (sans
relire `fraudTest.csv`), réécrit le manifeste complet, puis enregistre
`completed` avec le **même** `launch_id`. Le protocole approuvé
(`b0bfaf9b…adc24`) n'est pas modifié et aucune nouvelle autorisation n'est
nécessaire.

**Motifs.** La lecture unique est préservée ; la source finale reste lue par un
seul programme ; les artefacts repris sont produits par le même code que
l'exécution normale (`summarize_details` et `finish` sont partagés), donc
identiques à ceux d'une exécution non interrompue.

**Conséquences.** Le bootstrap est parallélisé au niveau du noyau de calcul
(masques précalculés, sommes entières via `bincount`) et affiche sa progression
toutes les 500 réplications ; la reprise reste une opération manuelle et
explicite, jamais automatique. Une interruption avant `predictions_saved` ne
laisse aucune reprise possible : `record_event` n'écrit pas d'entrée `failed`,
ce qui reste une lacune connue du journal.

**Numérotation.** Cette décision a d'abord été publiée sous `D49`, en collision
avec `D49` (outbox et consommateur idempotent, 21 novembre). Elle est renumérotée
`D51` après confirmation de P1 le 28 novembre ; `D49` reste réservé à l'outbox et
n'est pas modifié. Le journal réel de la mesure n'a enregistré que des entrées
`D48` : aucun journal ne porte `D49` pour cette reprise, il n'y a donc rien à
réécrire.

## D52 — Équité : constat, conservation du modèle, surveillance

Décision du **28 novembre 2026**, après l'audit d'équité de D48. Proposition
soumise à la validation de P1 (Reda) et de P2 (Basma).

**Constat (descriptif, test final, IC 95 %, 10 000 tirages).**

| Groupe | N | Fraudes | Bloquées auto | Légitimes bloqués | Revue |
|---|---:|---:|---|---|---|
| F | 304 886 | 1 164 | 94,42 % [93,04 ; 95,71] | 1,60 % [1,55 ; 1,64] | 0,84 % [0,80 ; 0,87] |
| M | 250 833 | 981 | 98,17 % [97,28 ; 98,95] | 1,06 % [1,02 ; 1,10] | 0,51 % [0,49 ; 0,54] |

Au total, 7 506 légitimes bloquées pour 2 062 fraudes bloquées, soit 3,64 pour 1
et une précision des blocages de 21,55 % ; 60 fraudes ont été approuvées
automatiquement (2,80 %). Par tranche d'âge, le blocage automatique va de
94,39 % (26–35) à 98,64 % (0–25), écarts exploratoires.

**Décision.** Publier ces écarts tels quels et **conserver le modèle actuel**,
sans aucun réglage post-mesure : ni seuil conformal, ni calibration, ni
sélection. Aucun verdict binaire d'équité n'est tiré de l'audit ; les causes ne
sont pas établies, les comparaisons d'âge restent exploratoires et
l'indépendance des transactions est supposée (la corrélation par carte n'est pas
corrigée).

**Évaluation indépendante future.** Le test final a été lu deux fois
(10 novembre et D48) et aucun bloc n'en reste inutilisé : une future évaluation
ne peut donc pas venir de `fraudTest.csv`. Elle utilisera **des données
nouvelles** — trafic de production postérieur au déploiement avec étiquettes de
chargeback (D19), ou un jeu acquis séparément — avec un protocole pré-enregistré
**avant** tout travail de remédiation. La remédiation elle-même se développe
uniquement sur le développement ; aucun chiffre du test final ne sert à la
valider.

**Statut : proposition, en attente de validation.** Aucun accord écrit n'est
consigné à ce jour. La date et les références des accords P1 (Reda) et P2
(Basma) seront ajoutées ici dès qu'elles existeront ; tant qu'elles manquent, la
mention reste « en attente de validation ».

**Acceptation et surveillance (proposées).** Acceptation de l'écart F/M en
l'état par P1 (Reda) et P2 (Basma). Surveillance : audit hors ligne mensuel
(`ml.fairness.audit` sur les prédictions sauvegardées) lu par P2, et tableau de
bord agrégé par P5 (Hakima). Seuil d'alerte **proposé**, à fixer par l'équipe :
écart de blocage automatique F/M supérieur à 5 points, ou rapport de taux de
revue supérieur à 2.

**Portée.** Conserver le candidat sans réglage ne vaut **ni approbation de
l'alias `champion` existant, ni clôture de #32**. La promotion est traitée
séparément : l'alias a été déplacé le 27 novembre sans accord écrit, et D52 ne
régularise pas cet état.

Limite technique : le service n'expose pas de dimension genre ou tranche d'âge
dans Prometheus (`ml_predictions_total{model_version,prediction_set}`). La
surveillance par groupe est donc hors ligne, à partir des prédictions
sauvegardées ; ajouter ces labels serait un changement de code et de
cardinalité, à décider séparément.

## D53 — Dérogation unique pour une nouvelle tentative

Décision du **28 novembre 2026**, proposition soumise à revue. Non implémentée :
aucun code, aucun test, aucune lecture du test final.

**Objet.** Une interruption sans entrée terminale bloque la source pour toute
nouvelle réservation, y compris avec un nouveau `decision_id`. La dérogation est
un document signé qui **clôture** une tentative bloquée et autorise **une**
réservation supplémentaire pour cette source. Elle ne contourne pas la garde,
elle la débloque explicitement.

**Mécanisme et autorisation sont distincts.** D53 décrit un mécanisme futur, pas
une autorisation. Il ne s'active que sur un document signé distinct, ciblant un
`launch_id` précis et un état constaté ; sans ce document, la garde refuse toute
réservation. Et il ne peut concerner qu'une mesure **non terminée** : D48 est
`completed`, donc D53 ne peut ni rouvrir D48 ni provoquer une nouvelle lecture
du test final. **Cette PR n'autorise aucune nouvelle lecture du test final,
aucune relance de D48 et aucune promotion.**

**Interdits.** Elle ne peut servir ni à sélectionner ni à régler un modèle, ni à
changer de seuil, ni à promouvoir, ni à provoquer une nouvelle lecture du test
final. Elle ne remplace pas `--resume` (D51), qui reste le seul chemin sans
nouvelle décision et uniquement après `predictions_saved`.

**Garde renforcée.** Toute nouvelle réservation est refusée s'il existe déjà une
tentative D48 pour cette source, quel que soit son statut (`reserved` pendant,
`failed`, `predictions_saved`, `completed`), sauf dérogation valide. Une entrée
`completed` refuse toujours, dérogation comprise. Les ancres historiques du
10 novembre ne comptent pas comme tentative : elles n'ont pas de `decision_id`.

**Document.** `decision_id: D53`, `launch_id` visé, état constaté
(`unknown_source_state`), `model_sha256`, `source_sha256`, `protocol_sha256`
(protocole D48 approuvé), `journal_sha256` des octets relus, `approved: true`.
Toute empreinte différente des constantes approuvées ou du journal courant est
refusée : la dérogation est liée à un état précis.

**Deux situations couvertes.** (a) *réservation pendante sans `failed`* : la
dérogation autorise l'ajout d'une entrée terminale `failed` pour ce
`launch_id` — `decision_id: D48`, catégorie fermée `unknown`,
`derogation_decision_id: D53`, `derogation_sha256` — puis la nouvelle
réservation ; (b) *tentative déjà `failed`* : aucune entrée `failed`
supplémentaire, seulement la réservation avec `supersedes: <launch_id>`. Dans
les deux cas la réservation porte `decision_id: D48`,
`derogation_decision_id: D53`, `supersedes` et `derogation_sha256`. La mesure
initiale et la décision qui la rouvre restent distinctes sur la même ligne.

**Usage unique et verrou.** Lecture du journal, contrôle de la cible, contrôle
que `derogation_sha256` n'apparaît nulle part, clôture éventuelle et écriture de
la réservation se font sous le **même `journal_lock`**. Le compteur est dans le
journal : une copie du document ne permet aucun rejeu, un second processus
trouve le hash déjà enregistré et refuse.

**Interruption entre les deux écritures.** Si `failed` est écrit et la
réservation de remplacement ne l'est pas, l'état reste bloquant : une relance
normale est refusée (une tentative D48 existe), la même dérogation est refusée
(hash déjà consommé), et seule une **nouvelle** dérogation ciblant la tentative
désormais `failed` permet de continuer. C'est une revue manuelle explicite, pas
une reprise automatique.

**Tests prévus.** Refus si modèle, source, protocole ou journal diffèrent ;
refus si le `launch_id` est inconnu, `completed` ou déjà `predictions_saved` ;
chemin « pendante » avec ajout de `failed` puis réservation ; chemin « déjà
failed » sans nouvelle entrée `failed` ; rejeu refusé ; concurrence : une seule
réservation ; interruption entre les deux écritures : relance et ancienne
dérogation refusées, nouvelle dérogation acceptée ; `completed` refuse même avec
dérogation. Responsable : P3 (Omar).
