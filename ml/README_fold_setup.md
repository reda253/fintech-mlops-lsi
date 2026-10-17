# T4 : preparation d'un pli et smoke LogReg

Depuis la racine, dans l'environnement fintech :

```powershell
python -m pytest ml/tests/test_fold_data.py -v
python ml/scripts/smoke_fold_logreg.py
```

Le smoke utilise le premier des cinq plis stratifies, seed 42, et entraine une
seule regression logistique. Il ne lance ni Optuna ni le benchmark 10x5.

Le module `ml/src/validation/fold_data.py` ajuste un clone neuf du preprocessing
sur tout le train naturel du pli. Ensuite seulement, il conserve toutes les
fraudes et au plus dix legitimes par fraude, tires sans remplacement. La
validation garde toutes ses lignes. Beta est le rapport reel entre les
legitimes conserves et les legitimes presents dans ce train.

Le chargeur refuse tout chemin sauf `data/raw/fraudTrain.csv`. Une premiere
lecture porte uniquement sur les dates, pour retrouver le development trie
stablement (70 % par calcul entier). La seconde lecture ignore toutes les
lignes hors development. Les bornes, index source et metadonnees de provenance
permettent ensuite de refuser les autres zones et les plis qui se chevauchent.
Ces gardes controlent les appels normaux ; des metadonnees pandas forgees
volontairement ne constituent pas une preuve d'origine.

MLflow : `ml.tracking_smoke.get_tracking_uri()` resout l'argument CLI,
l'environnement puis les `.env` locaux. Sans URI, le smoke refuse de demarrer.
Le repli SQLite dans `.mlflow/fold_smoke/mlflow.db` exige le flag explicite
`--allow-local-sqlite` ; il n'est jamais choisi silencieusement.
Ce backend local ne demontre pas une connexion au serveur PostgreSQL de P3.
Pour ce dernier, une fois demarre :

```powershell
$env:MLFLOW_TRACKING_URI = "http://localhost:5000"
python ml/scripts/smoke_fold_logreg.py
```

Verifier d'abord la connexion sans entrainement et le telechargement d'artefact :

```powershell
python ml/scripts/check_mlflow_connection.py
```

Details : [connexion, backend et migration](../docs/mlflow_connection_p2.md).

Le run enregistre beta, effectifs, configuration, seed, PR-AUC brute et corrigee,
moyenne des probabilites, prevalence validation, versions, commit et etat dirty.
Les sources du preprocessing et du smoke sont aussi jointes au run. Le client
relit le run pour verifier les metriques et l'artefact de synthese.

La correction d'a priori conserve le classement et donc l'average precision.
Elle ne suffit pas a garantir que la moyenne des probabilites d'un modele
reel soit egale a la prevalence : cela depend de sa calibration. Le test de
prevalence utilise un posterior connu pour verifier la formule, sans imposer
une fausse garantie au modele reel. Les calibrations seront traitees plus tard.

Les sorties du smoke sont dans `reports/fold_logreg_smoke.json`. Aucun modele
final n'est package et aucun autre pli n'est execute.
