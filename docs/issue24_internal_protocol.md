# Protocole interne P2 pour l'issue #24

**Précision postérieure au benchmark**, rédigée le 5 novembre 2026. La
spécification §4.2 définit trois zones chronologiques ~70/15/15. Le §4.10
ne précise pas comment comparer deux calibrateurs ni choisir alpha sans réutiliser
les mêmes observations. Les fractions internes ci-dessous sont une décision
d'implémentation, non une règle préenregistrée avant le benchmark.

1. `development` (70 %) : ajustement du preprocessing sur toutes les lignes
   naturelles, sous-échantillonnage 1 fraude / 10 légitimes du train seulement,
   ajustement du XGBoost candidat avec `configs/best_params.json`, beta mesuré.
   Aucune ligne de calibration ne sert à cet ajustement.
2. `probability_calibration` (15 %) : première moitié chronologique pour
   ajuster séparément Platt (sigmoïde) et isotonique sur les probabilités déjà
   corrigées de l'a priori ; seconde moitié pour comparer les Brier. Le
   calibrateur choisi n'est pas réajusté sur la moitié de comparaison.
3. `conformal_calibration` (15 %) : première moitié chronologique pour les
   quantiles Mondrian par classe ; quart suivant pour sélectionner le plus
   petit alpha parmi 0,01, 0,02, 0,03, 0,05, 0,10 avec revue <= 2 % ; dernier quart
   déjà consulté, désormais exploratoire après les précisions post hoc, pour
   rapporter couverture par classe, revue, automatisation et erreur automatique.
   Aucun quantile n'est ajusté sur les deux derniers quarts. Les frontières
   temporelles égales sont déplacées à droite pour garder les mêmes dates ensemble.

Le quantile par classe suit l'ordre statistique `ceil((n_c+1)*(1-alpha))` sur
les scores de non-conformité triés ; si ce rang dépasse `n_c`, aucun quantile
fini n'est disponible pour cet alpha et cette classe : l'alpha est déclaré
inapplicable, sans seuil arbitraire. Les tailles par classe et les limites de
couverture doivent figurer dans le rapport.

La sélection d'alpha utilise uniquement le taux de revue sur le quart de
sélection, sans étiquette ; les couvertures de ce quart ne fondent aucune
garantie. Le dernier quart n'ajuste ni les quantiles ni alpha, mais il a déjà
été consulté : ses mesures après les changements post hoc sont exploratoires.
Il ne constitue donc pas une nouvelle confirmation indépendante ni le test final. Si
aucun alpha ne respecte la capacité, aucun modèle n'est empaqueté pour le
service. XGBoost reste le candidat provisoire retenu après application du
seuil d’effet post hoc de l’issue #23, sans promotion champion. Aucune lecture
du jeu de test final dans ce workflow.

## Exécution et lecture des résultats

Depuis la racine du dépôt, la commande suivante est réservée au lancement
réel ultérieurement autorisé. Le dossier de sortie doit être neuf.

```console
python -m ml.src.final.train_final --source data/raw/fraudTrain.csv --best-params configs/best_params.json --output-dir ../p2-final-candidate --journal ../p2-final-audit/launches.jsonl
```

La CLI vérifie le SHA-256 du handoff #22. La seed est 42. En cas d'égalité
exacte de Brier, l'ordre alphabétique des méthodes départage les calibrateurs.
Le run MLflow de l'expérience `p2_final_calibration` porte le statut
`provisional`, les empreintes des paramètres et de la source, et le commit.
`--local-report-only` permet les tests synthétiques hors réseau.
Le dossier contient le rapport Markdown, le JSON détaillé, la courbe de
fiabilité et la courbe de revue. Si la capacité est satisfaite,
`candidate_model.joblib` contient le pyfunc avec son preprocessing,
sa correction de l'a priori, son calibrateur et ses deux seuils mesurés.
Le rechargement requiert le code du projet et son environnement Python.
Aucun alias de production n'est créé.

Les couvertures observées restent soumises à la dérive temporelle et aux
effectifs par classe. La garantie théorique suppose des scores échangeables
dans chaque classe à alpha fixé. Les mesures du dernier quart documentent
le comportement observé après choix d'alpha.


## Vérification avant lancement — 7 novembre 2026

Ces précisions interviennent après observation du benchmark. Elles ne changent
ni les paramètres figés, ni le candidat provisoire, ni les zones externes.
La spec §4.10 demande le plus petit alpha respectant la capacité ; le « par
exemple <= 2 % » de la spec devient ici la capacité explicitement demandée par
Basma. Le premier lancement utilisait 0,01 / 0,05 / 0,10 ; D44 étend post hoc
la grille à 0,01 / 0,02 / 0,03 / 0,05 / 0,10. La courbe est incluse
dans le README du dossier de sortie. La comparaison des Brier se fait hors
ajustement, mais la mesure sur la moitié de choix peut subir l'optimisme de
sélection : Brier et ECE sont aussi rapportés sur le quart conforme final.
L'ECE reprend les 10 bins uniformes pondérés par effectif du benchmark (§4.6),
et ne sert pas à choisir alpha. La fiabilité avant/après reste mesurée sur la
moitié de comparaison des calibrateurs, explicitement identifiée comme telle.

