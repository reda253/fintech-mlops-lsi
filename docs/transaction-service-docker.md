# Transaction Service : image Docker

## Construction

Depuis la racine du depot, en CMD :

```cmd
docker build -f services/transaction-service/Dockerfile -t fintech-transaction-service:local-test services
docker run --rm --entrypoint id fintech-transaction-service:local-test
```

Le contexte est `services`, et non `services/transaction-service`, car Maven
doit construire le parent et le module `common`. Le build execute
`-pl transaction-service -am verify`, sans ignorer les tests existants.
Transaction Service est encore un squelette sans tests propres ; les tests
du module commun ne prouvent pas que le service demarre avec sa base.

L'image reprend le modele Gateway/Customer : build Java 21, extraction des
couches Spring Boot, runtime JRE 21 et UID/GID 10001. Le port interne est 8083.
Le correctif Tomcat 11.0.26 est aligne sur Customer Service.
La commande `id` doit afficher UID/GID 10001 ; elle ne demarre pas Java.

## Controle CI

Le job `Transaction image build and scan` construit l'image etiquetee avec le
SHA du commit, puis execute Trivy. Toute vulnerabilite CRITICAL detectee fait
echouer le job, meme sans correctif disponible. Aucun registre n'est alimente
et aucun deploiement n'est effectue.

Les sorties partagees par l'utilisateur confirment le build Docker local
reussi et `uid=10001(fintech) gid=10001(fintech)`. L'etape Maven `verify`
du Dockerfile a termine avec succes. La capture CI partagee confirme aussi
le succes du job `Transaction image build and scan` avant sa fusion.
Conserver les liens des executions reussies dans l'issue #38.

## Prerequis pour le futur test de demarrage

- PostgreSQL accessible depuis le reseau Docker ; `localhost` dans le
  conteneur designe ce conteneur, pas PostgreSQL.
- Role `transaction_user`, schema `transaction` appartenant a ce role et
  `search_path=transaction`. Flyway ne cree pas le schema automatiquement.
- `DB_URL`, `DB_USER` et `DB_PASSWORD` dans un fichier local non suivi, hors
  depot. Ne pas utiliser le mot de passe par defaut pour le test partage.
- RabbitMQ accessible avec les variables `RABBITMQ_HOST`, `RABBITMQ_PORT`,
  `RABBITMQ_USER` et `RABBITMQ_PASSWORD`. Ne pas compter sur `guest` entre
  conteneurs.
- `JWKS_URI` pointant vers Auth Service sur le reseau Docker pour valider de
  vrais JWT lors des tests authentifies.

Ne pas rejouer integralement `deploy/sql/00_schemas_users.sql` sur la base
existante : il cree aussi les comptes et schemas des autres services.
Ne pas supprimer les volumes PostgreSQL pour recommencer un test.

La securite est fournie par `common` : seuls les GET exacts
`/actuator/health/liveness` et `/actuator/health/readiness` sont publics ;
Prometheus et les routes applicatives restent authentifies.
La readiness par defaut ne comprend pas explicitement les indicateurs DB et
RabbitMQ : le second test ci-dessous les ajoute par variable d'environnement,
sans modifier la configuration applicative commitee.
L'integration Compose reste a effectuer, sans modifier les services deja
utilises par l'equipe.

## Demarrage observe le 24 octobre 2026

Les sorties partagees par l'utilisateur confirment :

- Connexion TCP PostgreSQL avec `current_user=transaction_user` et
  `current_schema=transaction`.
- Conteneur `fintech-transaction-test` sur `fintech-mlops-lsi_default`, port
  local `127.0.0.1:8090` vers 8083, limite 512 Mio, filesystem en lecture seule
  et tmpfs `/tmp` de 128 Mio avec `noexec,nosuid`.
- Connexion Hikari a PostgreSQL et migration Flyway V1 appliquee avec succes.
- `Started TransactionServiceApplication` en environ 10 secondes.
- GET liveness et readiness : HTTP 200 avec `status=UP`.
- GET Prometheus sans JWT : HTTP 401, challenge Bearer et Problem Details.
- En-tete `X-Correlation-Id` present sur les trois reponses HTTP.

Commandes de verification depuis CMD :

```cmd
docker logs --tail 30 fintech-transaction-test
curl.exe -i http://localhost:8090/actuator/health/liveness
curl.exe -i http://localhost:8090/actuator/health/readiness
curl.exe -i http://localhost:8090/actuator/prometheus
```

## Verification PostgreSQL et RabbitMQ

La premiere liste de connexions RabbitMQ etait vide. Le conteneur de test a
ensuite ete recree avec les memes contraintes et l'option suivante :

```text
-e MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE=readinessState,db,rabbit
```

Avec le fichier env local deja prepare et le nom de conteneur libre, depuis
la racine du depot en CMD :

```cmd
docker run -d --name fintech-transaction-test --network fintech-mlops-lsi_default --env-file "%LOCALAPPDATA%\fintech-env\transaction.env" -e MANAGEMENT_ENDPOINT_HEALTH_GROUP_READINESS_INCLUDE=readinessState,db,rabbit -p 127.0.0.1:8090:8083 --memory 512m --read-only --tmpfs /tmp:rw,noexec,nosuid,size=128m fintech-transaction-service:local-test
```

Apres demarrage, l'utilisateur a execute :

```cmd
curl.exe -i http://localhost:8090/actuator/health/readiness
docker exec fintech-rabbitmq rabbitmqctl list_connections user peer_host peer_port state
```

Resultats observes : HTTP 200 avec `status=UP` et une connexion RabbitMQ
pour l'utilisateur `fintech`, peer `172.21.0.4`, etat `running`. L'adresse IP
est temporaire et ne doit pas etre fixee dans la configuration.
La readiness verifie ainsi les indicateurs DB et RabbitMQ, et pas seulement
l'etat interne de l'application. Elle ne prouve pas un echange de messages
metier ni le fonctionnement des consommateurs.

La validation d'un vrai JWT reste a effectuer. Aucun secret du fichier local
`%LOCALAPPDATA%\fintech-env\transaction.env` n'est copie dans le depot.
