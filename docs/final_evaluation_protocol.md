# Protocole d’évaluation finale du candidat D44

Le script `ml/scripts/evaluate_final_candidate.py` recharge le candidat existant,
contrôle son SHA-256 fourni, ses deux seuils conformes et alpha = 0,02 face au
rapport D44. Il n'effectue aucun fit et ne promeut aucun modèle.
Le test final a été consommé le 10 novembre 2026 ; aucune nouvelle évaluation
de ce jeu ne doit être lancée sans décision explicite de l'équipe.
Le journal central hors dépôt est fourni par `--journal`, sinon par
`FINAL_EVALUATION_JOURNAL`. Il n’existe aucun chemin implicite lié à un poste.
Son parent doit exister : un montage absent n’est jamais créé automatiquement.
La réservation lie décision, SHA-256 de la source, du modèle et du texte du
protocole approuvé, avant ouverture de la source. `--reason` explique le lancement
mais n’autorise pas à lui seul une relance. Une autorisation consommée ne peut
être rétablie en changeant le motif ou le libellé de révision. Le hash réellement
lu est ensuite comparé au hash déclaré, avant toute inférence.

## Métriques et incertitude

PR-AUC (average precision), ROC-AUC, accuracy, précision, rappel, F1, MCC,
Brier, log-loss et ECE (10 classes uniformes), ainsi que couverture par classe,
revue, automatisation et erreur parmi les décisions automatiques sont calculés.
Les ensembles vides et ambigus sont comptés en revue. Les métriques de classe
secondaires portent le suffixe `_point_prediction` et utilisent le seuil 0,5 ; ce seuil
ne démontre pas la conformité à la règle du seuil F1 optimisé par pli en §4.6.
Le seuil du modèle final pour cet usage reste à clarifier sans utiliser le test.

Les IC à 95 % sont des percentiles bootstrap : **10 000 rééchantillonnages avec
remise, seed 42, unité transaction**, avec un même tirage pour toutes les
mesures et les groupes. Les tirages sans dénominateur sont exclus de l'IC
concerné et leur nombre est rapporté ; une mesure sans aucun tirage valide vaut
`null`. Les transactions d'une carte peuvent être dépendantes : le bootstrap
transactionnel iid ne tient pas compte de cette dépendance ni d'une dérive.
Le coût du calcul sur le jeu final n'a pas été mesuré. La latence locale utilise
20 préchauffages et 1 000 appels unitaires, un thread, sur au plus 100 lignes
de développement échantillonnées avec seed 42, jamais issues des calibrations
ni du test final. Les dates seules peuvent être lues hors développement. Un
seul appel à la mesure est effectué avant lecture du test. Ses IC rééchantillonnent
les appels, et non les transactions. Elle n'inclut ni réseau ni conteneur.

L'audit par genre et âge utilise les limites exactes de l'EDA : 0–25, 26–35,
36–45, 46–55, 56–65 et 66–120 ans. Les effectifs et effectifs de fraudes sont
indiqués. Les métriques principales sont les fraudes bloquées automatiquement
(ensemble `[1]`), les fraudes interceptées (blocage ou revue), les légitimes
bloqués automatiquement et la revue. `[0]` approuve ; `[]` et `[0,1]` sont en
revue. Les métriques au seuil 0,5 sont secondaires. Sans dénominateur, la mesure
et son IC sont indéfinis (`null`), jamais remplacés par zéro.

## Portes et ambiguïtés

Les couvertures **de chaque classe** sont comparées à `(1-alpha)-0,02`, la revue
à `<= 2 %`, et la latence locale p95 à `< 50 ms`. La non-régression reste
`UNVERIFIED` sans référence fournie explicitement : champion moins 0,01, ou
baseline logistique pour la première exécution (§5.4). Le bon comparateur et
l'utilisation de mesures sur des jeux comparables doivent être validés par
l'équipe. Le test registry sur 100 transactions reste `UNVERIFIED` ; aucune
porte manquante ne provoque de promotion. La remarque initiale de revue
concernait une porte P3 à 3 % ; son propriétaire doit confirmer l’alignement
sur la version effectivement déployée. Ces corrections ne modifient aucune
porte du pipeline P3.

