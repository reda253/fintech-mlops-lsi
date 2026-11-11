# Issue #24 — revue du résultat existant

**Décision ouverte, postérieure aux résultats.** Revue du 7 novembre 2026.
Au moment de cette revue initiale, XGBoost était provisoire et aucun changement
de capacité, grille ou fractions n'était décidé. D44 étend ensuite la grille
post hoc ; les nouveaux alpha n'ont pas encore été évalués.

## Périmètre et provenance

Analyse exclusivement des artefacts déjà produits : `report.md`, `results.json`,
`README.md`, les figures et le journal JSONL. Aucun entraînement, aucune nouvelle
prédiction, aucune lecture de données Sparkov ou de zones de calibration, aucun
accès au jeu de test final. Les calculs nouveaux sont uniquement arithmétiques
et statistiques à partir des agrégats enregistrés.

- Dossier local initial : artefacts conservés hors dépôt.
- Journal de lancement initial : conservé hors dépôt.
- Expérience MLflow : `p2_final_calibration`.
- Run : `160fa16ab027444fbb813dc5f50ddc36` (identifiant lu dans le journal ;
  aucune interrogation du serveur nécessaire pour cette revue).
- Lancement : `bbb9b949c3ee4db9826a6d9800925571` ; dernier événement
  `launch_completed`, le 2026-11-07 à 11:51:06.165131 UTC.
- SHA-256 de `results.json` :
  `1582635b263f5e02b5dc8cf249c7b504ecd350b44577750c2352e1a0d9f22d6f`.
- SHA-256 de `report.md` :
  `0269ce1665752e7c33fe37b44f946e228f368260f369c1c308523f9da06c5a8e`.

Le dossier contient cinq fichiers : les trois documents ci-dessus,
`reliability.png` et `alpha_review.png`. Aucun vecteur de probabilités,
ensemble de prédiction individuel ou label n'est sauvegardé. Aucun
`candidate_model.joblib` n'a été produit : `selected_alpha=null` et
`capacity_met=false`.

## Résultat de calibration

Sur la moitié de comparaison, hors ajustement des calibrateurs :

| Méthode | Brier | ECE |
|---|---:|---:|
| Avant calibration, après correction d'a priori | 0.0016056283608987722 | 0.0012298263183607564 |
| Sigmoïde | 0.0013913714978400625 | 0.0004079168402078386 |
| Isotonique | 0.001432282832344267 | 0.00025109755018345813 |

La sigmoïde a été choisie selon le **Brier**, conformément au protocole.
Le meilleur ECE de l'isotonique ne justifie pas de remplacer après coup le
critère de choix. Le beta enregistré est `0.05673917595792371`.

## Composition de la revue, par alpha et par bloc

Les effectifs sont **reconstitués**, et non des compteurs directement sauvegardés.
Le JSON fournit les tailles N, les taux de revue et les quantiles. Pour la
probabilité calibrée de fraude p, la règle enregistrée dans le workflow est :
classe 0 incluse si `p <= q0`, classe 1 incluse si `p >= 1-q1`.

- Si `q0 > 1-q1`, aucun ensemble vide n'est possible : toute revue est ambiguë.
- Si `q0 < 1-q1`, aucun ensemble ambigu n'est possible : toute revue est vide.
- Les inégalités sont strictes entre les deux seuils dans les trois cas présents.
  Il n'y a donc pas de cas limite de seuils égaux à résoudre.

| alpha | q0 | 1-q1 | Type de revue possible |
|---|---:|---:|---|
| 0.01 | 0.016058107799944932 | 0.001898678478443161 | {0,1} seulement |
| 0.05 | 0.0007175058628636045 | 0.05349269886633179 | Ensemble vide seulement |
| 0.10 | 0.00016433549073552626 | 0.13276934525693784 | Ensemble vide seulement |

Pour chaque ligne, `round(N * taux_revue) / N == taux_revue` a été vérifié
avec les nombres du JSON à pleine précision. Les singletons sont `N - revue`.

| alpha | Bloc | N | Vides : nombre (%) | Ambigus : nombre (%) | Singletons : nombre (%) |
|---|---|---:|---:|---:|---:|
| 0.01 | Choix | 48625 | 0 (0 %) | 1102 (2.266324 %) | 47523 (97.733676 %) |
| 0.01 | Évaluation | 48626 | 0 (0 %) | 1136 (2.336199 %) | 47490 (97.663801 %) |
| 0.05 | Choix | 48625 | 2133 (4.386632 %) | 0 (0 %) | 46492 (95.613368 %) |
| 0.05 | Évaluation | 48626 | 2204 (4.532555 %) | 0 (0 %) | 46422 (95.467445 %) |
| 0.10 | Choix | 48625 | 4610 (9.480720 %) | 0 (0 %) | 44015 (90.519280 %) |
| 0.10 | Évaluation | 48626 | 4644 (9.550446 %) | 0 (0 %) | 43982 (90.449554 %) |

