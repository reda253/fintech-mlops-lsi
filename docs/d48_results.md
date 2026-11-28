# Résultats D48 et audit d’équité

**Seconde mesure post hoc, non indépendante : le test final a été lu deux fois, les 10 et 22 novembre. Modèle provisoire, aucune sélection, aucun réglage ni promotion automatique.**

Les sources ci-dessous sont les fichiers de l’archive privée `d48-output-20261122.zip`. Les prédictions individuelles restent privées.

## Résultats globaux

Estimations et effectifs : `results/final_metrics.json` ; IC percentile 95 % : `results/bootstrap_intervals.json` (10 000 tirages, seed 42).

| Mesure | Estimation [IC 95 %] |
|---|---|
| PR-AUC | 0,875502 [0,863777 ; 0,886656] |
| ROC-AUC | 0,997504 [0,996873 ; 0,998038] |
| Couverture légitimes | 97,96 % [97,92 % ; 97,99 %] |
| Couverture fraudes | 96,13 % [95,30 % ; 96,92 %] |
| Fraudes interceptées | 97,20 % [96,48 % ; 97,87 %] |
| Revue | 0,69 % [0,67 % ; 0,71 %] |
| Erreur automatique | 1,37 % [1,34 % ; 1,40 %] |

555 719 transactions : 2 145 fraudes et 553 574 légitimes. Alpha figé : 0,02. Source : `results/final_metrics.json`.

## Décisions recomptées depuis les prédictions

Source : recomptage sur `results/predictions.csv` sauvegardé et vérifié par `results/artifact_manifest.json`. `[1]` bloque, `[0]` approuve, `[]` et `[0,1]` vont en revue. Aucun identifiant ni prédiction individuelle n’est reproduit ici.

| Classe réelle | Bloquées automatiquement | Approuvées automatiquement | Revue |
|---|---:|---:|---:|
| Légitimes | 7 506 | 542 254 | 3 814 |
| Fraudes | 2 062 | 60 | 23 |

Le ratio 7 506 / 2 062 est **3,64 légitimes bloqués pour une fraude bloquée**, soit environ 3,6 pour 1. Ce n’est pas un taux conditionnel : les effectifs des classes diffèrent.

## Équité descriptive

Sources des tableaux : `fairness_audit/fairness_metrics.json` et `fairness_audit/manifest_d48.json`. IC percentile 95 % issus du bootstrap multinomial sur les cellules conjointes (10 000 tirages, seed 42). Les taux suivent les décisions conformes. Les **60 écarts d’âge sont exploratoires et non corrigés pour comparaisons multiples** ; les quatre écarts de genre ne sont pas corrigés non plus. Les IC ponctuels ne constituent pas un test global d’équité.

<!-- BEGIN FAIRNESS RESULTS -->
**D48 — seconde mesure post hoc, non indépendante.** Run MLflow de publication : `e0adc3e7bee847648199f57a5b15de41`. Alpha = 0,02 ; bootstrap transactionnel : 10 000 tirages, seed 42, IC percentile 95 %.