## Persistance et publication

Les prédictions sont sauvegardées immédiatement après inférence, **avant les
métriques, le bootstrap et les rapports** : écriture temporaire dans le même
dossier, `flush`/`fsync`, puis remplacement atomique. Un manifeste intermédiaire
contient leur SHA-256 même si le bootstrap échoue. Un échec pendant le renommage
ne publie aucun CSV partiel ; la réservation demeure et interdit une reprise
automatique de l’inférence.

Les agrégats, IC, rapport et le manifeste SHA-256 final sont écrits hors dépôt avant
la publication MLflow. Les empreintes du modèle, de la source, de la référence,
des scripts et des artefacts sont enregistrées. Les métriques MLflow
`group_N_*` correspondent à l’élément N du tableau `fairness` du JSON.
La révision du code est une
valeur fournie par l'utilisateur via `--code-revision` ; le script ne lance
aucune commande Git. Le fichier local `predictions.csv` contient les étiquettes, probabilités, indicateurs des ensembles, genre et tranche d’âge ; aucun identifiant ni date de naissance exacte. Son hash figure dans les métriques ; il reste hors dépôt et n'est pas inclus dans la publication MLflow des agrégats. Protéger ce fichier et ne pas le partager sans autorisation.

Si la publication échoue, `mlflow_status.json` conserve le statut et le run ID
lorsqu'il a pu être créé. Après rétablissement de MLflow, exécuter uniquement :

```bat
python ml\scripts\evaluate_final_candidate.py --republish "CHEMIN_DU_DOSSIER_DE_RESULTATS"
```

Cette commande vérifie les empreintes des fichiers sauvegardés et ne reçoit ni
ne relit le jeu final. Un arrêt avant sauvegarde complète nécessite une revue
manuelle ; ne pas changer le chemin du journal pour relancer automatiquement.


## Autorisation et précontrôles avant toute nouvelle lecture

**D48 ne peut pas encore être exécutée ; Omar a donné un accord conditionnel**, accord transmis par Basma
le 12 novembre 2026 et consigné dans `docs/decisions.md`. Option **B** retenue :
la CLI est le seul lecteur final ; le pipeline consomme les artefacts vérifiés.
Cette seconde mesure est **post hoc, non indépendante**. Le code corrigé doit
être mergé, la CI verte et l’intégration B vérifiée avant toute exécution.
Ces préconditions ne sont pas attestées par ce document. Aucune relance réelle
n’a été effectuée dans cette préparation ; les tests restent synthétiques.

En mode final, tous les arguments manquants sont affichés ensemble :
`--confirm-final-test`, `--journal` (ou la variable), `--model-sha256`,
`--source-sha256`, `--decision-id`, `--protocol-revision`, `--protocol-file`,
`--authorization`, `--reason`, `--latency-source`.
`--protocol-file` désigne le texte approuvé exact (toute modification change
son SHA-256). `--authorization` désigne un JSON hors dépôt fourni après accord :
`approved: true`, `decision_id`, `source_sha256`, `model_sha256`,
`protocol_sha256`, `journal_sha256`. Ce dernier fige l’état du journal examiné
lors de l’autorisation. Aucun de ces documents d’accord n’est fabriqué par le
script ; le statut déclaré n’est pas une signature cryptographique de l’équipe.

Les fichiers du modèle et de la référence, leurs empreintes et seuils figés,
le protocole et son autorisation, l’historique du journal, la frame de latence
(provenant du développement, validée par le préprocesseur figé), le dossier
neuf hors dépôt, l’espace libre et les droits d’écriture sont vérifiés avant
ouverture de la source finale. La réserve disque est conservatrice (au moins
1 Mio ou trois fois la taille du CSV source), pas une nouvelle porte métier.
La vérification de taille utilise les métadonnées du fichier, pas ses lignes.

