# Protocole descriptif d'audit d'équité — D48

Préparation du 20 novembre 2026, avant la seconde mesure. D48 est une seconde
mesure post hoc, non indépendante du test consommé le 10 novembre. Ce document
ne constitue pas une autorisation de lancement. Le candidat D44, son
préprocesseur, son calibrateur, beta, ses paramètres, alpha=0.02 et ses quantiles
restent figés. Aucune sélection, correction de seuil ou promotion ne découle
de l'audit. Référence : spécification §4.3 et décisions D44/D48.

## Groupes fixés

`gender` : catégories attendues `F` et `M` (aucun nouveau comptage sur le test
final n'a été réalisé pour ce document). Une valeur manquante ou inattendue
doit être signalée, jamais recodée silencieusement.

L'âge est le nombre d'années révolues à la date de transaction : année de
transaction moins année de naissance, moins un si l'anniversaire n'est pas
encore passé. Réutiliser les formats et la convention temporelle existants.
Les âges invalides hors [0,120] sont refusés.

Les bornes sont celles de l'EDA et de `evaluate_final_candidate.py`, et non
les exemples alternatifs <25/25-34 :

| Libellé existant `age_group` | Intervalle | Âges entiers |
|---|---|---|
| 0-25 | [0,25] | 0 à 25 |
| 26-35 | ]25,35] | 26 à 35 |
| 36-45 | ]35,45] | 36 à 45 |
| 46-55 | ]45,55] | 46 à 55 |
| 56-65 | ]55,65] | 56 à 65 |
| 66-120 | ]65,120] | 66 à 120 |

`age_band` désigne conceptuellement cette partition ; le nom sérialisé reste
`age_group` pour préserver le format existant.

## Décisions et métriques

Pour une transaction i, Y_i est son étiquette réelle et S_i son ensemble de
prédiction. B_i=1 si S_i=[1], R_i=1 si S_i=[] ou [0,1]. S_i=[0] est approuvé.
Pour chaque groupe g, I_g est l'ensemble de ses transactions :

1. N_g=|I_g|, N_pos,g=sum(Y_i), N_neg,g=N_g-N_pos,g.
2. Fraudes bloquées automatiquement : sum(Y_i B_i)/N_pos,g.
3. Fraudes interceptées : sum(Y_i (B_i+R_i))/N_pos,g. Blocage et revue sont disjoints.
4. Légitimes bloqués automatiquement : sum((1-Y_i) B_i)/N_neg,g.
5. Revue humaine : sum(R_i)/N_g.

Un dénominateur nul donne `N/A (undefined)` dans le rapport et `null` dans le
JSON ; jamais un zéro artificiel. Les groupes vides et sans fraude sont
explicitement signalés. Les métriques ponctuelles à 0.5 restent secondaires,
avec suffixe `_point_prediction` ; elles ne décrivent pas les décisions du service.

**Règle des petits groupes et dénominateurs nuls** :

Pour chaque métrique, le dénominateur pertinent est publié : nombre de fraudes, de légitimes ou de transactions. Un dénominateur nul entraîne la mention « non interprétable — métrique indéfinie ». Aucun minimum numérique d’effectif n’est actuellement approuvé. Les autres estimations restent descriptives et sont accompagnées de leurs effectifs, IC et nombres de réplications valides ; un faible effectif ou un intervalle large interdit de conclure à une absence de disparité. Tout critère supplémentaire d’effectif minimal ou de précision devra être approuvé et consigné avant D48, sans être choisi après observation des résultats.

## Bootstrap et interprétation

Bootstrap non paramétrique par transaction : 10 000 tirages avec remise,
seed=42, intervalles percentile 95 % (2.5 et 97.5). Les mêmes indices et poids
sont utilisés pour les groupes et leurs différences. Les tirages où une
métrique est indéfinie sont exclus de son intervalle ; rapporter le nombre
de tirages valides, et N/A si aucun ne l'est.

Ces intervalles supposent des transactions indépendantes, bien qu'une même
carte (`cc_num`) produise plusieurs transactions. La dépendance par carte et
la dérive temporelle ne sont pas corrigées. Aucun identifiant de carte ni
date de naissance exacte ne doit apparaître dans les sorties d'audit.

Présenter les effectifs, les taux et leurs IC par groupe. Pour les écarts,
présenter les différences absolues de chaque paire de groupes, en points de
pourcentage, et leur IC obtenu avec les mêmes tirages. Aucun groupe de
référence privilégié et aucun seuil binaire « équitable/non équitable » ne
sont définis. Les petits effectifs, intervalles larges et comparaisons
multiples limitent l'interprétation descriptive.

**Précision sur les écarts et comparaisons multiples** :

Aucun seuil d’écart acceptable entre groupes n’est fixé. Les IC sont ponctuels, sans correction pour comparaisons multiples, et ne constituent pas un test global d’équité. Aucun verdict de conformité ou d’absence de discrimination ne sera déduit de cet audit seul.

## Précontrôle sans lancement

La PR #120 est mergée sur `main` (`c5d9881`). Les responsabilités sont séparées :

