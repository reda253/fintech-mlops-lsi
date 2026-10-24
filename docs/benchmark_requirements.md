# Exigences du benchmark P2 - issue #22

Statut : cahier des charges et diagnostics, pas un resultat de benchmark.
Seul un smoke Optuna borne a trois essais par modele est autorise ici ;
aucune optimisation complete, aucun benchmark 10x5 ni test confirmatoire.

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
  Adequation acceptee par Basma le 23/10/2026, avec la limite statistique
  documentee ci-dessous ; aucun seuil universel de fiabilite n'est attribue
  a la spec. `partition.adequacy_confirmed = true`.
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
290 fraudes internes au prix d'un benchmark reduit. Basma accepte le 20/80
avec la limite ci-dessous, sans modifier retrospectivement cette partition.

### Decisions complementaires validees le 23/10/2026

**décidé par Basma**, date : **23/10/2026** (validation explicite dans le chat).

1. `RandomSampler(seed=42)` pour les cinq modeles, execution sequentielle.
   Ce choix respecte la recherche aleatoire du 4.5 ; aucun TPE implicite.
2. `process_wall_clock`, **300 s par essai**, demarrage du processus,
   preparation, fit, prediction et score inclus. Filet global : **10800 s
   (3 h) par etude**, pas pour les cinq etudes reunies. Le superviseur borne
   l'essai par le minimum des 300 s et du temps d'etude restant. Nettoyage
   separe et borne du processus enfant ; pas de simple timeout de thread.
   Un essai interrompu compte parmi les 30 tentatives, etat FAIL et motif
   trial_timeout/study_timeout, sans score invente ni remplacement silencieux.
   Compteurs par modele : attempted, completed, timeout_count,
   timeout_fraction ; alerte si timeout_fraction **strictement > 0,20**.
3. Parmi les maxima de F1 sur validation INTERNE uniquement, retenir le
   **plus petit seuil** ; egalite numerique absolue **1e-12**, sans arrondir
   les scores. Convention de classification : probabilite >= seuil.
4. Provisoire : meilleure moyenne PR-AUC des dix repetitions. Egalite
   numerique au meilleur a 1e-12 pres : Brier moyen minimal, puis latence
   p95 minimale, puis identifiant de modele stable. La latence doit etre
   MESUREE sur **1000 appels unitaires du pipeline complet**, CPU un thread,
   meme machine (4.6), pas deduite des temps batch ci-dessous.
   Tag **provisional**, jamais de promotion automatique champion.
5. Signalement d'incertitude : IC bootstrap 95 % de la **difference appariee**
   sur les **10 moyennes de repetition**, **10000 reechantillonnages** (4.8).
   Si zero appartient a l'IC : **supériorité non démontrée**, pas preuve
   d'equivalence. Le verdict confirmatoire attend Friedman/Wilcoxon/Holm.
   Aucun de ces calculs statistiques n'est execute dans le smoke.

Limite du 20/80 acceptee : AP LogReg mesuree 0,2551854001614933 ; IC95 %
**[0,19923473029601207 ; 0,3202553295288669]** sur **237 fraudes**.
Par decision de Basma, un ecart de PR-AUC **inferieur a environ 0,03** entre
essais Optuna ne suffit pas a les departager : conserver ces essais comme
candidats proches, sans pretendre qu'un ecart minuscule est une amelioration.
C'est une marge de prudence operationnelle, PAS un seuil de significativite
derive de l'IC, ni la tolerance numerique de 1e-12 du benchmark. Ne pas
modifier/arrondir les scores reellement journalises. Le smoke ne selectionne
aucun essai ; l'arbitrage entre configurations proches reste explicite.

Le prevol strict ne comporte plus de valeur obligatoire "a confirmer".
Les regles de seuil, de selection provisoire et de bootstrap sont configurees
pour le futur benchmark ; elles ne sont pas pretendues executees par ce smoke.
Questions P3 et formats : voir [questions_omar_p2.md](questions_omar_p2.md).