Le journal est obligatoire, non vide, JSONL complet terminé par un saut de ligne.
D48 exige aussi la paire historique du 10 novembre : entrée `started` avec
le modèle `aa1565caf7fed3af833a5613fd76416b6489c9a9f31ee8c523d65e5d9113da33`,
suivie de `completed` avec la source
`7e50d0ce13f08b45ed1740127fe56f9c90c8eeec37a11288a372afcc61efe3b3`.
Cela reconnaît le format ancien ; il ne reconstitue ni l’auteur ni la commande
absents de cette trace. Les nouvelles entrées sont chaînées par empreinte.
Une entrée `completed` consomme la décision ; une réservation sans fin reste
bloquante, même pour une copie de source ou une révision renommée. Une nouvelle
autorisation exige une autre décision approuvée. Les entrées `reserved`,
`predictions_saved` et `completed` prennent le même verrou exclusif.

Le contrôle protège contre les accidents et modifications non reconnues ; il
ne protège pas contre une édition volontaire du journal ET de l’autorisation.
Un journal supprimé ne doit jamais être recréé pour contourner le contrôle.

### Récupération d’un verrou ou d’un lancement interrompu

1. Arrêter les tentatives ; vérifier le PID, l’heure du verrou et l’absence de
   tout processus ou Job encore actif, y compris sur un volume partagé.
2. Sauvegarder journal, verrou, sortie et manifestes hors dépôt ; vérifier les
   empreintes contre les sauvegardes et l’autorisation approuvée.
3. Après accord humain, archiver explicitement le verrou abandonné. Le script
   ne le supprime jamais automatiquement et ne modifie pas l’historique.
4. Une réservation incomplète reste bloquante : exploiter les prédictions déjà
   sauvées hors ligne si elles existent, sans rouvrir la source. Une nouvelle
   inférence nécessite une revue et une nouvelle autorisation explicite ; ne
   pas effacer ni réécrire une réservation pour obtenir une reprise silencieuse.

### Une seule évaluation officielle : option B décidée par Omar

