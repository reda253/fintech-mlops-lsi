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
du Dockerfile a termine avec succes. Le job CI de build/scan a ensuite ete
valide avant fusion. Le demarrage manuel avec PostgreSQL et RabbitMQ a aussi
ete observe le 24 octobre 2026 ; voir le guide Compose pour les preuves et
les limites de cette validation.
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
La readiness inclut maintenant explicitement `readinessState,db,rabbit` ;
la liveness ne depend que de `livenessState`.
Le [guide Compose Transaction](transaction-compose.md) decrit la configuration
locale, le fichier env prive, les tests HTTP et les tests CI isoles de panne
et reprise. Les commandes de build ci-dessus restent valables.