| Attribut | Groupe | N | Fraudes | Légitimes | Fraudes bloquées [IC 95 %] | Fraudes interceptées [IC 95 %] | Légitimes bloqués [IC 95 %] | Revue [IC 95 %] |
|---|---|---:|---:|---:|---|---|---|---|
| Genre | F | 304 886 | 1164 | 303 722 | 94.42 % [93.04 % ; 95.71 %] | 95.96 % [94.77 % ; 97.08 %] | 1.60 % [1.55 % ; 1.64 %] | 0.84 % [0.80 % ; 0.87 %] |
| Genre | M | 250 833 | 981 | 249 852 | 98.17 % [97.28 % ; 98.95 %] | 98.67 % [97.91 % ; 99.32 %] | 1.06 % [1.02 % ; 1.10 %] | 0.51 % [0.49 % ; 0.54 %] |
| Âge | 0-25 | 54 029 | 220 | 53 809 | 98.64 % [96.86 % ; 100.00 %] | 98.64 % [96.86 % ; 100.00 %] | 1.78 % [1.67 % ; 1.89 %] | 0.79 % [0.71 % ; 0.86 %] |
| Âge | 26-35 | 122 790 | 410 | 122 380 | 94.39 % [92.01 % ; 96.53 %] | 95.12 % [92.88 % ; 97.12 %] | 1.46 % [1.40 % ; 1.53 %] | 0.70 % [0.66 % ; 0.75 %] |
| Âge | 36-45 | 116 926 | 364 | 116 562 | 96.70 % [94.72 % ; 98.37 %] | 97.80 % [96.12 % ; 99.17 %] | 1.34 % [1.28 % ; 1.41 %] | 0.69 % [0.65 % ; 0.74 %] |
| Âge | 46-55 | 109 372 | 424 | 108 948 | 95.28 % [93.23 % ; 97.22 %] | 96.93 % [95.22 % ; 98.47 %] | 1.47 % [1.40 % ; 1.55 %] | 0.75 % [0.70 % ; 0.80 %] |
| Âge | 56-65 | 69 615 | 341 | 69 274 | 95.60 % [93.31 % ; 97.67 %] | 97.07 % [95.15 % ; 98.75 %] | 1.00 % [0.93 % ; 1.08 %] | 0.57 % [0.52 % ; 0.63 %] |
| Âge | 66-120 | 82 987 | 386 | 82 601 | 97.41 % [95.70 % ; 98.90 %] | 98.45 % [97.11 % ; 99.51 %] | 1.08 % [1.01 % ; 1.15 %] | 0.63 % [0.58 % ; 0.68 %] |

Les écarts ci-dessous sont absolus, en points de pourcentage ; IC percentile 95 %, sans correction des comparaisons multiples.

