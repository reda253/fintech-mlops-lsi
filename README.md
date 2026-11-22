# Plateforme FinTech MLOps haute disponibilité

Real-time card-fraud risk platform: every transaction is scored by a calibrated ML model with conformal prediction and is **approved**, **blocked**, or sent to **human review** when the model is uncertain. Built with Spring Boot microservices, FastAPI, MLflow, React, Kubernetes (kind), Argo CD, Prometheus/Grafana.

> Full report — sections are filled by each member before J8 (03/01/2027). Architecture reference: [`docs/specs/Architecture_Plateforme_FinTech_MLOps_1.pdf`](docs/specs/Architecture_Plateforme_FinTech_MLOps_1.pdf).

## Table of contents
1. [Architecture microservices](#1-architecture-microservices) — P1
2. [Machine learning, statistical validation, uncertainty](#2-machine-learning) — P2
3. [MLOps and model serving](#3-mlops-and-model-serving) — P3
4. [Docker, Kubernetes, CI/CD, experiments](#4-devops) — P4
5. [Frontend and observability](#5-frontend-and-observability) — P5
6. [How to run](#6-how-to-run)
7. [Limits and future work](#7-limits-and-future-work)
8. [Limites éthiques et audit d’équité](#limites-éthiques-et-audit-déquité)

## 1. Architecture microservices
_TODO (P1)_

## 2. Machine learning
_TODO (P2)_

## 3. MLOps and model serving
_TODO (P3)_

## 4. DevOps
_TODO (P4)_

## 5. Frontend and observability
_TODO (P5)_

## 6. How to run
_TODO_ — prerequisites: JDK 21, Docker, kind, kubectl.

## 7. Limits and future work
_TODO_

## Limites éthiques et audit d'équité

Le genre et l'âge sont conservés conformément à D18. L'audit compare `F` et `M`
et les âges révolus à la transaction : 0–25, 26–35, 36–45, 46–55, 56–65,
66–120 ans. Les groupes sont figés ; la tranche est stockée sous `age_group`.

Les quatre taux opérationnels sont les fraudes bloquées automatiquement,
les fraudes interceptées (blocage + revue), les légitimes bloqués
automatiquement et le taux de revue. `[1]` bloque, `[0]` approuve ; `[]` et
`[0,1]` vont en revue. Effectifs, fraudes et légitimes sont affichés par groupe.
Une division indéfinie est rendue par `N/A (undefined)` et `null` dans le JSON.

Les IC percentile 95 % utilisent 10 000 rééchantillonnages, seed 42, avec les
mêmes tirages pour les groupes et leurs différences. L'implémentation
multinomiale sur les catégories conjointes reproduit exactement le bootstrap
iid des transactions pour ces quatre taux. Les IC supposent des transactions
indépendantes malgré les transactions répétées d'une même carte : cette
dépendance et la dérive temporelle ne sont pas corrigées.

D48 sur le jeu final est une seconde mesure post hoc, non indépendante. Les
comparaisons sont descriptives, sans verdict binaire d'équité ni retouche
ultérieure du modèle. XGBoost reste provisoire, sans promotion automatique.

<!-- BEGIN FAIRNESS RESULTS -->
**Résultats réels en attente.** Aucun chiffre d'équité synthétique ne doit être
présenté comme une mesure finale. Les artefacts réels doivent être fournis et vérifiés.

Run MLflow : **à compléter**. D48 est une seconde mesure post hoc non indépendante.

| Attribut | Groupe | N | Fraudes | Légitimes | Fraudes bloquées [IC 95 %] | Fraudes interceptées [IC 95 %] | Légitimes bloqués [IC 95 %] | Revue [IC 95 %] |
|---|---|---:|---:|---:|---|---|---|---|
| Genre | F | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter |
| Genre | M | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter |
| Âge | 0–25 | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter |
| Âge | 26–35 | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter |
| Âge | 36–45 | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter |
| Âge | 46–55 | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter |
| Âge | 56–65 | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter |
| Âge | 66–120 | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter | À compléter |

| Comparaison | Métrique | Écart absolu | IC 95 % | Réplications valides |
|---|---|---|---|---|
| Groupes à compléter | À compléter | À compléter | À compléter | À compléter |

Signaler les valeurs indéfinies et petits effectifs ; ne tirer aucun verdict binaire.
<!-- END FAIRNESS RESULTS -->

`evaluate_final_candidate.py` reste le seul lecteur et exécuteur de
l'inférence finale. Il sauvegarde `predictions.csv` avec exactement `label`,
`fraud_probability`, `include_0`, `include_1`, `gender`, `age_group`.
`ml.fairness.audit` consomme directement ce fichier et les artefacts voisins
vérifiés, sans nouvelle inférence ni réutilisation de l'autorisation consommée.
Voir [le protocole](docs/fairness_protocol.md).

```text
python -m ml.fairness.audit --from-predictions <evaluation-dir>/predictions.csv --output-dir <new-external-dir> --model-metadata <candidate-provenance.json> --journal <external-journal.jsonl> --code-revision <current-full-git-hash>
```

La provenance candidat doit fournir `model_sha256`, `model_uri` et
`model_version`. Le run d'évaluation est repris de `mlflow_status.json` et doit
être publié pour une mesure réelle. `--code-revision` est fourni explicitement
pour éviter toute commande Git automatique ; il doit correspondre au code
exécuté. Le manifeste distingue cette révision de celle de l'évaluation.

L'Option B est intégrée par la PR #117 (`bc30b93`) :
`evaluate_final_candidate.py` → artefacts vérifiés #117 → `audit.py` →
`step_evaluate`. Le pipeline consomme le dossier d'évaluation original ;
les sorties fairness restent complémentaires et dans un dossier distinct.
L'audit réutilise `load_verified_final_evaluation` et les empreintes approuvées
centralisées, avec alpha attendu 0.02. Son `--journal` est lu sans modification :
toute entrée D47 d'évaluation est refusée ; un achèvement D48 cohérent est requis.
`manifest_d48.json` ne remplace jamais `artifact_manifest.json` ni l'historique.

L'alignement inclut désormais #120 (`main` : `c5d9881`). Les préconditions
locales restent dans `ml/scripts/d48_preflight.py`. Le module
`ml.scripts.registry_preflight` contrôle uniquement le Registry, avec
`--model-metadata`, `--version` ou `--alias`, et `--tracking-uri` : il ne relit ni la
source finale ni le journal, ne réserve rien et ne prédit rien. `audit.py`
consomme les prédictions et vérifie le journal de complétion sans réutiliser
l'autorisation. Les paramètres Registry sont dans une provenance distincte
du JSON d'autorisation officiel à six champs ; le tag de protocole D44 du
modèle enregistré ne remplace pas le protocole D48 approuvé.