Augmenter alpha réduit les ensembles de prédiction ; cela peut transformer
des singletons en ensembles vides. Comme les ensembles **vides et ambigus**
sont tous deux envoyés en revue, la revue n'est pas nécessairement décroissante
en alpha. Les seuils enregistrés expliquent ici le passage d'une revue ambiguë
à une revue entièrement composée de vides. Ils ne permettent pas de suivre
les transitions individuelles entre alpha, faute de prédictions sauvegardées.

## Effectifs de fraudes : enregistré, reconstitué ou indisponible

| Bloc | Lignes | Fraudes | Provenance |
|---|---:|---:|---|
| Ajustement des quantiles | 97251 | 560 | Compteur explicite `conformal_fit_counts["1"]` |
| Choix d'alpha | 48625 | NON DISPONIBLE pour le premier lancement | Aucun compteur sauvegardé lors du premier lancement ; les versions ultérieures enregistrent ces effectifs et couvertures. |
| Évaluation | 48626 | 312 | Unique dénominateur compatible avec toutes les couvertures enregistrées |

L'effectif 312 n'a pas été supposé à partir d'un taux arrondi : tous les entiers
`1 <= n_fraude < 48626` ont été examinés. Pour les trois alpha, les couvertures
fraude doivent être des rapports `k_fraude/n_fraude`, et les couvertures légitime
des rapports `k_legitime/(48626-n_fraude)`. **Seul n_fraude=312** satisfait
simultanément les six rapports. L'unicité a été vérifiée avec égalité flottante
stricte, puis avec une tolérance absolue de `1e-12`.
Cette reconstitution suppose des proportions non pondérées, sauvegardées à
pleine précision comme dans le rapport ; elle n'est pas une relecture des labels.

Les 560 fraudes de l'ajustement suffisent aux rangs finis pour les trois alpha
(minima 99, 19 et 9 par classe). Le nombre de fraudes dans le bloc de choix reste
indéterminable : les taux de revue dépendent des prédictions, pas des labels.
Aucune couverture du bloc de choix ou de l'ajustement n'est inventée.

## Couverture fraude et intervalles Clopper–Pearson

IC bilatéraux marginaux à 95 %, calculés avec SciPy 1.17.1 sur les succès
reconstitués du bloc d'évaluation (n=312). Pour k succès :
`L=Beta.ppf(0.025,k,n-k+1)` (0 si k=0) et
`U=Beta.ppf(0.975,k+1,n-k)` (1 si k=n).

| alpha | Fraudes couvertes / total | Couverture brute | IC 95 % brut | Cible 1-alpha dans l'IC ? |
|---|---:|---:|---|---|
| 0.01 | 312 / 312 | 1.0 | [0.9882462893472557 ; 1.0] | Oui : 0.99 |
| 0.05 | 287 / 312 | 0.9198717948717948 | [0.8839866051841883 ; 0.947475465935119] | Non : 0.95 |
| 0.10 | 279 / 312 | 0.8942307692307693 | [0.8546743757337543 ; 0.9260671683987806] | Oui : 0.90 |

À alpha=0.05, **91.98717948717948 %** a donc un IC
**[88.39866051841883 % ; 94.7475465935119 %]**, qui exclut 95 %.
Sous l'hypothèse binomiale, cette observation n'est pas compatible avec 95 %
au sens de cet IC bilatéral marginal. Le test binomial exact bilatéral donne
`p=0.019129449759425154` pour H0 : couverture=0.95.

**Limites de l'interprétation :** ces IC supposent des indicateurs de couverture
Bernoulli indépendants avec probabilité commune, conditionnellement au système
ajusté. La dépendance entre transactions d'une même carte et la dérive temporelle
ne sont pas contrôlées par ces agrégats. Les IC n'intègrent pas l'incertitude
liée au réajustement des quantiles sur un autre échantillon. Ce sont des IC
marginaux par alpha, sans correction simultanée des trois comparaisons, et une
analyse postérieure à l'observation du résultat. Ce constat n'est donc ni une
preuve indépendante de dérive, ni une démonstration de défaut du code conforme.
Une cible dans l'IC n'est pas une preuve que la couverture est garantie.

Les IC de couverture du bloc de choix sont **non calculables** : son nombre
de fraudes et son nombre de fraudes couvertes ne figurent pas dans les artefacts.
La couverture sur l'ajustement des quantiles n'est pas une mesure indépendante.

## Comparaison temporelle des blocs

| alpha | Revue choix (fraction brute) | Revue évaluation (fraction brute) | Écart évaluation-choix, points de % | Couverture légitime évaluation | Couverture fraude évaluation |
|---|---:|---:|---:|---:|---:|
| 0.01 | 0.022663239074550128 | 0.023361987414140584 | +0.06987483395904555 | 0.9898373142360393 | 1.0 |
| 0.05 | 0.04386632390745501 | 0.045325546004195284 | +0.14592220967402716 | 0.9500351864883885 | 0.9198717948717948 |
| 0.10 | 0.09480719794344473 | 0.09550446263315922 | +0.0697264689714483 | 0.901995280870969 | 0.8942307692307693 |