### Verifications reelles 1 a 3, 23/10/2026

1. **Chargeur T4 et smoke LogReg.** `validation/fold_data.py:44,47-48`
   calcule 70 % en entiers, trie les dates (mergesort), puis selectionne
   les premiers rangs chronologiques ; `:59` ignore les lignes non retenues.
   Le smoke appelle ce chargeur (`ml/scripts/smoke_fold_logreg.py:132`).
   Une inversion physique detectee : index 100531 = 2019-02-28 23:59:40,
   index 100532 = 2019-02-28 00:02:34 (indexation a partir de zero).
   Les deux sont dans development ; verification des ensembles : **0** ligne
   du development chronologique hors prefixe physique, et **0** dans l'autre
   sens. Aucun mauvais cote a la frontiere development du fait de l'inversion.
2. **Un pli reel**, meme premier pli StratifiedKFold(5, shuffle=True, seed=42)
   de development pour tous les modeles ; chronometrage diagnostique, PAS le
   benchmark officiel sur les 80 % reserves. Preprocessing ajuste sur 726137
   lignes naturelles ; apres sous-echantillonnage 45067 lignes = 4097 fraudes
   + 40970 legitimes ; beta = 0,05674200875297768. Validation naturelle :
   181535 lignes / 1024 fraudes. 76 features float32. Preparation totale
   9,678531500016106 s, dont fit_transform train 5,999439299979713 s et
   transform validation 1,2496732999861706 s. Temps des modeles ci-dessous.
3. **LogReg interne 20/80.** Train naturel 145227 lignes / 1323 fraudes ;
   apres reduction 14553 lignes ; validation 36307 lignes / 237 fraudes,
   beta = 0,09193629086057371, 75 features ajustees sur ce train seulement.
   Derniere date train 2019-03-19 10:45:00 ; premiere validation
   2019-03-19 10:46:46 ; derniere validation 2019-04-05 01:23:52.
   LogReg C=1, lbfgs, max_iter=2000, seed=42 : 38 iterations, sans warning.
   Fit 0,12279019999550655 s ; prediction 0,007202299981145188 s.
   Bootstrap percentile iid par transaction, modele fixe sans reentrainement,
   seed=42, 2000/2000 tirages valides : AP et IC ci-dessus ; ecart-type
   bootstrap 0,03155742684209774 ; largeur IC 0,12102059923285485.
   Ce diagnostic n'integre ni dependance carte/temps ni incertitude du tuning.
   Il ne remplace PAS le bootstrap apparie 10000 tirages du futur benchmark.

Mesures mono-thread : Windows, Intel64 Family 6 Model 140 Stepping 1,
4 coeurs/8 threads, RAM 15,56 Gio ; Python 3.11.17, numpy 2.4.6,
pandas 3.0.6, scikit-learn 1.9.1, XGBoost 3.2.0, MLflow 3.17.1.
Lecture globale limitee aux dates ; labels/features development uniquement.
Aucun avertissement d'entrainement sur les dix chronometrages et la LogReg.
MLflow p2_diagnostics : run 1445ed5bc1be4aaab0b75157b7c9606d, dix enfants.

## Estimation du cout de calcul

**Base : temps MESURES sur le pli reel 45067/181535, pas extrapolation du
smoke 319/800.** Les colonnes leger/haut correspondent a deux configurations
du meme pli ; une mesure par configuration, pas des bornes mathematiques.

| Modele | Fit leger (s) | Prediction legere (s) | Fit haut (s) | Prediction haute (s) |
|---|---:|---:|---:|---:|
| LogisticRegression | 0,180569 | 0,031163 | 0,125019 | 0,010574 |
| RandomForest | 1,753114 | 0,753533 | 148,352455 | 6,139958 |
| XGBoost | 1,351319 | 0,357839 | 9,520448 | 1,529459 |
| Nystroem + LinearSVC | 2,107268 | 0,521600 | 11,245661 | 3,403937 |
| MLPClassifier | 16,250785 | 0,028150 | 38,904893 | 0,197827 |

