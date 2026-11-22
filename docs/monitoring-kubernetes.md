Monitoring Kubernetes — kube-prometheus-stack, ServiceMonitors, Loki & Grafana Alloy
Projet : FinTech MLOps LSI
Issue GitHub : #49 — K8s monitoring (kube-prometheus-stack, ServiceMonitors) + Loki/Alloy
Responsable : P5 — Frontend & Observability
Spécifications : §8.1, §8.6, §8.7 (docs/specs/P5_Frontend_Observabilite_1.md, Décisions D22, D27, D39, D43)

1. Objectif
Déployer la pile complète d'observabilité Kubernetes dans le namespace monitoring afin de :

Superviser automatiquement les métriques du cluster Kubernetes, des 7 microservices Spring Boot (fintech), du service d'inférence FastAPI (ml), ainsi que des briques de données (data : PostgreSQL, RabbitMQ) grâce à kube-prometheus-stack et aux ressources ServiceMonitor / Probe.
Centraliser les logs JSON structurés de tous les pods via Grafana Alloy (DaemonSet) et Loki (mode monolithique), permettant le suivi de bout en bout d'une transaction par correlationId sans alourdir l'index de Loki.
2. Architecture (§8.1 & §8.6)
text

                       Cluster Kubernetes (kind)
                                  |
     +----------------------------+----------------------------+
     |                            |                            |
Namespaces : fintech / ml / data  |                  Namespace : monitoring
- 7 services Spring Boot          |                  - Prometheus Operator
  (/actuator/prometheus - D43)    |--- scrape 15s -->| - Prometheus (PVC 5Gi, 7j)
- ml-service FastAPI (/metrics)   |                  - Alertmanager
- RabbitMQ (:15692/metrics)       |                  - Grafana (Dashboards + Explore)
- postgres-exporter (:9187)       |                  - kube-state-metrics & node-exporter
     |                            |                            ^
     | Logs JSON (stdout - D39)   |                            |
     +----------------------------+---> Grafana Alloy          |
                                         (DaemonSet)           |
                                              |                |
                                              v                |
                                            Loki --------------+
                                   (Monolithique, PVC 5Gi, 72h)
3. Composants et budget de ressources (§6.5, §8.1, §8.6)
Composant	Rôle	Mode / Déploiement	Budget RAM (Request / Limit)	Stockage & Rétention
Prometheus	Collecte et évaluation PromQL (15s)	StatefulSet (Operator)	512 Mi / 1 Gi	PVC 5 Gi, rétention 7d
Grafana	Visualisation métriques & logs (Explore)	Deployment	128 Mi / 256 Mi	Sidecar ConfigMaps + Loki
Alertmanager	Regroupement, inhibition et routage	StatefulSet	64 Mi / 128 Mi	Rétention 120h
Loki	Stockage centralisé des logs JSON	StatefulSet monolithique	256 Mi / 512 Mi	PVC 5 Gi, rétention 72h (3j)
Grafana Alloy	Collecte des logs de tous les pods	DaemonSet (1 pod / nœud)	64 Mi / 100 Mi	Sans état (buffer /tmp)
Exporters K8s	kube-state-metrics + node-exporter	Deployment / DaemonSet	32 Mi / 64 Mi chacun	—
L'ensemble de la brique Loki + Alloy respecte l'enveloppe d'environ 0,6 Go de RAM fixée par la décision D27 et la section §8.6.

4. Organisation des fichiers
text

fintech-mlops-lsi/
├── monitoring/
│   ├── prometheus.yml                          # Config locale Docker Compose (#47)
│   ├── grafana/                                # Provisioning local Docker Compose (#47)
│   └── k8s/                                    # Manifests & Helm values Kubernetes (#49)
│       ├── namespace.yaml                      # Namespace monitoring
│       ├── kube-prometheus-stack-values.yaml   # Valeurs Helm kube-prometheus-stack (§8.1)
│       ├── servicemonitors.yaml                # ServiceMonitors & Probe blackbox (§8.1, §8.2)
│       ├── loki.yaml                           # Loki monolithique + règles d'alerte logs (§8.6)
│       ├── alloy.yaml                          # Grafana Alloy DaemonSet + RBAC (§8.6)
│       ├── kustomization.yaml                  # Point d'entrée Kustomize
│       └── test_monitoring_k8s.py              # Tests unitaires de conformité (§8.1 & §8.6)
└── docs/
    ├── monitoring-docker.md                    # Documentation Docker Compose (#47)
    └── monitoring-kubernetes.md                # Documentation Kubernetes & Loki (#49)
5. Découverte automatique des cibles (ServiceMonitors & Décision D43)
Chaque composant est supervisé via une ressource ServiceMonitor portant le label release: prometheus (monitoring/k8s/servicemonitors.yaml) :