1. `ml/scripts/d48_preflight.py` conserve les préconditions locales de #120 :
   source et modèle figés, référence D44, mesure précédente, protocole,
   autorisation, journal, source de latence et sortie. Lui seul effectue ces
   contrôles avant l'évaluateur. Son calcul du hash source lit les octets du
   fichier final : ne pas l'exécuter sur le réel sans instruction explicite.
2. `ml/fairness/preflight_d48.py` contrôle uniquement le Registry : un manifeste
   de provenance du candidat avec `model_sha256` et `alpha`, la version/alias,
   le tag `source_model_sha256`, la signature pyfunc et alpha=0.02. Il n'accepte
   plus `--source`, `--journal`, `--authorization`, `--protocol-file`,
   `--output-dir`, `--reason` ni `--force`. Il ne lit ni le test final ni le
   journal et ne prédit rien. Le chargement peut alimenter le cache MLflow local.
3. `ml/fairness/audit.py` analyse seulement les prédictions déjà sauvegardées et
   leurs artefacts vérifiés ; il contrôle le journal de complétion sans réutiliser
   l'autorisation consommée. Il ne lit pas la source finale et ne charge pas le modèle.

Le contrôle reste une photographie ; l'évaluateur refait ses propres contrôles
et réserve sous verrou. Une nouvelle mesure exige une nouvelle décision
approuvée, jamais un changement de motif ou un contournement de la garde.

Le manifeste candidat est distinct de `authorization-d48.json` : le fichier
d'autorisation conserve ses six champs officiels, sans ajout obligatoire de
paramètres Registry. Le tag Registry `protocol_sha256` décrit D44 et ne remplace
pas l'empreinte du protocole D48 ; il n'est pas comparé par le contrôle Registry.

La vérification du tag `source_model_sha256` établit la provenance déclarée,
pas à elle seule l'identité du modèle chargé ; conserver le contrôle
`model_binding.py` lors de l'intégration officielle.

## Arbitrage validé par Basma — 20 novembre 2026

Options 1-A et 2-A : l'évaluateur existant reste l'unique lecteur de la source
finale et l'unique exécuteur d'inférence. Le schéma minimal `predictions.csv`
est conservé ; aucun `trans_num`, âge exact ou nouveau fichier de prédictions
n'est introduit par l'audit. Les comparaisons d'âge sont toutes les paires par
défaut ; `--age-reference` est une option descriptive explicite, sans effet sur
le modèle ni sur alpha.

L'analyse exige les empreintes du dossier d'évaluation complet : métriques,
prédictions et historique. Une mesure réelle exige D48, les empreintes source
et modèle approuvées, alpha=0.02, les métadonnées de version du candidat et le
run publié. Le journal central est lu via `--journal`, hors dépôt : toute
entrée d'évaluation D47 est refusée, quel que soit son statut. Un achèvement
D48 lié aux mêmes empreintes source/modèle/protocole est exigé. Le fichier
source final n'est jamais relu par l'analyse.
L'autorisation consommée n'est pas réutilisée : recalculer les rapports depuis
les prédictions ne constitue pas une nouvelle mesure. Le manifeste conserve
le hash du protocole de l'évaluation, sans prétendre que ce nouveau document
ou le protocole courant était déjà celui du lancement historique.

Le champ `git_commit` de l'analyse est fourni par `--code-revision` : il doit
être la révision complète courante ; aucune commande Git n'est exécutée.
Les tags du candidat consignés dans ce manifeste proviennent des métadonnées
fournies, pas d'une consultation en direct du registry. Si la publication
MLflow de l'analyse échoue, les résultats locaux et leur manifeste restent
disponibles ; relancer l'analyse dans un dossier neuf ne réinfère rien.

## Alignement sur Option B mergée (#117)

La PR [#117](https://github.com/reda253/fintech-mlops-lsi/pull/117), commit
`bc30b938cf0bbb86de3e6c6c8fca61cc85dc35d5`, est mergée. Le flux est :
`evaluate_final_candidate.py` → artefacts vérifiés par le lecteur #117 →
`audit.py` → `step_evaluate` (consommation des artefacts d'évaluation).
L'audit descriptif est complémentaire : #117 ne consomme pas ses quatre sorties.

`ml.src.evaluation.final_artifacts` centralise les deux SHA-256 approuvés et
fournit `load_verified_final_evaluation`. L'audit l'appelle avec alpha attendu
0.02 avant ses calculs : manifeste complet, bornes des métriques, effectifs,
prédictions et `previous_evaluation/` sont vérifiés. Les tests passent par le
même lecteur, sans branche de contournement pour les artefacts synthétiques.
Les scripts fairness ne redéfinissent pas les empreintes approuvées.

`artifact_manifest.json` appartient à l'évaluateur et reste intact.
`manifest_d48.json` décrit uniquement l'audit, dans un dossier externe neuf
avec `fairness_metrics.json`, `fairness_report.md` et les huit figures.
Il ne remplace jamais le manifeste de l'évaluation. `--evaluation-dir` désigne
le dossier de l'évaluateur ; `--candidate-model` est le joblib figé utilisé par
le pipeline pour son contrôle de liaison. Aucun de ces arguments ne désigne
le dossier de l'audit. L'historique `previous_evaluation/` demeure inchangé.