| Attribut | Groupes | Métrique | Écart absolu [IC 95 %] | Réplications valides |
|---|---|---|---|---:|
| Genre | F / M | Fraudes bloquées | 3.75 pp [2.19 pp ; 5.32 pp] | 10000 / 10000 |
| Genre | F / M | Fraudes interceptées | 2.71 pp [1.37 pp ; 4.08 pp] | 10000 / 10000 |
| Genre | F / M | Légitimes bloqués | 0.53 pp [0.47 pp ; 0.59 pp] | 10000 / 10000 |
| Genre | F / M | Revue | 0.32 pp [0.28 pp ; 0.36 pp] | 10000 / 10000 |
| Âge | 0-25 / 26-35 | Fraudes bloquées | 4.25 pp [1.54 pp ; 6.98 pp] | 10000 / 10000 |
| Âge | 0-25 / 26-35 | Fraudes interceptées | 3.51 pp [0.89 pp ; 6.14 pp] | 10000 / 10000 |
| Âge | 0-25 / 26-35 | Légitimes bloqués | 0.31 pp [0.18 pp ; 0.44 pp] | 10000 / 10000 |
| Âge | 0-25 / 26-35 | Revue | 0.08 pp [0.01 pp ; 0.17 pp] | 10000 / 10000 |
| Âge | 0-25 / 36-45 | Fraudes bloquées | 1.93 pp [0.15 pp ; 4.34 pp] | 10000 / 10000 |
| Âge | 0-25 / 36-45 | Fraudes interceptées | 0.83 pp [0.05 pp ; 2.99 pp] | 10000 / 10000 |
| Âge | 0-25 / 36-45 | Légitimes bloqués | 0.43 pp [0.31 pp ; 0.57 pp] | 10000 / 10000 |
| Âge | 0-25 / 36-45 | Revue | 0.10 pp [0.01 pp ; 0.18 pp] | 10000 / 10000 |
| Âge | 0-25 / 46-55 | Fraudes bloquées | 3.35 pp [0.89 pp ; 5.84 pp] | 10000 / 10000 |
| Âge | 0-25 / 46-55 | Fraudes interceptées | 1.70 pp [0.11 pp ; 3.88 pp] | 10000 / 10000 |
| Âge | 0-25 / 46-55 | Légitimes bloqués | 0.30 pp [0.17 pp ; 0.44 pp] | 10000 / 10000 |
| Âge | 0-25 / 46-55 | Revue | 0.04 pp [0.00 pp ; 0.13 pp] | 10000 / 10000 |
| Âge | 0-25 / 56-65 | Fraudes bloquées | 3.04 pp [0.41 pp ; 5.69 pp] | 10000 / 10000 |
| Âge | 0-25 / 56-65 | Fraudes interceptées | 1.57 pp [0.10 pp ; 3.94 pp] | 10000 / 10000 |
| Âge | 0-25 / 56-65 | Légitimes bloqués | 0.77 pp [0.64 pp ; 0.91 pp] | 10000 / 10000 |
| Âge | 0-25 / 56-65 | Revue | 0.22 pp [0.12 pp ; 0.31 pp] | 10000 / 10000 |
| Âge | 0-25 / 66-120 | Fraudes bloquées | 1.23 pp [0.07 pp ; 3.41 pp] | 10000 / 10000 |
| Âge | 0-25 / 66-120 | Fraudes interceptées | 0.19 pp [0.04 pp ; 2.26 pp] | 10000 / 10000 |
| Âge | 0-25 / 66-120 | Légitimes bloqués | 0.70 pp [0.57 pp ; 0.83 pp] | 10000 / 10000 |
| Âge | 0-25 / 66-120 | Revue | 0.16 pp [0.07 pp ; 0.25 pp] | 10000 / 10000 |
| Âge | 26-35 / 36-45 | Fraudes bloquées | 2.31 pp [0.15 pp ; 5.22 pp] | 10000 / 10000 |
| Âge | 26-35 / 36-45 | Fraudes interceptées | 2.68 pp [0.34 pp ; 5.33 pp] | 10000 / 10000 |
| Âge | 26-35 / 36-45 | Légitimes bloqués | 0.12 pp [0.03 pp ; 0.22 pp] | 10000 / 10000 |
| Âge | 26-35 / 36-45 | Revue | 0.01 pp [0.00 pp ; 0.08 pp] | 10000 / 10000 |
| Âge | 26-35 / 46-55 | Fraudes bloquées | 0.89 pp [0.06 pp ; 3.96 pp] | 10000 / 10000 |
| Âge | 26-35 / 46-55 | Fraudes interceptées | 1.81 pp [0.09 pp ; 4.57 pp] | 10000 / 10000 |
| Âge | 26-35 / 46-55 | Légitimes bloqués | 0.01 pp [0.00 pp ; 0.11 pp] | 10000 / 10000 |
| Âge | 26-35 / 46-55 | Revue | 0.04 pp [0.00 pp ; 0.11 pp] | 10000 / 10000 |
| Âge | 26-35 / 56-65 | Fraudes bloquées | 1.21 pp [0.07 pp ; 4.33 pp] | 10000 / 10000 |
| Âge | 26-35 / 56-65 | Fraudes interceptées | 1.95 pp [0.12 pp ; 4.77 pp] | 10000 / 10000 |
| Âge | 26-35 / 56-65 | Légitimes bloqués | 0.46 pp [0.36 pp ; 0.56 pp] | 10000 / 10000 |
| Âge | 26-35 / 56-65 | Revue | 0.13 pp [0.06 pp ; 0.21 pp] | 10000 / 10000 |
| Âge | 26-35 / 66-120 | Fraudes bloquées | 3.02 pp [0.40 pp ; 5.82 pp] | 10000 / 10000 |
| Âge | 26-35 / 66-120 | Fraudes interceptées | 3.32 pp [0.92 pp ; 5.85 pp] | 10000 / 10000 |
| Âge | 26-35 / 66-120 | Légitimes bloqués | 0.38 pp [0.29 pp ; 0.48 pp] | 10000 / 10000 |
| Âge | 26-35 / 66-120 | Revue | 0.07 pp [0.01 pp ; 0.14 pp] | 10000 / 10000 |
| Âge | 36-45 / 46-55 | Fraudes bloquées | 1.42 pp [0.07 pp ; 4.09 pp] | 10000 / 10000 |
| Âge | 36-45 / 46-55 | Fraudes interceptées | 0.87 pp [0.04 pp ; 3.08 pp] | 10000 / 10000 |
| Âge | 36-45 / 46-55 | Légitimes bloqués | 0.13 pp [0.04 pp ; 0.23 pp] | 10000 / 10000 |
| Âge | 36-45 / 46-55 | Revue | 0.06 pp [0.00 pp ; 0.13 pp] | 10000 / 10000 |
| Âge | 36-45 / 56-65 | Fraudes bloquées | 1.10 pp [0.06 pp ; 3.96 pp] | 10000 / 10000 |
| Âge | 36-45 / 56-65 | Fraudes interceptées | 0.73 pp [0.04 pp ; 3.12 pp] | 10000 / 10000 |
| Âge | 36-45 / 56-65 | Légitimes bloqués | 0.34 pp [0.24 pp ; 0.43 pp] | 10000 / 10000 |
| Âge | 36-45 / 56-65 | Revue | 0.12 pp [0.05 pp ; 0.19 pp] | 10000 / 10000 |
| Âge | 36-45 / 66-120 | Fraudes bloquées | 0.71 pp [0.05 pp ; 3.22 pp] | 10000 / 10000 |
| Âge | 36-45 / 66-120 | Fraudes interceptées | 0.64 pp [0.04 pp ; 2.67 pp] | 10000 / 10000 |
| Âge | 36-45 / 66-120 | Légitimes bloqués | 0.26 pp [0.16 pp ; 0.36 pp] | 10000 / 10000 |
| Âge | 36-45 / 66-120 | Revue | 0.06 pp [0.00 pp ; 0.13 pp] | 10000 / 10000 |
| Âge | 46-55 / 56-65 | Fraudes bloquées | 0.32 pp [0.05 pp ; 3.40 pp] | 10000 / 10000 |
| Âge | 46-55 / 56-65 | Fraudes interceptées | 0.13 pp [0.04 pp ; 2.76 pp] | 10000 / 10000 |
| Âge | 46-55 / 56-65 | Légitimes bloqués | 0.47 pp [0.37 pp ; 0.57 pp] | 10000 / 10000 |
| Âge | 46-55 / 56-65 | Revue | 0.18 pp [0.10 pp ; 0.25 pp] | 10000 / 10000 |
| Âge | 46-55 / 66-120 | Fraudes bloquées | 2.13 pp [0.15 pp ; 4.69 pp] | 10000 / 10000 |
| Âge | 46-55 / 66-120 | Fraudes interceptées | 1.51 pp [0.09 pp ; 3.55 pp] | 10000 / 10000 |
| Âge | 46-55 / 66-120 | Légitimes bloqués | 0.39 pp [0.29 pp ; 0.49 pp] | 10000 / 10000 |
| Âge | 46-55 / 66-120 | Revue | 0.12 pp [0.04 pp ; 0.19 pp] | 10000 / 10000 |
| Âge | 56-65 / 66-120 | Fraudes bloquées | 1.81 pp [0.09 pp ; 4.55 pp] | 10000 / 10000 |
| Âge | 56-65 / 66-120 | Fraudes interceptées | 1.38 pp [0.07 pp ; 3.64 pp] | 10000 / 10000 |
| Âge | 56-65 / 66-120 | Légitimes bloqués | 0.08 pp [0.00 pp ; 0.18 pp] | 10000 / 10000 |
| Âge | 56-65 / 66-120 | Revue | 0.06 pp [0.00 pp ; 0.14 pp] | 10000 / 10000 |

