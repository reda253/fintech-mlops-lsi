# Exigences du benchmark P2 - issue #22

Statut : cahier des charges, pas un resultat de benchmark. Aucun Optuna,
benchmark complet ou test statistique n'est execute pour rediger ce document.

## Sources et perimetre

- [Spec P2](specs/P2_Data_Scientist_1.md), notamment sections 4.5-4.7.
- [Spec commune](specs/00_Commun_1.md), section 10.5.
- [Issue #22](https://github.com/reda253/fintech-mlops-lsi/issues/22), lue le
  17/10/2026 : responsable P2, livraison #8 a Omar ; Definition of done =
  documented, tested, demonstrated to the team. Les trois cases sont ouvertes.
- Implementation actuelle : [README ML](../ml/README.md),
  [template tracking](../ml/tracking_smoke.py),
  [pipeline](../ml/src/pipeline/steps.py),
  [endpoint performance](../ml-service/app/routes/model.py),
  [test du contrat](../ml-service/tests/test_model_routes.py).

Les contraintes connexes des sections 4.2-4.4, 4.8-4.12 et 5.2/5.6 sont
referencees explicitement : elles ne sont pas inventees comme des ajouts a #22.
Le dataset final reste hors perimetre de cette preparation : aucune lecture.

## Checklist numerotee

1. [ ] Utiliser seulement la zone development chronologique de la source
   d'entrainement ; reserver les deux zones de calibration et le test final.
   Reference : spec P2 4.1-4.2.
2. [ ] Ajuster le preprocessing dans le train de chaque pli, jamais sur la
   validation ni sur une matrice deja transformee sur tout development.
   Reference : spec P2 4.3, decision D13 de la spec commune.
3. [ ] Sous-echantillonner uniquement les legitimes du train, ratio 1 fraude
   pour 10 legitimes ; validation naturelle et correction avec beta reel.
   Reference : spec P2 4.4. Un ratio ne remplace pas le beta mesure du pli.
4. [ ] Comparer exactement cinq familles : LogisticRegression, RandomForest,
   XGBoost, Nystroem + LinearSVC, MLPClassifier avec early stopping.
   Reference : spec P2 4.5. Pas de SVC RBF exact, pas de substitution LightGBM.
5. [ ] Effectuer une recherche aleatoire avec Optuna, meme budget par modele,
   sur une partie temporelle distincte au debut de development. Reference : 4.5.
   Les 30 essais sont un exemple, pas un nombre obligatoire.
6. [ ] Figer les configurations avant le benchmark ; ne pas refaire Optuna
   dans chaque pli. Documenter l'absence de CV imbriquee comme limite.
   Reference : spec P2 4.5.
7. [ ] Mesurer la PR-AUC avec average precision, critere principal des tests
   confirmatoires. Reference : spec P2 4.6.
8. [ ] Mesurer ROC-AUC, MCC, precision, rappel, F1 et accuracy, en rappelant
   pourquoi l'accuracy peut etre trompeuse sur ce desequilibre. Reference : 4.6.
9. [ ] Choisir le seuil par maximisation de F1 sur une validation INTERNE au
   train ; appliquer ensuite ce seuil a la validation externe du pli. Ne pas
   optimiser sur cette validation externe. Reference : spec P2 4.6.
10. [ ] Rapporter Brier score, ECE et diagrammes de fiabilite. Reference : 4.6.
11. [ ] Mesurer l'inference du pipeline complet, CPU, un thread, meme machine,
    1 000 appels d'une seule ligne ; p50 et p95, cible p95 < 50 ms.
    Reference : spec P2 4.6 et spec commune 1.4.
12. [ ] Effectuer 10 repetitions de CV stratifiee a 5 plis avec 10 seeds
    distinctes : 50 evaluations par modele, 250 pour cinq modeles. Reference : 4.7.
13. [ ] Agreger les cinq plis par repetition : 10 moyennes par modele, donc
    50 lignes modele/repetition. Les 50 plis d'un modele ne sont pas 50 blocs
    independants pour les statistiques. Reference : spec P2 4.7-4.8.
14. [ ] Journaliser chaque pli : seed, pli, hyperparametres, metriques, duree.
    References : 4.7, 4.12, 5.2. Conserver commit Git, SHA-256 des sources et
    versions ; structure parent pipeline / enfant Training / enfant pli.
15. [ ] Utiliser le template de ml/tracking_smoke.py et une URI explicitement
    configuree. References : spec P2 5.2, ml/README.md. Les essais SQLite sont
    locaux ; les resultats officiels proviennent du Job du cluster (5.6).
16. [ ] Transmettre a P3 le benchmark et le meilleur modele provisoire en S6
    (livrable #8), sans le presenter comme le modele final valide statistiquement.
    References : spec commune 10.5 ; spec P2 4.8-4.10, livrables transmis.
17. [ ] Documenter, tester et demontrer le livrable a l'equipe. References :
    Definition of done de #22, spec commune 10.5. Une CI verte seule ne vaut
    ni benchmark complet ni demonstration.
18. [ ] Decouper le travail en sous-issues au demarrage ; ne fermer #22 par
    `Closes #22` que lorsque son perimetre est entierement termine.
    Reference : consigne de l'issue #22, pas une exigence ML de la spec.

Le cout metier est un BONUS de 4.6 ; ce n'est pas un critere obligatoire ajoute.
Friedman, Wilcoxon et Holm appartiennent au livrable #9 (4.8 et 10.5) : #22
prepare les resultats necessaires, sans inventer de significativite.

## Ambiguites et decisions a prendre

Cette section conserve l'historique des propositions. Les decisions du
23/10/2026 ci-dessous la remplacent uniquement pour les points valides.

Aucune proposition ci-dessous n'est validee et aucun defaut d'execution n'en
decoule. Accord de Basma et alignement avec P3 avant les calculs longs.

Le notebook 03b declare une regle operationnelle : ecart moyen AP aleatoire
moins AP groupee par carte strictement superieur a 0,02 => proposer
StratifiedGroupKFold, sinon StratifiedKFold. Il avertit lui-meme qu'une CV
groupee modifierait 4.7 et exige l'accord de l'equipe.
Le fichier `reports/leakage_diagnostic_summary.json` est absent. En revanche,
le CSV local ignore `reports/leakage_diagnostic_folds.csv` existe : sa lecture
reelle donne 5 plis aleatoires (AP moyenne 0,8288027672680318), 5 groupes par
carte (0,8238238737890368), et un holdout temporel (0,8225443559117582).
L'ecart recalcule est 0,00497889347899505, inferieur a 0,02 : la regle declaree
propose donc StratifiedKFold, coherent avec 4.7. Il s'agit d'une relecture des
scores stockes, PAS d'une nouvelle execution ; leur provenance complete reste
a verifier en l'absence de synthese. Aucune decision nouvelle n'est imposee.

| Point | Ce que fixent les sources | Proposition a approuver / alternative |
|---|---|---|
| Budget Optuna | 4.5 : meme budget, 30 seulement en exemple | Proposer 30 essais par modele apres chronometrage ; alternative 50 si les ressources le permettent. |
| Frontiere Optuna / benchmark | 4.5 : debut temporel distinct, pourcentage/date non specifies | Proposer les premiers 20 % de development pour Optuna et les 80 % suivants pour le benchmark, disjoints ; alternative 30/70. Calculer ensuite les dates et effectifs REELS, inclure les gardes de frontiere. |
| Holdout interne Optuna | 4.5 ne fixe ni taille ni methode interne | Proposer une validation temporelle 80/20 dans la seule partie Optuna ; alternative 70/30. Jamais les 15 % de calibration globale. |
| CV apres diagnostic 03b | 4.7 impose 10x5 stratifie ; 03b est un diagnostic, pas une autorisation de changer la spec | Proposer de conserver le protocole prescrit et de documenter 03b ; si son diagnostic impose une alternative temporelle/groupee, demander une decision d'architecture explicite avant de remplacer 4.7. Aucun resultat de 03b n'est invente ici. |
| Seuil precision/rappel/F1/MCC | 4.6 fixe deja l'objectif : maximum F1 sur validation interne du train | Ne PAS substituer arbitrairement 0,5. Proposer un holdout interne chronologique 80/20 ; alternative 70/30. Figer aussi la grille, les egalites et le reajustement final sans fuite. |
| Probabilites du SVM | 4.5 : scores convertis par calibration ; 4.2 interdit d'utiliser les zones de calibration pour comparer les modeles | Proposer une calibration sigmoide exclusivement interne au train du pli pour les metriques probabilistes ; alternative calibration interne CV a 3 plis. Le cout et le protocole restent a approuver. |
| ECE | 4.6 exige ECE sans definir les bins | Proposer 10 bins de largeur egale ; alternative 15. Figer avant lecture des scores. |
| Modele provisoire | 10.5 exige le meilleur provisoire, 4.9 concerne le modele final | Proposer le meilleur PR-AUC moyen des 10 repetitions, etiquete `provisional`, jamais `champion` automatique. Alternative : departage Brier puis latence pour une egalite numerique. P3 valide le packaging et les alias. |
| Spec contre issue #22 | Issue : titre 10x5, renvoi 4.5-4.7, DoD generique ; aucun budget ni schema supplementaire | Aucun conflit de protocole observe. Proposer de lier cette checklist a l'issue ; ne pas transformer son silence en nouvelle exigence. |
| Spec contre endpoint P3 | Endpoint code en dur LightGBM et omet SVM ; plusieurs valeurs et champion sont fixes | Proposer avec P3 de remplacer le mock par les cinq familles de 4.5. Aucun chiffre du mock ne devient un resultat P2. |
| Formats Parquet | Aucun lecteur folds.parquet / repeat_means.parquet dans les fichiers inspectes | Le schema ci-dessous est une PROPOSITION de contrat a valider avec P3, pas une compatibilite existante. |

## Décisions validées

Date : 23/10/2026. **décidé par Basma** (validation humaine dans le chat).
Les sections 4.4-4.7 et 10.5 restent les references normatives.

- 30 essais par modele, budget global identique pour les cinq familles ;
  budget a reviser apres le chronometrage leger, sans lancer Optuna ici.
- Partition temporelle proposee 20/80 de development ; holdout interne 80/20.
  Validation conditionnelle aux effectifs : aucun seuil universel de fiabilite
  de l'average precision n'est defini dans la spec. L'adequation reste donc
  explicitement a confirmer, sans ajustement opportuniste apres les scores.
- StratifiedKFold, 5 plis x 10 repetitions, seeds 0 a 9, memes plis pour les
  cinq modeles. Une carte peut figurer dans train et validation. Le diagnostic
  03b n'est pas reproductible actuellement : module, script et resume JSON
  absents ; ses scores stockes ne prouvent pas l'absence de fuite.
- Seuil : maximum F1 sur validation interne au train, jamais sur le pli mesure.
- Provisoire : meilleure PR-AUC moyenne des 10 repetitions ; tag provisional,
  pas de promotion automatique champion ni de superiorite statistique supposee.
- SVM : probabilites par calibration sigmoide interne au train uniquement.
- ECE : 10 intervalles de largeur egale.
- Log-loss ajoutee aux metriques secondaires sur demande de Basma ; elle
  n'est pas une obligation supplementaire attribuee a la spec 4.6.

### Comptage leger reel, 23/10/2026

Exception autorisee par Basma : lecture des dates seules de tout fraudTrain,
puis lecture par blocs des etiquettes de development exclusivement. Aucun
label ni feature de calibration n'a ete charge. Aucun modele entraine pour ce
comptage. Tri stable et timestamps egaux conserves du meme cote de la coupure.

| Option | Partie | Lignes | Fraudes |
|---|---|---:|---:|
| 20/80 | Optuna total | 181534 | 1560 |
| 20/80 | Train interne Optuna | 145227 | 1323 |
| 20/80 | Validation interne Optuna | 36307 | 237 |
| 20/80 | Benchmark | 726138 | 3561 |
| 30/70 | Optuna total | 272301 | 2037 |
| 30/70 | Train interne Optuna | 217840 | 1747 |
| 30/70 | Validation interne Optuna | 54461 | 290 |
| 30/70 | Benchmark | 635371 | 3084 |

Development : 907672 lignes, 5121 fraudes. Pour 20/80 : Optuna termine le
2019-04-05 01:23:52 ; benchmark commence le 2019-04-05 01:24:56.
Le holdout interne commence le 2019-03-19 10:46:46. Aucun timestamp commun.
Verdict : pas de partie vide ni sans fraudes ; 237 fraudes permettent un
premier diagnostic mais ne certifient pas une PR-AUC precise. Le 30/70 fournit
290 fraudes internes au prix d'un benchmark reduit. Ne pas figer l'adequation
sans accord humain sur le niveau d'incertitude acceptable.

### Decisions encore ouvertes et lancement bloque

- Sampler : RandomSampler seede respecte une recherche aleatoire independante
  (4.5) ; TPE seede est adaptatif et peut exploiter les essais precedents.
  Les deux sont possibles techniquement, mais TPE exige de clarifier le mot
  "aleatoire" avec l'equipe. Aucun choix impose ; seed proposee 42.
- Timeout PAR ESSAI : Study.optimize(timeout=...) est un plafond d'etude.
  Proposition : essais dans un processus surveille, interrompu au delai et
  journalise comme interrompu ; alternative : bornes d'iterations/estimateurs
  et pruning cooperatif, qui ne sont PAS une garantie murale stricte.
  Duree, comportement des essais interrompus et sampler restent a confirmer.
- Adequation du 20/80, regle d'egalite des seuils F1 et des modeles provisoires :
  a confirmer. Toute configuration incomplete doit refuser un lancement reel.
- Questions P3 et formats : voir [questions_omar_p2.md](questions_omar_p2.md).

## Estimation du cout de calcul

**Mesure diagnostique reelle du 23/10/2026, pas un benchmark.** Les cinq
modeles ont ete mesures sur le meme petit pli, et non sur les volumes complets.

Nombre de fits minimaux : `modeles x n_trials + 250 evaluations` =
`5 x n_trials + (5 modeles x 10 repetitions x 5 plis)`.

Cette formule suppose un seul fit par essai Optuna et par evaluation ; ajouter
les fits du seuil interne, de la calibration SVM, du reajustement et les echecs.

Temps estime apres mesure : `somme_m(n_trials x temps_trial_m + 50 x temps_fold_m)`
+ cout des fits internes + mesures de latence + journalisation/artefacts.

| Modele | Temps d'un essai | Temps d'un pli | Ressources / memoire |
|---|---|---|---|
| LogisticRegression | 0,016537 s mesurees, parametres smoke | Fit estime 1,624 s ; pli total estime 43,673 s | 1 thread CPU |
| RandomForest | 0,125068 s mesurees, 30 arbres profondeur 6 | Fit estime 12,286 s ; pli total estime 56,434 s | 1 thread CPU |
| XGBoost | 0,047458 s mesurees, 30 arbres profondeur 3 | Fit estime 4,662 s ; pli total estime 47,182 s | hist CPU, 1 thread |
| Nystroem + LinearSVC | 0,130032 s mesurees, 64 composantes et calibration CV 3 | Fit estime 12,774 s ; pli total estime 55,881 s | 1 thread CPU |
| MLPClassifier | 0,114215 s mesurees, couche 32, plafond 40 iterations | Fit estime 11,220 s ; pli total estime 53,295 s | early stopping, 1 thread CPU |

Protocole exact : 4000 lignes stratifiees tirees UNIQUEMENT du train interne
Optuna ; seed 42, un seul pli diagnostique. Le helper make_fold_data existant
ajuste le preprocessing sur 3200 lignes naturelles, puis conserve 29 fraudes
et 290 legitimes (319 lignes, beta=0,09145380006307159). Validation naturelle :
800 lignes, 7 fraudes. Ces 7 fraudes ne permettent aucune conclusion de
qualite des modeles. Correction via correct_proba, sans calibration globale.

Preprocessing commun mesure : 0,230843 s. Sortie : 75 features sur cet
echantillon ; ce n'est pas une preuve d'egalite de cardinalite au grand jeu.
Machine : Windows AMD64, Intel64 Family 6 Model 140 Stepping 1, GenuineIntel.
Versions : Python 3.11.17, numpy 2.4.6, pandas 3.0.6, scikit-learn 1.9.1,
XGBoost 3.2.0, MLflow 3.17.1. Aucun avertissement de modele lors de cette mesure.

**ESTIMATIONS LINEAIRES, PAS DES BORNES NI DES TEMPS MESURES A GRANDE ECHELLE.**
Le train sous-echantillonne moyen d'un pli benchmark est estime a
3561 x 4/5 x 11 = 31336,8 lignes. Le fit estime vaut le fit mesure multiplie
par 31336,8/319. Le total ajoute le preprocessing multiplie par 726138/4000
et la prediction validation multipliee par (726138/5)/800. Cette extrapolation
peut surestimer le cout fixe et sous-estimer les iterations et la memoire.

Sans cache et aux seuls parametres smoke, 250 evaluations donnent une
extrapolation de 12823,267 s (environ 3,56 h), NON une execution reelle.
Les 30 essais x 5 modeles donneraient 593,038 s pour les fits seuls aux
parametres smoke et au volume train Optuna estime, SANS preparation, lecture,
seuil interne ni surcout des espaces de recherche. Ne pas sommer ces valeurs
pour promettre un delai officiel. L'estimation depasse l'ordre de grandeur
indicatif 30-90 min du mode full (5.1), sans demontrer un depassement reel.

Risques du budget : RF et XGB vont jusqu'a 300 arbres et plus de profondeur ;
SVM jusqu'a 256 composantes (cout non lineaire), avec plusieurs fits internes ;
MLP jusqu'a 150 iterations et des couches plus grandes ; LogReg peut converger
plus lentement pour d'autres C. Aucun timeout ni nouveau budget n'est valide.
Plafonds par essai a discuter apres cette premiere mesure : 120 s ou 300 s,
uniquement comme propositions, jamais comme garantie de suffisance.

Commande : avec la racine et ml/src dans PYTHONPATH,
`python -m benchmark.models_smoke --diagnostic-smoke --sample-rows 4000`.
Sans ce flag, les configurations incompletes refusent le lancement avant
lecture de donnees. Les sorties JSON optionnelles sont limitees a un chemin
hors depot ; aucun fichier de donnees ou rapport n'est cree dans le depot.

MLflow models_smoke : tentative reelle via get_tracking_uri ; FAIL,
MlflowException, categorie connection, connexion impossible ou refusee.
Aucun run serveur cree confirme, aucune bascule SQLite et aucun Docker lance.
Relancer seulement le diagnostic explicite lorsque le serveur sera disponible.

## Format de resultats attendu par P3

### Contrat actuellement visible (pas des mesures reelles)

Dans ml/README.md : convention URI et template de runs, mais AUCUN schema
Parquet. Dans ml/src/pipeline/steps.py : metriques `pr_auc`, `roc_auc`,
`brier_score`, `latency_p95_sec`, `conformal_coverage`, `review_rate` ; parametre
`model_type` et metrique `train_duration_seconds`. Les dernieres metriques de
conforme du squelette sont simulees : elles ne doivent pas servir au benchmark.

GET `/api/v1/ml/performance` de ml-service/app/routes/model.py expose :

| Chemin JSON | Cles observees |
|---|---|
| `benchmark` | `evaluation_metric`, `cross_validation`, `selected_champion`, `models` |
| `benchmark.models[]` | `name`, `pr_auc`, `roc_auc`, `brier_score`, `inference_p95_ms`, `rank` |
| `statistical_validation.friedman_test` | `statistic`, `p_value`, `null_hypothesis_rejected` |
| `statistical_validation.holm_bonferroni_correction[]` | `comparison`, `p_value`, `adjusted_alpha`, `significant` |
| `statistical_validation` | `conclusion` |

Noms presents dans ce mock : `LogisticRegression`, `MultiLayerPerceptron`,
`RandomForest`, `LightGBM`, `XGBoost`. La spec impose le SVM a la place de
LightGBM. Le nom de sortie du SVM n'est pas defini : proposition `SVM`, a valider.
Garder `MultiLayerPerceptron` comme etiquette API du MLP est une proposition
d'alignement, pas le nom de classe sklearn (`MLPClassifier`).

Les tests actuels du endpoint ne verifient que la presence de `benchmark` et
`fairness_audit`, pas les cinq noms ni la validite des tests statistiques.
Il n'existe pas de calcul Friedman/Holm dans ml/src a ce stade : seulement
des champs JSON codes en dur dans le serving. Ne pas les recopier comme preuves.

### Proposition de tables - validation P3 requise

`results/folds.parquet` : une ligne par modele/repetition/pli, 250 lignes si
les cinq modeles terminent les 50 evaluations. Cle unique `(name, repeat, fold)`.

| Colonnes proposees | Type / unite |
|---|---|
| `name`, `repeat`, `fold`, `seed`, `run_id` | string, int, int, int, string ; conventions d'index a figer |
| `pr_auc`, `roc_auc`, `brier_score` | float ; noms identiques au JSON P3 |
| `mcc`, `precision`, `recall`, `f1`, `accuracy`, `ece` | float ; noms absents du contrat P3 actuel, a approuver |
| `threshold`, `beta`, `n_train_before`, `n_train_after`, `n_validation`, `validation_prevalence` | float/int ; tracabilite, pas deja un contrat P3 |
| `train_duration_seconds` | float, secondes ; nom de la metrique du pipeline |
| `inference_p50_ms`, `inference_p95_ms` | float, millisecondes ; p95 aligne sur le endpoint |
| `git_commit`, `source_sha256`, `params_json` | strings ; metadata de reproductibilite, format a valider |

`results/repeat_means.parquet` : une ligne par `(name, repeat)`, donc 50 lignes
pour cinq modeles, les memes noms de metriques contenant les moyennes des cinq
plis. Ajouter `n_folds=5` et refuser une repetition incomplete, plutot que
produire une moyenne silencieuse sur moins de cinq plis (proposition de garde).
Pour Friedman/Wilcoxon : pivoter `repeat x name` sur `pr_auc`, 10 blocs.

Compatibilite sans conversion NON demontree : aucun lecteur Parquet n'existe.
Le pipeline emploie des secondes (`latency_p95_sec`), le endpoint des
millisecondes (`inference_p95_ms`) ; un accord d'unites et un adaptateur P3
sont necessaires. Ni `rank` ni `selected_champion` ne sont des scores de pli.
L'etape de validation #9 calculera les statistiques reelles avant publication.

## Etat de livraison

Ce document satisfait seulement la preparation des exigences. Il ne coche pas
le benchmark termine, la demonstration d'equipe ni les decisions encore ouvertes.
Pas de nouveaux modeles, pas de resultats Parquet vides ou artificiels produits.
