# Monitoring Docker — Prometheus & Grafana

**Projet :** FinTech MLOps LSI  
**Issue GitHub :** #47 — Prometheus + Grafana in Docker Compose  
**Responsable :** P5 — Frontend & Observability  
**Environnement :** Docker Compose — Développement local

## 1. Objectif

Mettre en place une solution de monitoring permettant de collecter, consulter et visualiser les métriques techniques du service de prédiction de fraude (`ml-service`).

La solution repose sur deux composants :

- **Prometheus :** collecte et stockage des métriques.
- **Grafana :** visualisation des métriques à travers des dashboards.

Cette intégration constitue la base de l'observabilité de la plateforme FinTech MLOps.

## 2. Architecture

Le monitoring utilise l'architecture suivante :

```text
                    Docker Compose
                          |
          +---------------+---------------+
          |               |               |
     ML Service       Prometheus        Grafana
      Port 8000        Port 9090        Port 3000
          |               |               |
       /metrics ---------->               |
                          |<--------------|
                          |
                    Stockage métriques
```

Le fonctionnement est le suivant :

1. Le service ML expose ses métriques sur `/metrics`.
2. Prometheus collecte ces métriques toutes les 15 secondes.
3. Grafana interroge Prometheus pour afficher les indicateurs.
4. Les données sont conservées dans des volumes Docker.

## 3. Technologies

| Composant | Version | Port |
|---|---|---|
| Prometheus | 3.5.0 | 9090 |
| Grafana | 12.1.1 | 3000 |
| ML Service | FastAPI | 8000 |
| Orchestration locale | Docker Compose | — |

## 4. Organisation des fichiers

```text
fintech-mlops-lsi/
├── docker-compose.yml
├── monitoring/
│   ├── prometheus.yml
│   └── grafana/
│       ├── dashboards/
│       │   └── fintech-monitoring-overview.json
│       └── provisioning/
│           ├── dashboards/
│           │   └── dashboards.yml
│           └── datasources/
│               └── prometheus.yml
└── docs/
    └── monitoring-docker.md
```

Les configurations et le dashboard sont versionnés dans Git.

## 5. Configuration de Prometheus

Fichier : `monitoring/prometheus.yml`

Paramètres :

- `scrape_interval: 15s`
- `evaluation_interval: 15s`
- Job `prometheus` : `localhost:9090`
- Job `ml-service` : `ml-service:8000`
- Endpoint du service ML : `/metrics`

Prometheus utilise les noms des services Docker pour communiquer avec les conteneurs.

## 6. Configuration de Grafana

La source de données Prometheus est configurée automatiquement dans :

`monitoring/grafana/provisioning/datasources/prometheus.yml`

Paramètres principaux :

- Nom : `Prometheus`
- UID : `prometheus`
- Type : `prometheus`
- URL : `http://prometheus:9090`
- Source de données par défaut : activée
- Intervalle minimal configuré : `15s`

Les dashboards sont chargés automatiquement grâce au fichier :

`monitoring/grafana/provisioning/dashboards/dashboards.yml`

Ils sont regroupés dans le dossier Grafana **FinTech MLOps**.

## 7. Démarrage

Depuis la racine du projet :

```bash
docker compose config --quiet
docker compose up -d
docker compose ps
```

La première commande vérifie la configuration.

La deuxième démarre les services définis dans Docker Compose. Certains services peuvent nécessiter leurs dépendances et variables d'environnement.

La troisième affiche l'état des conteneurs.

### Accès aux interfaces

| Service | Adresse |
|---|---|
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 |
| Métriques ML | http://localhost:8000/metrics |
| Santé ML | http://localhost:8000/health/ready |

Le port `8000` correspond au service ML exposé localement.

## 8. Dashboard de démonstration

Un premier dashboard est disponible dans Grafana :

**FinTech MLOps - Monitoring Overview**

Il contient dix panneaux :

1. ML Service — disponibilité
2. Request Rate — débit des requêtes
3. HTTP Latency p95 — latence HTTP
4. HTTP Error Rate — taux d'erreurs HTTP
5. ML Service — Memory Usage
6. HTTP Request Rate
7. HTTP Response Latency (p95)
8. HTTP Error Rate
9. ML Inference Latency (p95)
10. ML Inference Latency — Average

Ce dashboard constitue une démonstration fonctionnelle de l'intégration Prometheus–Grafana.

La réalisation de l'ensemble des neuf dashboards, des alertes Discord et des runbooks relève d'une tâche GitHub distincte.

## 9. Métriques surveillées

Les métriques actuellement disponibles comprennent notamment :

| Métrique | Description |
|---|---|
| `up` | Disponibilité de la cible Prometheus |
| `process_resident_memory_bytes` | Mémoire utilisée par le processus |
| `http_requests_total` | Nombre de requêtes HTTP |
| `http_request_duration_seconds` | Durée des requêtes HTTP |
| `ml_inference_duration_seconds` | Durée des inférences ML |
| `ml_predictions_total` | Nombre de prédictions |
| `ml_fraud_probability` | Probabilité de fraude |
| `ml_uncertainty` | Incertitude des prédictions |
| `ml_input_validation_errors_total` | Erreurs de validation des entrées |
| `ml_model_info` | Informations sur le modèle |

