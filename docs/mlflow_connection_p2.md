# Connexion MLflow P2

## Configuration et backend

La resolution d'URI du smoke P2 et du diagnostic est centralisee dans
`ml.tracking_smoke.get_tracking_uri()` ; le pipeline P3 existant reste inchange.
Priorite : argument CLI, environnement, `.env` racine, `ml/.env`. Aucun serveur
par defaut n'est suppose. Les fichiers `.env` sont ignores par `.gitignore`.

URI confirmee par Basma : `http://localhost:5000`, sans authentification client.
Ce serveur Docker Compose appartient a la machine qui execute Docker. Les runs
envoyes a cette URI sont stockes dans PostgreSQL (schema `mlflow`) et les
artefacts dans le volume `mlflow_artifacts` de CETTE machine, pas dans Git et
pas automatiquement sur la machine d'Omar.

Le template existant `log_smoke_run` garde le tag `git_commit`, les parametres
`smoke` et `source`, la metrique de controle `example_metric`, l'artefact
`note.txt` et retourne le run_id. Le diagnostic reutilise ce template et
`connectivity_check` ; il ne cree pas une seconde convention de run.

Le smoke LogReg garde ses metriques, seeds et protocole de pli. Seul le repli
implicite est supprime. SQLite exige `--allow-local-sqlite`, avec annonce visible.
Une URI serveur configuree reste prioritaire : ce flag n'efface pas silencieusement
une erreur serveur ni ne relabellise un run local en run partage.

## Verification depuis l'hote

Dans l'environnement fintech, a la racine :

```powershell
python ml/scripts/check_mlflow_connection.py --report reports/mlflow_connectivity_check.json
```

Le test cree un run, journalise le template, relit les parametres/metrique/tag,
liste puis TELECHARGE `note.txt` depuis l'hote, compare son contenu exact et
supprime uniquement le run qu'il a cree. Le nettoyage est aussi tente apres
un echec de logging ou de telechargement. La suppression MLflow est logique
(`lifecycle_stage=deleted`), pas une purge physique du serveur. L'experience est
conservee. Timeout par requete : 10 s, retries desactives pour ce diagnostic.

La verification HTTP seule ne prouve ni l'upload ni le download des artefacts.
Un rapport FAIL / UNVERIFIED ne doit jamais etre presente comme une connexion
validee. Les erreurs tierces sont classees sans afficher URL, headers ni secrets.

## Incident observe le 17/10/2026

- Depuis Windows : connexion a `localhost:5000` refusee, `WinError 10061`.
- `docker compose ps --format json` : moteur Docker injoignable,
  `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified.`
- Creation/relecture/suppression du run et transfert d'artefact serveur :
  NON VERIFIES tant que le moteur et le service ne sont pas disponibles.
- Aucun changement d'authentification, de certificat ou de compose n'a ete fait.

Reprise : demarrer Docker Desktop (moteur Linux), verifier `docker info`, puis
suivre l'initialisation PostgreSQL/MLflow de [ml/README.md](../ml/README.md).
Si les schemas existent deja, ne pas les recreer et ne pas effacer les volumes.
Relancer ensuite le diagnostic ci-dessus. Ne jamais desactiver TLS pour
contourner une erreur de certificat sur une future URI HTTPS.

## Resolution verifiee le 17/10/2026

Apres demarrage de Docker, le role `mlflow_user` et le schema `mlflow`
manquaient. Avec accord explicite de Basma, seules les lignes 23, 30 et 37 de
`deploy/sql/00_schemas_users.sql` ont ete executees, sans reecriture, dans une
transaction unique. Le mot de passe de developpement deja configure dans
Compose correspondait a `.env.example` ; aucune valeur n'a ete affichee.
La variable locale `MLFLOW_DB_PASSWORD` est maintenant presente dans `.env`,
ignore et non suivi par Git. Ce secret PostgreSQL est distinct de l'absence
d'authentification HTTP client sur le serveur local.

Seul le service MLflow a ete redemarre. Resultats reels : HTTP 200, role et
schema presents, diagnostic PASS, artefact charge puis telecharge depuis
Windows et compare, run supprime logiquement. Le schema contient 65 tables.
Voir `reports/mlflow_postgres_verification.json` et
`reports/mlflow_connectivity_check.json` pour les preuves ; les incidents
ci-dessus restent l'historique initial, pas l'etat courant.
Aucun autre role/schema initialise, aucun volume supprime ou reinitialise.

## SQLite et inventaire a migrer

La base locale precedente `.mlflow/fold_smoke/mlflow.db` et ses artefacts sont
conserves. L'inventaire ne lit ni CSV source ni contenu des artefacts :

```powershell
python ml/scripts/inventory_local_mlflow.py --report reports/mlflow_local_inventory.json
```

Les nombres reels d'experiences, de runs et de fichiers d'artefacts sont dans
ce rapport. `mode=ro` interdit les ecritures SQLite ; aucun run n'est migre.
Un emplacement d'artefacts absent/inconnu y est signale, jamais compte comme
un transfert reussi. Les experiences vides, runs supprimes et runs actifs sont
distingues avant de decider quoi migrer.

Pour reprendre explicitement le backend historique alors que `.env` designe
le serveur, fournir une URI SQLite locale et le flag :

```powershell
python ml/scripts/smoke_fold_logreg.py --tracking-uri "sqlite:///.mlflow/fold_smoke/mlflow.db" --allow-local-sqlite
```

Cette commande ENTRAINE le smoke LogReg : elle est documentee, pas lancee
pour ce travail de connexion. Elle ne demontre pas un serveur partage.

Procedure proposee, non executee :

1. Sauvegarder la base SQLite fermee et les repertoires d'artefacts. Conserver
   l'inventaire et les originaux ; ne pas copier directement SQLite dans PostgreSQL.
2. Valider d'abord le diagnostic complet du serveur cible, y compris artefacts.
3. Choisir avec Omar les experiences et runs historiques utiles (les checks
   et runs supprimes ne sont pas automatiquement des resultats a publier).
4. Exporter via l'API client les parametres, tags, TOUT l'historique des metriques
   avec steps/timestamps et les artefacts. Creer des runs cibles, avec tags
   `source_run_id`, `source_experiment_id`, et conserver une table ancien/nouvel ID.
5. Reconstituer ensuite les liens parent/enfant avec les nouveaux IDs. Les IDs
   ne sont pas transportables tels quels ; registry/aliases a traiter separement
   si l'inventaire futur montre des modeles enregistres.
6. Comparer les comptes, metriques et SHA-256 des artefacts source/cible avant
   toute declaration de migration reussie. Ne pas supprimer les originaux.

## Consultation par Omar

Pour consulter CES runs, Omar doit acceder a la MEME instance et aux memes
volumes persistants : soit sur ta machine, soit via une adresse reseau/VPN
explicitement convenue avec lui (port expose, pare-feu et droits adaptes), soit
en migrant vers une instance partagee. Son propre `localhost:5000` ne pointe
pas sur ton ordinateur. Ne pas exposer un serveur sans auth sur Internet.

Les resultats officiels restent ceux du Job du cluster (spec P2 5.6) ; les
essais du portable ne remplacent pas ce livrable. Les identifiants d'une future
instance restent exclusivement dans l'environnement ou un `.env` ignore.

References : [spec P2 5.2 et 5.6](specs/P2_Data_Scientist_1.md),
[authentification officielle](https://mlflow.org/docs/latest/self-hosting/security/basic-http-auth/),
[API de suppression logique](https://www.mlflow.org/docs/latest/api_reference/rest-api.html#delete-run).