La revue augmente légèrement dans le bloc d'évaluation, temporellement postérieur.
Cela décrit un changement observé ; aucun test de dérive ne peut être conclu
sur cette seule comparaison. La comparaison de **couverture** entre blocs est
impossible, car les couvertures du bloc de choix ne sont pas enregistrées.
Le déficit à alpha=0.05 s'apprécie face à la cible nominale, pas face à une
couverture antérieure mesurée. Aucun taux du bloc de choix ne doit être imputé
à partir des 560 ou 312 fraudes des autres blocs.

## Options méthodologiques — aucune n'est exécutée ou adoptée

| Option | Intérêt / coût opérationnel | Coût en intégrité du protocole et validation nécessaire |
|---|---|---|
| Conserver capacité 2 %, grille et fenêtres | Conserve le constat d'échec de capacité ; pas de modèle empaqueté pour le service | Aucun assouplissement post-hoc. Le système candidat reste non déployable selon cette règle ; il faut une nouvelle proposition validée avant toute autre expérimentation. |
| Capacité revue différente, approuvée métier | Plus de travail analyste. À titre d'illustration post-hoc, une capacité 2.5 % aurait accepté alpha=0.01 sur le choix (2.266324 %) ; l'évaluation observée vaut 2.336199 % | Modification du seuil après consultation des deux blocs. L'évaluation actuelle ne redevient pas un test indépendant d'une règle maintenant choisie grâce à elle. Justification métier indépendante et validation prospective sur nouvelles observations requises ; aucune recommandation de 2.5 % ici. |
| Alpha hors grille initiale | Peut déplacer la frontière entre ensembles ambigus et vides ; aucune baisse de revue ne peut être promise | Extension de la recherche après résultats. Les scores individuels n'étant pas sauvegardés, les nouveaux quantiles et revues ne sont pas calculables à partir des artefacts seuls. Nouveau protocole et nouveaux calculs explicitement autorisés, journal de déviation, puis nouvelle évaluation indépendante nécessaires. Ne pas optimiser sur le quart d'évaluation déjà consulté. |
| Conforme avec fenêtre d'ajustement plus récente | Peut mieux suivre une dérive, mais réduit les effectifs par classe et peut rendre certains quantiles finis impossibles | Modification des fenêtres après résultats. Réutiliser le bloc de choix ou d'évaluation pour ajuster détruirait leur rôle initial. Fixer une règle de fenêtre avant de nouvelles observations, conserver un nouveau bloc ultérieur distinct pour l'évaluation, et recontrôler les effectifs par classe. Aucun gain garanti. |

Les zones ayant déjà été consultées ne peuvent pas être présentées comme
« jamais vues » après un changement de protocole. Aucune de ces options
n'autorise la lecture du jeu de test final dans ce flux. Le journal des
lancements doit conserver les résultats actuels et toute décision motivée
ultérieure ; une entrée de journal ne restaure pas l'indépendance statistique.

## Contrôles de cette revue et décision ouverte

- Tailles de blocs, compteurs de revue et singletons vérifiés arithmétiquement.
- Unicité du dénominateur fraude du bloc d'évaluation vérifiée sur tous les
  entiers admissibles, en version stricte et avec tolérance 1e-12.
- IC Clopper–Pearson calculés sans import du workflow d'entraînement.
- Aucune réexécution de benchmark, Optuna, calibration ou prédiction.
- Aucun changement de code, de paramètres, d'alpha, de seuil ou d'artefact initial.
- Manques de traçabilité : compteur de fraudes et couvertures du bloc de choix,
  compteurs explicites des types d'ensembles et des succès de couverture.
  Les versions ultérieures enregistrent les effectifs et couvertures du bloc
  de choix ; ils ne sont pas disponibles rétroactivement pour le premier lancement.

**Décision ouverte, postérieure aux résultats.** La capacité de 2 % n'est
respectée par aucun alpha de la grille initiale. XGBoost reste provisoire ; aucune
promotion ni nouvelle sélection n'est effectuée dans cette revue.


## Test final consommé — décision de Basma, 11 novembre 2026

Le test final a été consommé le 10 novembre 2026 pour le candidat provisoire
d’empreinte `aa1565caf7fed3af833a5613fd76416b6489c9a9f31ee8c523d65e5d9113da33`.
L’empreinte de la source enregistrée a été comparée par Basma à celle de
`fraudTest.csv` et correspond. La commande et l’auteur du lancement ne sont
pas tracés dans le journal. Le journal conserve un début et une fin, mais ne
prouve pas qu’aucune autre lecture n’a eu lieu. Les IC bootstrap n’ont pas été
calculés ; aucune prédiction par ligne n’a été conservée dans le dossier connu.
Aucune décision ultérieure de sélection ou de réglage ne doit s’appuyer sur ce jeu.