Lecture effectuée pour ce contrôle : seule `trans_date_trans_time` de la source
autorisée. Aucun label ni feature des zones réservées n'a été chargé.

| Sous-partie | Lignes, calculées à partir des dates |
|---|---:|
| development | 907672 |
| calibration : ajustement | 97250 |
| calibration : comparaison Brier | 97251 |
| conforme : quantiles | 97251 |
| conforme : choix alpha | 48625 |
| conforme : évaluation | 48626 |

Les effectifs de fraudes ne peuvent pas être déduits des dates. Pour un quantile
fini, chacune des deux classes du bloc **quantiles** doit compter au moins 99
observations à alpha=0,01, 19 à 0,05 et 9 à 0,10. Ces minima assurent seulement
l'existence du rang, pas la précision des couvertures estimées. L'alternative
est de vérifier les effectifs par classe lors du lancement autorisé ; toute
valeur impossible est signalée, sans fusionner les sous-zones ni changer les
fractions après observation. Une classe absente du bloc d'évaluation entraîne
une erreur explicite, plutôt qu'une couverture inventée.

Le seuil d’effet de 0,01 PR-AUC a été décidé par Basma le 9 novembre 2026,
**post hoc**, puis appliqué dans #23 : le statut est `provisional`. Friedman
p=4.328422607120966e-08, W=1 ; comparaison XGBoost moins RF : p Holm=0.01953125,
différence moyenne=0.02592986057170187, rang-bisérial=+1, IC bootstrap 95 %
[0.023695277277932792 ; 0.028121637315621423]. La borne inférieure dépasse
le seuil d’effet 0,01 : XGBoost est retenu provisoirement, sans départage
Brier/latence ni promotion champion. Le test final a ensuite été consommé le
10 novembre ; voir la revue #24. Aucune sélection ou modification du candidat
ne doit s’appuyer sur ce jeu. Omar donne ensuite un accord conditionnel pour D48, dont l’exécution reste interdite avant vérification des préconditions, le 12 novembre 2026 ;
voir `decisions.md`. Aucune exécution n’est autorisée avant merge, CI verte et
vérification de l’intégration B. La seconde mesure est post hoc, non indépendante.

## Journal obligatoire des lancements

`--journal` désigne un JSONL **hors dépôt**, à conserver au même chemin pour
tous les lancements. Une entrée `launch_started` contient les alpha, les
fractions externes et internes, les paramètres XGBoost et leur hash, la seed,
le ratio de sous-échantillonnage et la capacité. Tout changement depuis le
dernier lancement est refusé **avant lecture** sauf si une décision motivée
est fournie par `--protocol-change-reason "..."`. Cette décision est alors
inscrite dans `protocol_change_acknowledged` avant le nouveau lancement.
Le verrou interdit deux lancements simultanés sur le même journal. Après une
interruption brutale, un verrou restant doit être examiné manuellement.

Le chargement réel est volontairement explicite : les trois zones de la source
train sont chargées, avec leurs labels/features, uniquement lors du lancement
ultérieurement autorisé. `source_read_started` journalise les zones et colonnes
avant tout accès (y compris le hash), et `source_read_completed` enregistre
leurs effectifs et le hash source. Il ne faut pas confondre lecture en mémoire
et ajustement : seul development ajuste le preprocessing et XGBoost. L'alpha
est fixé avant calcul des prédictions/métriques du quart d'évaluation.
La garde de chemin s'applique avant toute ouverture du fichier ; aucun chemin
de test final n'est accepté. Le journal ne contient aucune ligne de données.
Les fins normales/erreurs sont enregistrées ; le run et le snapshot du journal
sont liés dans MLflow. La copie MLflow est prise avant la fermeture du run ;
le journal local fait foi pour son événement final `launch_completed`.

Ce journal local n'est pas un mécanisme anti-altération : utiliser un autre
fichier ou supprimer son historique annule sa garantie de comparaison. Un
changement motivé reste une déviation documentée, pas une validation scientifique.
Aucun lancement réel n'a été effectué pour cette vérification.


## D44 — extension post hoc du 10 novembre 2026

La capacité reste 2 %. La grille étendue et la règle de déplacement des frontières
font partie de l'identité du protocole ; le journal exige une raison explicite
avant toute nouvelle lecture. Le choix utilise uniquement le taux de revue du
bloc de choix, sans labels. Le bloc d'évaluation a déjà été observé : ses
nouveaux résultats sont exploratoires. Le rapport compare la couverture fraude
au plancher `(1-alpha)-0.02` et donne l'erreur automatique pour chaque alpha.
Les tests binomiaux utilisent une famille Bonferroni de cinq comparaisons.

## Intégration de la mesure finale

La [PR #102](https://github.com/reda253/fintech-mlops-lsi/pull/102) concerne le
pipeline et le serving. Ce lien ne présume pas du contenu déployé. Omar et Reda
ont reçu la décision d’Omar pour l’option B : le Job appelle la CLI, puis
`step_evaluate` consomme ses artefacts vérifiés sans lire le test final.
D48 bénéficie d’un accord conditionnel ; son exécution reste interdite avant vérification des préconditions ; ses
préconditions de merge, de CI et d’intégration restent à vérifier.
