# Transaction Service avec Compose

## Perimetre du lot

- Compose complementaire pour Transaction, sans demarrer toute la plateforme.
- PostgreSQL et RabbitMQ attendus healthy avant le service.
- Readiness applicative limitee a `readinessState,db` (jamais RabbitMQ :
  l'outbox conserve les evenements pendant une panne du broker, D15 et
  `docs/architecture.md`) ; liveness limitee a `livenessState` pour ne pas
  redemarrer le service lors d'une panne externe.
- Port local uniquement, utilisateur 10001, 512 Mio, filesystem en lecture
  seule, tmpfs, capabilities supprimees et `no-new-privileges`.
- Tests HTTP, migration Flyway et tests de panne/reprise dans une CI isolee.

Le fichier de base de l'equipe n'est pas modifie. La configuration Compose
complementaire ajoute un healthcheck RabbitMQ ; sa premiere utilisation peut
recreer ce conteneur. Le Compose actuel ne persiste pas ses messages : se
coordonner avec l'equipe avant de l'appliquer sur un environnement utilise.
Ne jamais utiliser `down -v` sur le projet de developpement.

## Preparation locale (CMD Windows)

Depuis la racine du depot :

```cmd
docker compose up -d postgres rabbitmq
docker exec fintech-postgres psql -U fintech -d fintech -c "\du transaction_user"
docker exec fintech-postgres psql -U fintech -d fintech -c "\dn transaction"
```

Si et seulement si le compte et le schema n'existent pas, entrer dans psql :

```cmd
docker exec -it fintech-postgres psql -U fintech -d fintech
```

Puis, dans psql, une commande a la fois :

```sql
CREATE ROLE transaction_user LOGIN;
```

```text
\password transaction_user
```

Saisir un mot de passe local, invisible a l'ecran, puis :

```sql
CREATE SCHEMA transaction AUTHORIZATION transaction_user;
ALTER ROLE transaction_user SET search_path = transaction;
```

```text
\q
```

Si le compte/schema existe deja, ne pas le recreer ni changer son mot de
passe pour les autres utilisateurs. Verifier la connexion existante :

```cmd
docker exec -it fintech-postgres psql -h 127.0.0.1 -U transaction_user -d fintech -W -c "SELECT current_user, current_schema();"
```

Le resultat attendu est `transaction_user | transaction`.

## Fichier env prive

Reutiliser `%LOCALAPPDATA%\fintech-env\transaction.env` cree pour le test
Docker manuel. Pour une nouvelle machine :

```cmd
if not exist "%LOCALAPPDATA%\fintech-env" mkdir "%LOCALAPPDATA%\fintech-env"
notepad "%LOCALAPPDATA%\fintech-env\transaction.env"
```

Contenu a adapter localement, sans publier les mots de passe :

```dotenv
DB_PASSWORD=REMPLACER_PAR_LE_MOT_DE_PASSE_POSTGRESQL
RABBITMQ_USER=fintech
RABBITMQ_PASSWORD=REMPLACER_PAR_LE_MOT_DE_PASSE_RABBITMQ
```

Les identifiants RabbitMQ doivent correspondre au broker deja initialise.
Le Compose de base utilise `fintech` comme utilisateur de developpement.
Ne pas utiliser `guest` pour une connexion entre conteneurs.
Les adresses DB/RabbitMQ et l'utilisateur DB sont fixes par le complement
Compose ; `DB_URL` et `DB_USER` de l'ancien fichier peuvent rester presents,
mais seront remplaces par Compose.

## Demarrage et controles

Si le conteneur manuel `fintech-transaction-test` tourne encore, l'arreter
pour liberer le port 8090 (ne pas arreter les autres services) :

```cmd
docker stop fintech-transaction-test
```

Puis :

```cmd
set "TRANSACTION_ENV_FILE=%LOCALAPPDATA%\fintech-env\transaction.env"
docker compose -f docker-compose.yml -f docker-compose.transaction.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.transaction.yml up -d --build --wait --wait-timeout 180 transaction-service
docker compose -f docker-compose.yml -f docker-compose.transaction.yml ps transaction-service
docker compose -f docker-compose.yml -f docker-compose.transaction.yml logs --tail 60 transaction-service
curl.exe -i http://localhost:8090/actuator/health/liveness
curl.exe -i http://localhost:8090/actuator/health/readiness
curl.exe -i http://localhost:8090/actuator/prometheus
```

Attendu : conteneur healthy, sondes HTTP 200 UP, Prometheus sans JWT HTTP 401.
Ne jamais partager `config` sans `--quiet` : la sortie peut contenir les
secrets du fichier env. Le fichier reste obligatoire ; a defaut de variable,
Compose attend `.env.transaction.local` (ignore par Git).