Leger/haut : LogReg C=0,01/100 (lbfgs, plafond 1000) ; RF 50/300 arbres,
profondeur 3/16, min_samples_leaf 10/1, max_features sqrt/1 ; XGB 50/300,
profondeur 2/8, learning_rate 0,02/0,2, subsample et colsample 0,7/1 ;
Nystroem 64/256 composantes, C=0,01/10, gamma=0,001/1, plafond SVC 3000 ;
MLP (32)/(64,32), alpha=1e-5, learning_rate_init=1e-4, plafond 150,
early stopping : 133/84 iterations. Le SVM inclut deja ses trois sous-plis
de calibration sigmoide et le reajustement interne : ne pas les recompter.
"Haut" signifie capacite couteuse, pas maximum numerique de chaque parametre.

**Benchmark : 5 modeles x 10 repetitions x 5 plis = 250 evaluations.**
Hypothese mono-thread, sequentiel, sans cache de preprocessing :
`T = 250 x preparation + 50 x somme_modele(fit + prediction)`.
Utiliser par modele les minima/maxima OBSERVES des deux configurations,
car meme LogReg haut n'est pas necessairement plus lent que leger.

| Scenario de planification | Bas empirique | Haut empirique |
|---|---:|---:|
| Modeles seuls, une passe | 1162,960 s | 10975,318 s |
| Une passe avec 250 preparations | 3582,593 s (59,7 min) | 13394,951 s (223,2 min) |
| Deux passes completes par evaluation (seuil interne puis reajustement) | 7165,186 s (119,4 min) | 26789,903 s (446,5 min) |

La derniere ligne double explicitement preparation/fit/prediction : scenario
prudent pour les deux ajustements du protocole F1, pas une mesure executee.
Le pli reel mesure est plus grand que le futur pli benchmark : ce dernier
porte sur 726138 lignes, environ 31337 lignes apres reduction dans son train.
Aucun facteur lineaire de changement de taille n'est applique. Ces fourchettes
ne garantissent ni duree minimale ni plafond : convergence, cache, charge RAM,
autres hyperparametres et fits internes peuvent modifier le cout.
Ajouter les entrees/sorties, journalisations, echecs et les 1000 appels
unitaires de latence (cout non encore mesure pour les cinq pipelines).
Les IC et tests statistiques du livrable suivant ne sont pas inclus.

Optuna, a part : 30 x somme des couts de modele observes = 697,776 a
6585,191 s ; avec preparation repetee sur CE pli, 2149,556 a 8036,971 s.
Le vrai train interne Optuna est plus petit (14553 lignes reduites), sans
promesse de temps extrapole. Les 3 h par etude sont un filet, pas une prevision.

Commande smoke uniquement, racine et ml/src dans PYTHONPATH :
`python -B -m benchmark.optuna_smoke --smoke`.
Prevol STRICT, puis connexion MLflow obligatoire avant lecture de donnees ;
trois tentatives par modele (15 au total), meme seed et espaces YAML.
Echantillon de 4000 lignes du train interne Optuna seulement, preprocessing
neuf dans le train de chaque essai, ratio 1:10 et correction beta existants.
Validation diagnostique de 800 lignes / 7 fraudes : aucune selection de modele
ou conclusion de performance sur ces scores. Les labels development servent
au comptage global ; aucune feature ni aucun score du vrai holdout Optuna ou
du benchmark n'est utilise. Aucun mode complet dans ce point d'entree.
Les compteurs reels par modele sont journalises dans MLflow `optuna_smoke`.
Ni code source ni .env transmis ; aucun repli SQLite ni demarrage de Docker.

### Smoke execute le 23/10/2026