Les métriques sont exposées par le service ML. Leur présence ne signifie pas nécessairement que toutes les séries contiennent déjà des observations.

## 10. Tests réalisés

### Test 1 — Validation Docker Compose

Commande :

```bash
docker compose config --quiet
```

**Résultat :** aucune erreur de configuration.

### Test 2 — État des conteneurs

Commande :

```bash
docker compose ps
```

**Résultat observé :**

- `fintech-grafana` : Up
- `fintech-prometheus` : Up
- `fintech-ml-service` : Up (healthy)

### Test 3 — Endpoint des métriques

Commande Windows CMD :

```cmd
curl -s -o NUL -w "HTTP %{http_code}" http://localhost:8000/metrics
```

**Résultat :** `HTTP 200`.

### Test 4 — Santé du modèle ML

Commande :

```bash
curl -i http://localhost:8000/health/ready
```

**Résultat :** `HTTP 200` et `{"status":"ready"}`.

### Test 5 — Disponibilité des cibles Prometheus

Requête PromQL :

```promql
up
```

**Résultat observé :**

- `job="ml-service"` : `1`
- `job="prometheus"` : `1`

Les deux cibles sont accessibles.

### Test 6 — Collecte des prédictions ML

Requête PromQL :

```promql
ml_inference_duration_seconds_count{job="ml-service"}
```

**Résultat :** compteur passé de `11` à `12` après une prédiction de test.

Cela confirme que Prometheus récupère les nouvelles observations.

### Test 7 — Latence des inférences ML

Requête PromQL :

```promql
1000 * histogram_quantile(
  0.95,
  sum by (le) (
    rate(ml_inference_duration_seconds_bucket{job="ml-service"}[30m])
  )
)
```

**Résultat observé :** environ `0,95 ms`.

Ce résultat correspond à une estimation du 95e percentile à partir des buckets d'histogramme. Il ne représente pas nécessairement la latence réelle d'une charge de production.

### Test 8 — Visualisation Grafana

Le dashboard a été affiché avec succès dans Grafana.

Les graphiques de mémoire, trafic HTTP, latence HTTP, erreurs HTTP et inférences ML ont été visualisés.

## 11. Persistance des données

Deux volumes Docker sont configurés :

- `prometheus_data` : conservation des données Prometheus.
- `grafana_data` : conservation des données Grafana.

Les fichiers de configuration et dashboards sont montés en lecture seule depuis le dépôt.

Attention : la suppression des volumes Docker entraîne la perte des données persistantes correspondantes.

## 12. Sécurité

La configuration actuelle est destinée au développement local.

Points à respecter :

- Définir `GRAFANA_ADMIN_PASSWORD` avec un mot de passe robuste.
- Ne jamais versionner de mots de passe ou secrets dans Git.
- Ne pas exposer directement les ports de monitoring sur un réseau public.
- Désactiver les inscriptions publiques non autorisées.
- Adapter l'authentification et les contrôles d'accès avant tout déploiement partagé.

Le compte administrateur Grafana est configuré avec l'identifiant `admin`. En l'absence de variable `GRAFANA_ADMIN_PASSWORD`, le fichier Docker Compose prévoit actuellement `admin` comme valeur de secours. Cette valeur ne doit pas être utilisée en production.

## 13. Dépannage

### Prometheus ne récupère pas les métriques

Vérifier :

```bash
docker compose ps
docker compose logs prometheus
```

Puis contrôler la cible `ml-service:8000` dans Prometheus.

### Grafana ne trouve pas Prometheus

Vérifier :

- Que Prometheus est démarré.
- Que la source de données utilise `http://prometheus:9090`.
- Que les services communiquent sur le réseau Docker Compose.

### Un graphique affiche « No data »

Vérifier :

- La métrique dans Prometheus.
- La période sélectionnée dans Grafana.
- La présence d'observations récentes.
- Les labels utilisés dans la requête PromQL.

Certaines métriques calculées avec `rate()` nécessitent plusieurs échantillons et une activité récente.

## 14. Limites et évolutions

Cette intégration couvre actuellement le monitoring local avec Docker Compose et les métriques disponibles du service ML.

Les travaux suivants sont traités dans d'autres tâches :

- Création des neuf dashboards Grafana.
- Configuration des alertes Discord.
- Rédaction des runbooks.
- Monitoring Kubernetes avec kube-prometheus-stack.
- Tests complets de déclenchement des alertes.

## 15. Conclusion

Prometheus et Grafana sont intégrés à l'environnement Docker Compose du projet FinTech MLOps.

Les tests locaux confirment que les conteneurs fonctionnent, que Prometheus collecte les métriques du service ML et que Grafana permet de les visualiser.

Cette intégration fournit une base fonctionnelle pour les travaux d'observabilité à venir.