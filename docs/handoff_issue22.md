# Handoff P2 — issue #22

État au 2 novembre 2026. **Provisoire : sélection définitive après validation statistique (§4.8-4.9) et revue des limites du protocole.** Aucun modèle n'est promu automatiquement.

## Protocole et paramètres

- Source : partie `development` (70 % chronologiques) de `data/raw/fraudTrain.csv` uniquement. La partie Optuna initiale (20 % de `development`) est disjointe de la partie benchmark (80 % restants). Seules les dates de toute la source ont été lues pour délimiter les zones ; labels et features de calibration exclus.
- Recherche : 30 essais par modèle, RandomSampler seed 42, validation interne chronologique, sous-processus limité à 300 s par essai et 3 h par étude. Paramètres retenus selon la marge de 0,03 de PR-AUC puis la simplicité.
- Paramètres figés : `configs/best_params.json`, SHA-256 `f0ced06a7e2f863406aa55f891b10f337f1163cf6d6c0f08e584c18a3f6bfd41`. Modèles : `logreg`, `rf`, `xgb`, `nystroem_svc`, `mlp`. La provenance Optuna du fichier indique le commit `ee78441f87349ef56d6a3b3d388042ea395ef4c4`.
- Benchmark : 10 répétitions de 5 plis `StratifiedKFold`, plis partagés entre modèles, seeds 0 à 9. Dans chaque pli, preprocessing ajusté sur le train naturel seulement, puis sous-échantillonnage du train transformé à 1 fraude pour 10 transactions légitimes ; `beta` est calculé par pli. Validation à distribution naturelle. Seuil F1 déterminé dans une validation interne au train externe. La PR-AUC est la métrique confirmatoire.
- Commit enregistré dans les 250 runs et résultats : `ee78441f87349ef56d6a3b3d388042ea395ef4c4`. Les runs représentent ce code au moment du calcul ; vérifier les changements ultérieurs avant toute reproduction.

## Résultats du benchmark

Les écarts-types ci-dessous portent sur les **10 moyennes de répétition**, et non sur les 50 plis pris comme unités indépendantes.

| Modèle | Plis | Répétitions | PR-AUC moyenne | Écart-type entre répétitions | Run parent MLflow |
|---|---:|---:|---:|---:|---|
| `xgb` | 50 | 10 | 0,893470 | 0,003058 | `6d325d89b20f47dfb98a74cefeb8dc80` |
| `rf` | 50 | 10 | 0,867540 | 0,002043 | `a0f53bfa7b8a4b89b076963c6b9a8d8c` |
| `mlp` | 50 | 10 | 0,691750 | 0,025794 | `bc6fcf00db564338ae94d94f61f5a8f4` |
| `logreg` | 50 | 10 | 0,369704 | 0,000969 | `5714e2d514224b04b902b0fd1d386f9a` |
| `nystroem_svc` | 50 | 10 | 0,359026 | 0,005106 | `1691cb64bb91468887db25d9b483a6f3` |

Les 250 enfants et cinq parents de ces runs sont `FINISHED`, et les 250 PR-AUC correspondent au Parquet. L'expérience `benchmark_p2` contient aussi des anciens essais ou reprises : six runs distincts étaient encore `RUNNING` lors de l'audit du 2 novembre. Ne pas les confondre avec les 250 runs retenus.

## Artefacts et environnement

- Fichiers locaux hors dépôt : `C:\Users\Lenovo\AppData\Local\fintech-benchmark\full-p2-20261026-authorized\folds.parquet`, `repeat_means.parquet`, `fold_scores.csv`, `repeat_means.csv`, `parents.json`. Les CSV et Parquet de résultats ne doivent pas entrer dans Git.
- MLflow : expérience `benchmark_p2` (ID 5) sur le serveur accessible depuis cette machine par `localhost:5000`. Omar doit avoir accès au serveur ou à son port exposé et aux artefacts de l'instance pour consulter les runs ; `localhost` sur sa machine ne désigne pas automatiquement ce serveur.
- Versions locales vérifiées le 2 novembre : Python 3.11.17, scikit-learn 1.9.1, XGBoost 3.2.0, MLflow client 3.17.2. Le CI utilise Python 3.12 ; les versions exactes du conteneur serveur doivent être relevées séparément si nécessaires.
- Analyse statistique locale distincte : `results/stats/results.json` et `results/stats/stats_report.md`. Friedman sur les 10 répétitions : χ² = 40, p = 4,3284e-08 ; XGBoost contre RF : différence moyenne de PR-AUC +0,02593, p de Holm = 0,01953125. Revoir les hypothèses et le caractère corrélé des répétitions avant une sélection définitive.

## Limites et suites

- La validation du benchmark est stratifiée, non chronologique ou groupée par carte. `cc_num` est exclu des features, mais les mêmes cartes apparaissent dans train et validation : au premier pli contrôlé, les 145 228 lignes de validation, dont 712 fraudes, avaient une carte présente dans le train. Cela peut rendre la généralisation à de nouvelles cartes ou à des périodes futures moins certaine ; ce constat seul ne prouve pas une fuite de label.
- Le diagnostic antérieur `03b` sur l'ensemble de `development`, avec un XGBoost fixe différent du benchmark, donnait une PR-AUC moyenne de 0,828803 en plis aléatoires et 0,823824 en plis groupés par carte. Le différentiel de 0,004979 ne satisfaisait pas le seuil pré-déclaré de 0,02 pour changer le schéma. Les résultats `03b` et ceux du benchmark ne sont pas directement comparables car les modèles, hyperparamètres et sous-ensembles diffèrent.
- La zone finale réservée n'a pas été consultée pour cette issue. Aucune métrique de test final ne figure ici.
- Avant handoff P3 : finaliser la revue statistique, décider des limites acceptables de validation par carte/temps, valider les artefacts et corriger le lint du script local de latence. Aucun résultat brut volumineux ni secret ne doit être committé.