Pour un autre port local : `set "TRANSACTION_PORT=8091"` avant `up`, puis
adapter les URL. Apres modification du fichier env, refaire `up -d` avec
`--force-recreate transaction-service` ; `restart` seul ne recharge pas les
variables. Ne pas utiliser `--remove-orphans` pour supprimer Customer, defini
dans son propre complement Compose.

Pour ajouter aussi Customer a la meme pile, utiliser les deux complements et
definir egalement `CUSTOMER_ENV_FILE` ; ne pas inventer un second projet partageant
les memes noms fixes `fintech-postgres` et `fintech-rabbitmq`.

Arret cible, sans suppression des volumes :

```cmd
docker compose -f docker-compose.yml -f docker-compose.transaction.yml stop transaction-service
```

## Tests automatises

Python 3.10 ou plus recent, bibliotheque standard uniquement :

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_transaction_smoke_test.py -v
python -B deploy/bootstrap/transaction_smoke_test.py --base-url http://127.0.0.1:8090
```

Le second script teste les vraies reponses : sondes, challenge Bearer,
Problem Details, preservation du correlation ID, protection de Prometheus,
du health global, de la route transactions et des POST sur les sondes.
Le refus d'une route transactions sans JWT ne prouve pas son implementation
metier ni les permissions avec un vrai JWT.

Le job CI `Transaction image build and scan` execute aussi le test complet :

```cmd
python -B deploy/bootstrap/transaction_compose_ci.py --image fintech-transaction-service:local-test
```

Ce test reutilise l'image indiquee ; la reconstruire apres toute modification
de `application.yml`. Il cree un projet `transaction-ci-<identifiant>`, un
volume PostgreSQL prive, des mots de passe aleatoires temporaires et un port
HTTP aleatoire. Les dependances n'ont ni nom fixe ni port expose. Le modele
fusionne est controle avant de permettre demarrage ou nettoyage.
Le fichier de surcharge CI utilise `!reset`/`!override` : Compose >= 2.24.4
est requis. Ne pas l'appliquer manuellement au projet de l'equipe.

Le test initialise uniquement le role/schema Transaction dans la base jetable,
verifie UID 10001, migration V1 et HTTP, puis arrete successivement RabbitMQ
et PostgreSQL. Panne RabbitMQ : readiness doit rester HTTP 200 UP pendant
20 s (le pod reste dans le Service). Panne PostgreSQL : readiness HTTP 503
DOWN, puis retour 200 UP apres reprise. Liveness reste 200 UP dans les deux
cas. Les delais de connexion CI sont
raccourcis a 2 secondes pour rendre les pannes observables rapidement.
Seuls les conteneurs/volumes du projet prive sont supprimes a la fin, meme
en cas d'echec. Aucun fichier env local ni volume de developpement n'est utilise.

## Etat des preuves

Le test manuel du 24 octobre 2026 a valide le demarrage, Flyway V1, les deux
sondes 200, Prometheus 401 et une connexion RabbitMQ running avec readiness
incluant DB et RabbitMQ. Cela concernait la commande `docker run`, pas encore
le nouveau Compose ou les nouveaux tests de panne.
Le lot automatise a ete verifie localement le 24 octobre 2026 :

- 15 tests unitaires reussis (HTTP local, comportements attendus, refus des
  configurations CI partageant noms fixes, ports ou volumes de developpement).
- Modele Compose fusionne et isolation valides avec `--config-only`.
- Build Docker `fintech-transaction-service:compose-test` reussi, avec Maven
  `verify` pour Transaction et `common`.
- Test complet execute avec cette image : UID 10001, migration V1, sondes,
  controles HTTP de securite et correlation ID valides.
- Arret/reprise de RabbitMQ, puis PostgreSQL : readiness DOWN/UP et liveness
  UP confirmes a chaque phase. Ce resultat portait sur l'ancienne readiness
  incluant RabbitMQ ; depuis la correction, la panne RabbitMQ doit laisser
  readiness UP.
- Nettoyage reussi du projet `transaction-ci-1a6e4dc4a368`, de ses trois
  conteneurs, de son reseau et de son volume PostgreSQL temporaire.

La nouvelle execution sur GitHub Actions et l'utilisation du complement
Compose avec le fichier env de chaque coequipier restent a valider.
Pas de test de messages metier, d'authentification avec vrai JWT, de charge
ou de deploiement Kubernetes dans ce lot. Ne pas fermer #38 sur ce seul lot.