Les effectifs de fraudes varient de 220 à 424 selon la tranche d’âge. Une borne d’IC atteint 100 % pour le blocage des 0–25 ans ; un faible effectif ou un IC large ne démontre pas l’absence de disparité. Aucun seuil numérique minimal ni verdict binaire d’équité ne sont fixés. Les métriques indéfinies seraient affichées `N/A (undefined)` ; les valeurs de ce tableau sont définies. Les IC supposent des transactions indépendantes malgré les cartes répétées. Aucune promotion automatique ni retouche du modèle.
<!-- END FAIRNESS RESULTS -->

Les estimations ne prouvent ni les causes des écarts ni une absence de discrimination. `gender` et `age` sont des variables utilisées par le modèle ; ces associations ne permettent pas d’isoler leur rôle causal. Les IC supposent des transactions indépendantes alors qu’une carte peut être utilisée plusieurs fois. Les effectifs et IC doivent accompagner l’interprétation ; une métrique de dénominateur nul est `N/A (undefined)`. Aucun seuil d’écart acceptable n’est fixé.

## Provenance et limites des portes

- Source, modèle et protocole (`results/final_metrics.json`) : `7e50d0ce13f08b45ed1740127fe56f9c90c8eeec37a11288a372afcc61efe3b3`, `aa1565caf7fed3af833a5613fd76416b6489c9a9f31ee8c523d65e5d9113da33` et `b0bfaf9ba5b9c3b40dc91c52d34281227846fce4d11b24ff6bf9a166550adc24`.
- Script de reprise : commit `2e1f761b5fa4227fbc2c7e4df4f67e86ea84bdb2`, SHA-256 `2f2657f7625f9b15518182d6a07a5b735602eb514badbe6ad30921c4c5baac16`. `code_revision` enregistré : `14f2de70b447235519face7c84a270bd1824c20b` ; il correspond au HEAD avant la reprise et non au script de reprise. Source : `results/final_metrics.json`.
- Module métriques : `990880d8849c1e5086c90fd8df769195318d31b909fe8824206496a7eb429202` ; module publication : `751ec66350c9142e15a533c4a93ec569ea3864411037a7084dcb4244da925794`. Source : `results/final_metrics.json`.
- Prédictions : `a2c7ac27403fdb8825ba7db8fe5c7f2d0a90343cf21450b3c6d3256cf77abfdc` ; manifeste d’évaluation : `45f71c632a9d796d7c904dd055c209a2568c715feadfa114850a31cdfdb0d029` ; journal de l’archive : `dbe3d2b8de89d851aa5037db6336cce104ad34f74f5a40d4d605b1ce5197053d` (5 entrées, `reserved`, `predictions_saved` et `completed` liés au même lancement). Sources : `results/artifact_manifest.json` et `journal/journal.jsonl`.
- Archive : `0943a91890aa79c0b95a3b91a370d7876a5cd78e1867f6f86723a0825fdec393` ; run de publication `e0adc3e7bee847648199f57a5b15de41`. Source : archive et `fairness_audit/manifest_d48.json`.
- Le fichier `results/final_metrics.json` marque `registry_smoke` **UNVERIFIED** et `promotion_ready` **false**. Les six portes MLflow déclarées séparément et la version promue exigent un contrôle indépendant.
- La non-régression compare la PR-AUC du test final à `0,36970357094266615`, moyenne LogReg du benchmark de développement 10 × 5 : les périmètres ne sont pas identiques. Sources : `results/final_metrics.json`, `quality_gates.non_regression`, et `results/stats/results.json`.
- La couverture fraude de 0,961305 dépasse le plancher 0,96 de **0,001305**, environ 0,13 point de pourcentage ; son IC 95 % descend sous ce plancher. Sources : `results/final_metrics.json` et `results/bootstrap_intervals.json`.

D51 : non vu, à documenter par Omar.