fintech-spring-boot-services (namespace fintech) :
Cible les 7 services Spring Boot : api-gateway, auth-service, customer-service, transaction-service, risk-service, notification-service, audit-service.
Scrape GET /actuator/prometheus sur le port http toutes les 15s (ouvert sans token JWT à l'intérieur du cluster conformément à la décision D43).
Réécrit automatiquement le label Kubernetes app vers application=<nom-du-service> (§8.2).
ml-service (namespace ml) :
Scrape GET /metrics sur le port http (8000) toutes les 15s.
rabbitmq & postgres-exporter (namespace data) :
Scrape le plugin Prometheus de RabbitMQ sur le port metrics (15692) et l'exporteur PostgreSQL (9187) toutes les 15s.
fintech-http-blackbox (Probe) :
Vérifie la disponibilité HTTP de frontend et api-gateway (/actuator/health/readiness).
loki & alloy (namespace monitoring) :
Auto-supervision de la pile de logs sur /metrics.
6. Logs centralisés avec Loki et Grafana Alloy (§8.6, Décisions D27 & D39)
6.1 Collecte et parsing JSON (monitoring/k8s/alloy.yaml)
Les services Spring Boot émettent leurs logs sur la sortie standard au format JSON ECS contenant service.name, log.level et le correlationId issu du MDC (décision D39). Le ml-service émet également des logs structurés contenant correlationId.

Le DaemonSet Grafana Alloy :

Découvre automatiquement tous les pods actifs du cluster (discovery.kubernetes "pods").
Extrait les métadonnées Kubernetes (namespace, app, pod).
Parse le niveau de log JSON (log.level ou level) dans le label level.
Applique un filtre strict stage.label_keep pour ne conserver que 4 étiquettes indexées dans Loki :
namespace
app
pod
level
Pourquoi correlationId n'est pas un label Loki (§8.6) :
Indexer un identifiant unique par transaction créerait des millions de séries temporelles (explosion de cardinalité et saturation de la mémoire de Loki). Le correlationId reste dans le corps JSON et est filtré à la volée avec | json | correlationId="...".

6.2 Stockage et alertes sur les logs (monitoring/k8s/loki.yaml)
Mode monolithique (SingleBinary) avec stockage TSDB v13 sur disque (PVC 5 Gi).
Rétention de 3 jours (72h) assurée par le compactor (retention_enabled: true, retention_period: 72h).
Règles d'alerte Loki (fintech-log-alerts.yaml) :
JavaOutOfMemoryErrorInLogs (critical) : déclenchée dès l'apparition de OutOfMemoryError dans les logs d'un pod fintech.
MlModelLoadFailureInLogs (critical) : déclenchée en cas d'erreur de chargement du modèle ML dans ml-service.
7. Déploiement et commandes de vérification
7.1 Exécuter les tests automatisés de conformité
Bash

python -B -m unittest discover -s monitoring/k8s -p "test_*.py"
7.2 Valider le rendu Kustomize
Bash

kubectl kustomize monitoring/k8s
7.3 Installer kube-prometheus-stack et la pile Loki / Alloy dans le cluster
Bash

# 1. Créer le namespace monitoring
kubectl apply -f monitoring/k8s/namespace.yaml

# 2. Ajouter le dépôt Helm prometheus-community et installer kube-prometheus-stack
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm upgrade --install prometheus prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  -f monitoring/k8s/kube-prometheus-stack-values.yaml

# 3. Déployer Loki, Grafana Alloy et les ServiceMonitors
kubectl apply -k monitoring/k8s
7.4 Vérifier l'état des pods et des ServiceMonitors
Bash

kubectl get pods -n monitoring
kubectl get servicemonitors -n monitoring
kubectl get probes -n monitoring
8. Requêtes de test PromQL et LogQL (Démonstration)
8.1 Vérification des cibles dans Prometheus (kubectl port-forward -n monitoring svc/prometheus-kube-prometheus-prometheus 9090:9090)
promql

up{namespace=~"fintech|ml|data|monitoring"}
promql

sum by (application) (rate(http_server_requests_seconds_count{namespace="fintech"}[1m]))
8.2 Recherche de bout en bout par correlationId dans Grafana Explore (Datasource Loki)
Suivre une même transaction à travers api-gateway, transaction-service, risk-service, ml-service et audit-service :

logql

{namespace=~"fintech|ml"} | json | correlationId="corr-demo-001"
Afficher uniquement les erreurs récentes des microservices métier :

logql

{namespace="fintech", level="ERROR"} | json
Vérifier les 4 labels indexés par Loki (sans correlationId) :

Bash

kubectl port-forward -n monitoring svc/loki 3100:3100
curl -s http://localhost:3100/loki/api/v1/labels
Résultat attendu : ["app", "level", "namespace", "pod"].

9. Sécurité (§8.7)
Le mot de passe administrateur Grafana n'est jamais écrit en clair dans Git : 
kube-prometheus-stack-values.yaml
 référence le secret Kubernetes grafana-admin-credentials (géré par SealedSecret, décision D22).
Les pods loki et alloy s'exécutent en mode non-privilégié (runAsNonRoot: true, UID 10001, readOnlyRootFilesystem: true, capabilities.drop: [ALL]).
Seul Grafana a vocation à être exposé via Traefik (https://grafana.fintech.local en TLS) ; Prometheus, Alertmanager et Loki restent internes au cluster (ClusterIP).