Voir la [PR #102](https://github.com/reda253/fintech-mlops-lsi/pull/102), sans
présumer de sa version déployée. Le Job appelle la CLI une seule fois ;
`step_evaluate` consomme les agrégats sauvegardés, les portes et l’empreinte du
candidat, sans lire le jeu final. `run.py` ne doit pas charger `--test-path`
pour cette mesure. Les métriques sont partagées via `final_metrics.py`.
Le journal doit être monté de façon persistante et être accessible à l’utilisateur
du Job. Les prédictions doivent figurer dans le manifeste vérifié.

L’adaptation est à réaliser par Omar puis à tester avant D48 : artefact absent,
empreinte du candidat incorrecte, manifeste altéré et prédictions modifiées
font échouer le pipeline, sans lecture de la source finale. Le lancement D48
attend le merge, les tests et la CI verts, puis la confirmation de cette intégration.
Il ne déclenche aucune promotion.

### Préparation de la seconde mesure, sans exécution

Conserver hors dépôt, sans écraser les originaux : résultats du 10 novembre
(rapport et métriques), dossier candidat D44 avec le joblib et sa référence,
journal original et sa copie vérifiée. Consigner les SHA-256 de ces sauvegardes.
Le futur rapport doit conserver les résultats du 10 novembre et distinguer
explicitement la seconde mesure post hoc, non indépendante.

Après confirmation des préconditions, figer le texte approuvé et établir
l’autorisation liée aux empreintes du modèle, de la source, du protocole et du
journal examiné. Ne pas créer une nouvelle autorisation simplement pour faire
passer une garde. Utiliser le journal original et un dossier de sortie neuf.
Aucune lecture du jeu final n’est nécessaire pour préparer ces éléments.


### Conservation du premier résultat dans D48

`--previous-evaluation` désigne le dossier hors dépôt contenant
`final_metrics.json` et `final_report.md` du 10 novembre. Il est obligatoire
pour D48. Le contrôle intervient avant la réservation et toute lecture du jeu
final : scope, empreintes du modèle/de la source et alpha doivent correspondre.
Un fichier absent, incohérent ou illisible fait échouer le lancement.
Les effectifs doivent être des entiers JSON (ni booléens, chaînes ou fractions) :
`n_transactions > 0` et `0 <= fraud_count <= n_transactions`. Les compteurs
par classe et de couverture, s’ils sont présents, doivent être entiers,
non négatifs et cohérents avec ces totaux. Aucune valeur numérique `NaN` ou
infinie n’est admise, y compris dans les agrégats supplémentaires imbriqués.
Les métriques légitimement indéfinies restent `null`, sans conversion en zéro.
Tous ces rejets interviennent avant réservation et avant lecture finale.

Le générateur conserve les octets exacts des deux fichiers dans
`previous_evaluation/` du **nouveau** dossier. Les originaux ne sont pas modifiés.
Le rapport affiche les métriques du 10 novembre et celles de la seconde mesure
séparément, avec « Seconde mesure post hoc, non indépendante ». Cette comparaison
est descriptive ; elle ne sert ni à sélectionner ni à régler un candidat.
Le JSON contient `measurement.number = 2`, `post_hoc = true`, `independent = false`
et les agrégats historiques. Aucun ancien IC n’est reconstruit ou inventé.

Les copies historiques et leurs SHA-256 entrent dans le manifeste. Elles sont
vérifiées avant publication et jointes dans MLflow sous `previous_evaluation/`,
avec les tags de seconde mesure. `--republish` utilise exclusivement les copies
du nouveau dossier : ni les originaux ni le jeu final ne sont nécessaires.
La CLI refuse une publication D48 sans historique. Les changements ne lancent
aucune mesure et ne lèvent pas les préconditions de merge/CI/intégration B.

Argument supplémentaire à ajouter à la commande D48 **après** confirmation de
ces préconditions (exemple Windows, chemin à adapter au volume du Job) :

```bat
--previous-evaluation "CHEMIN_VERS_LE_PREMIER_DOSSIER_DE_RESULTATS"
```

### Latence : chemin de montage du Job

`--latency-source` est contrôlé par `guard_training_source` : le chemin résolu
est obligatoirement terminé par `data/raw/fraudTrain.csv` (comparaison insensible
à la casse). Dans le Job, monter le fichier de développement complet à
`/data/raw/fraudTrain.csv` et passer ce chemin. `/data/fraudTrain.csv` est refusé.
La première passe lit seulement les dates ; les features de latence proviennent
des lignes development, sans labels de calibration. Vérifier le montage avant
l’exécution réelle. La CLI manuelle suit les mêmes règles ; l’intégration du Job
et le choix des volumes restent à vérifier par Omar avant D48.

Les probabilités utilisent `batch_probabilities` si disponible : la correction
beta et la calibration de premier niveau sont ainsi appliquées par le wrapper.
Les anciens candidats avec calibration déjà imbriquée conservent leur chemin.
Sans méthode batch, un wrapper avec correction/calibrateur externes est refusé.
Le manifeste final porte `status: complete` ; métriques, équité, bootstrap et
rapport sont écrits atomiquement avant publication.

Le code final refuse explicitement D47, identifiant réservé à Auth. Toute ancienne
entrée d’autorisation D47 pour l’évaluation est caduque : D48 exige une nouvelle
autorisation liée au texte de protocole et au journal courants. Une réservation
D47 existante dans ce journal bloque D48 et nécessite une revue humaine ; aucune
entrée historique ne doit être supprimée pour contourner ce contrôle. La nouvelle
autorisation doit rester non approuvée tant que les préconditions de merge, CI,
intégration B et validation de l’équipe ne sont pas satisfaites.