`PREFLIGHT PASS : aucun champ a confirmer.` Connexion MLflow PASS avant
lecture : relecture du run, upload/download d'artefact verifies et run de
controle supprime (5e48bd22ebe04a04965d88658f0fb8ce).
Optuna 5.0.0 epingle dans ml/requirements.txt, execution Python 3.11.17.
Ce smoke utilise 4000 lignes / 36 fraudes du train interne Optuna ; son pli
entraine sur 3200 lignes naturelles puis 319 lignes reduites / 29 fraudes.
Validation diagnostique : 800 lignes / 7 fraudes. Beta reel
0,09145380006307159 ; labels/features de calibration charges : **0**.

| Modele | Tentatives | Termines | Timeouts | Fraction | Alerte >20 % |
|---|---:|---:|---:|---:|---|
| logreg | 3 | 3 | 0 | 0 | false |
| rf | 3 | 3 | 0 | 0 | false |
| xgb | 3 | 3 | 0 | 0 | false |
| nystroem_svc | 3 | 3 | 0 | 0 | false |
| mlp | 3 | 3 | 0 | 0 | false |

15 essais COMPLETE, aucune configuration selectionnee, aucun avertissement
d'entrainement. MLflow PASS, run parent **2f37257b60b144be89d1613517311222**,
experience **optuna_smoke**, cinq enfants contenant les compteurs verifies
par relecture et les resumes d'essais. La surveillance du delai est active ;
la terminaison effective et l'alerte >20 % sont aussi testees sur des cas
synthetiques (pas de faux timeout declare pour ce smoke qui en compte zero).
Pas de benchmark 250 evaluations ni de recherche complete de 30 essais.
Le smoke a precede le commit : tag git_commit=6fcc432 et git_dirty=true.
Les sources et configs executees sont ensuite versionnees dans **55ff96d**
(feat(p2): apply validated tuning controls and bounded smoke). Aucun code
source n'a ete envoye au serveur comme artefact pour compenser cet etat local.

### Controles avant commits

Lint : tous les fichiers Python versionnes du perimetre CI ml/ et ml-service/,
plus les nouveaux fichiers de ce travail, sans desactivation de regle.
Formatage limite aux huit fichiers Python P2 modifies ; pas de reformatage P3.
Le lint global incluant les fichiers locaux non suivis signale RUF100 dans
ml/scripts/measure_preprocessing_latency.py:18 (noqa E402 inutilise). Ce script
preexistant, non suivi et hors commit, est laisse intact ; il n'est pas present
dans un checkout CI. Ne pas presenter ce lint local global comme reussi.

Windows : `MLFLOW_SQLALCHEMYSTORE_POOLCLASS=NullPool` dans la seule session
de tests permet la fermeture des connexions SQLite avant suppression des
bases temporaires ; option existante de MLflow, aucun fichier P3 modifie.
`OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `MLFLOW_DISABLE_AGENT_HINT=1`,
`PYTHONDONTWRITEBYTECODE=1`. Tests sans cache pytest (`-p no:cacheprovider`).
Premiere verification verte : pytest ml/tests -v = 164 passed, 2 warnings ;
pytest -v dans ml-service = 21 passed, 1 warning. Warnings conserves : signature
pyfunc MLflow non supportee, strategie SQLAlchemy noload depreciee et
Starlette/httpx deprecie. Aucun filtre d'avertissement ajoute.
L'essai supplementaire `pytest tests/preprocessing` ne collecte aucun test
dans ce dossier local : NON VERIFIE, pas PASS. Les assertions des tests de
configs incompletes sont maintenues avec des fixtures explicitement incompletes
maintenant que les vraies configs sont validees.
Controles relances avant le commit documentaire : Ruff PASS, huit fichiers
Python deja formates, 164 tests ML PASS (2 warnings, 76,31 s), 21 tests
ml-service PASS (1 warning, 0,88 s). Aucun test saute ni assertion supprimee.

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
