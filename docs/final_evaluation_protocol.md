# Protocole d’évaluation finale du candidat D44

Le script `ml/scripts/evaluate_final_candidate.py` recharge le candidat existant,
contrôle son SHA-256 fourni, ses deux seuils conformes et alpha = 0,02 face au
rapport D44. Il n'effectue aucun fit et ne promeut aucun modèle.
Le test final a été consommé le 10 novembre 2026 ; aucune nouvelle évaluation
de ce jeu ne doit être lancée sans décision explicite de l'équipe.
Le journal central hors dépôt compare le SHA-256 déclaré avant la lecture : une
répétition exige `--reason`, enregistrée avant ouverture de la source. Le hash
calculé est ensuite vérifié avant l'analyse. Le contrôle ne protège pas contre
la suppression du journal ou une empreinte déclarée incorrecte.

## Métriques et incertitude

PR-AUC (average precision), ROC-AUC, accuracy, précision, rappel, F1, MCC,
Brier, log-loss et ECE (10 classes uniformes), ainsi que couverture par classe,
revue, automatisation et erreur parmi les décisions automatiques sont calculés.
Les ensembles vides et ambigus sont comptés en revue. Les métriques de classe
utilisent le seuil ponctuel 0,5 déjà utilisé par `FraudDetectorModel` ; ce seuil
ne démontre pas la conformité à la règle du seuil F1 optimisé par pli en §4.6.
Le seuil du modèle final pour cet usage reste à clarifier sans utiliser le test.

Les IC à 95 % sont des percentiles bootstrap : **10 000 rééchantillonnages avec
remise, seed 42, unité transaction**, avec un même tirage pour toutes les
mesures et les groupes. Les tirages sans dénominateur sont exclus de l'IC
concerné et leur nombre est rapporté ; une mesure sans aucun tirage valide vaut
`null`. Les transactions d'une carte peuvent être dépendantes : le bootstrap
transactionnel iid ne tient pas compte de cette dépendance ni d'une dérive.
Le coût du calcul sur le jeu final n'a pas été mesuré. La latence locale utilise
20 préchauffages et 1 000 appels unitaires, un thread ; ses IC rééchantillonnent
les appels, et non les transactions. Elle n'inclut ni réseau ni conteneur.

L'audit par genre et âge utilise les limites exactes de l'EDA : 0–25, 26–35,
36–45, 46–55, 56–65 et 66–120 ans. Les effectifs et effectifs de fraudes sont
indiqués. Sans fraude, le rappel et son IC sont indéfinis, pas égaux à zéro.

## Portes et ambiguïtés

Les couvertures **de chaque classe** sont comparées à `(1-alpha)-0,02`, la revue
à `<= 2 %`, et la latence locale p95 à `< 50 ms`. La non-régression reste
`UNVERIFIED` sans référence fournie explicitement : champion moins 0,01, ou
baseline logistique pour la première exécution (§5.4). Le bon comparateur et
l'utilisation de mesures sur des jeux comparables doivent être validés par
l'équipe. Le test registry sur 100 transactions reste `UNVERIFIED` ; aucune
porte manquante ne provoque de promotion. Le squelette P3 utilise encore 3 %
pour la revue et nécessite un alignement par son propriétaire.

## Persistance et publication

Les agrégats, IC, rapport et un manifeste SHA-256 sont écrits hors dépôt avant
la publication MLflow. Les empreintes du modèle, de la source, de la référence,
des scripts et des artefacts sont enregistrées. Les métriques MLflow
`group_N_*` correspondent à l’élément N du tableau `fairness` du JSON.
La révision du code est une
valeur fournie par l'utilisateur via `--code-revision` ; le script ne lance
aucune commande Git. Le fichier local `predictions.csv` contient les étiquettes, probabilités et indicateurs des ensembles. Son hash figure dans les métriques ; il reste hors dépôt et n'est pas inclus dans la publication MLflow des agrégats. Protéger ce fichier et ne pas le partager sans autorisation.

Si la publication échoue, `mlflow_status.json` conserve le statut et le run ID
lorsqu'il a pu être créé. Après rétablissement de MLflow, exécuter uniquement :

```bat
python ml\scripts\evaluate_final_candidate.py --republish "CHEMIN_DU_DOSSIER_DE_RESULTATS"
```

Cette commande vérifie les empreintes des fichiers sauvegardés et ne reçoit ni
ne relit le jeu final. Un arrêt avant sauvegarde complète nécessite une revue
manuelle ; ne pas changer le chemin du journal pour relancer automatiquement.
