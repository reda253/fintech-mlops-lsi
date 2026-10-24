# Images Auth, Risk, Notification et Audit

## Perimetre

Ce lot ajoute quatre Dockerfiles et quatre controles CI, sans changer le
Compose partage, les manifests Kubernetes ni le code metier des services.
Il suit le modele deja utilise par Customer et Transaction :

- Build Java 21 avec le Maven Wrapper, `verify` et les dependances du reactor.
- Extraction des couches Spring Boot puis copie dans un runtime JRE 21.
- Utilisateur/groupe 10001, repertoire `/app`, heap limite a 70 % de la RAM.
- Tomcat 11.0.26, aligne sur Customer et Transaction, pour les quatre modules.
- Aucun mot de passe, token ou materiel de signature genere dans les images.

| Service | Port interne | Schema | Compte applicatif | Particularite |
| --- | --- | --- | --- | --- |
| auth-service | 8081 | auth | auth_user | Emission JWT/JWKS pas encore implementee |
| risk-service | 8084 | risk | risk_user | Appel ML et decisions pas encore implementes |
| notification-service | 8085 | notification | notification_user | Consommation AMQP et SSE pas encore implementes |
| audit-service | 8086 | audit | audit_user | Migration avec audit_migrator, pas audit_user |

Au moment de ce lot, chacun contient uniquement sa classe de demarrage,
sa configuration et sa migration V1. Un build reussi n'est donc pas la preuve
d'un parcours applicatif fonctionnel. `common` est teste pendant le build ;
ces quatre modules n'ont pas encore de tests metier propres.

## Construire les quatre images (CMD)

Depuis la racine du depot :

```cmd
docker build -f services/auth-service/Dockerfile -t fintech-auth-service:local-test services
docker build -f services/risk-service/Dockerfile -t fintech-risk-service:local-test services
docker build -f services/notification-service/Dockerfile -t fintech-notification-service:local-test services
docker build -f services/audit-service/Dockerfile -t fintech-audit-service:local-test services
```

Le contexte doit rester `services`, car chaque build utilise le parent et le
module `common`. Les versions des dependances ne sont pas mises a jour
automatiquement par les Dockerfiles. Le cache Maven accelere les builds
successifs mais ne supprime aucun test.

`services/.dockerignore` exclut maintenant egalement les fichiers `.env`,
`.pem`, `.key`, `.p12`, `.pfx` et `.jks` dans tout le contexte des services.
Les secrets doivent rester hors depot, puis etre injectes au demarrage.
Cette exclusion ne remplace pas la vigilance ou le scan Gitleaks.

## Verifier les images sans demarrer les applications

Python 3.10 ou plus recent, sans bibliotheque externe :

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_verify_java_image.py -v
python -B deploy/bootstrap/verify_java_image.py --image fintech-auth-service:local-test --port 8081
python -B deploy/bootstrap/verify_java_image.py --image fintech-risk-service:local-test --port 8084
python -B deploy/bootstrap/verify_java_image.py --image fintech-notification-service:local-test --port 8085
python -B deploy/bootstrap/verify_java_image.py --image fintech-audit-service:local-test --port 8086
```

Le script controle les metadonnees reelles de l'image : utilisateur, port,
repertoire, entrypoint, heap et absence des principales variables de secrets
dans l'environnement integre. Il execute ensuite `id` et `java -version`
dans des conteneurs temporaires sans reseau, sans capabilities, en lecture
seule et avec `no-new-privileges`. Il verifie UID/GID 10001 et Java 21.
Il ne publie aucun port et ne se connecte pas aux bases ou au broker existants.
Il n'analyse pas tous les fichiers contenus dans le JAR et ne prouve pas
l'absence de tout secret : Gitleaks et la revue de code restent necessaires.

## CI et preuve des scans

Sur chaque PR et push sur `main`, une matrice execute independamment :

- `Auth image build and scan`
- `Risk image build and scan`
- `Notification image build and scan`
- `Audit image build and scan`

Chaque job construit l'image a partir du SHA analyse, execute le verificateur
d'image puis Trivy. Une vulnerabilite CRITICAL bloque le job, meme sans
correctif disponible. Un echec ne coupe pas les trois autres jobs.
Aucune publication dans un registre et aucun deploiement dans ce lot.
Le controle `Repository checks` execute les tests unitaires du verificateur.
Conserver les liens des executions reussies dans l'issue #38 ; ne pas
confondre validation locale et resultat du nouveau workflow sur GitHub.

## Prerequis pour les prochains tests applicatifs

### Connexions communes

Chaque schema PostgreSQL doit exister avant Flyway (`create-schemas=false`).
Utiliser les comptes propres a chaque service, pas le superutilisateur.
Les variables `DB_URL`, `DB_USER`, `DB_PASSWORD`, `RABBITMQ_HOST`,
`RABBITMQ_PORT`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD` et `JWKS_URI` sont lues
par les configurations actuelles. Ne pas utiliser `localhost` pour joindre
un autre conteneur ; utiliser un reseau Docker et des noms de services.
Ne pas utiliser `guest` pour RabbitMQ entre conteneurs.

Ne pas rejouer integralement `deploy/sql/00_schemas_users.sql` sur une base
existante : il cree aussi les comptes des autres services. Ne jamais utiliser
`down -v` ou supprimer les volumes pour contourner une erreur d'initialisation.

Les configurations de ces quatre services exposent les probes mais leurs
groupes readiness n'incluent pas encore explicitement DB/RabbitMQ. Un resultat
UP ne prouverait donc pas leur disponibilite. Leur integration runtime fera
l'objet d'un lot distinct, avec readiness et tests reels adaptes a chacun.

### Auth et cles JWT

Auth est encore un squelette : ne pas pretendre que la presence de son image
valide l'emission JWT, la publication JWKS ou les routes de connexion.
Aucun nom de variable pour une cle privee n'est invente dans ce lot : le
contrat d'injection doit etre defini avec le developpeur Auth quand ce code
sera ajoute. Ne pas generer de cle privee pendant le build, ne pas la copier
dans le JAR et ne pas la commiter. Prevoir une injection runtime en lecture
seule et les SealedSecrets pour Kubernetes, selon le contrat retenu.

### Audit : garder la separation des privileges

La configuration existante distingue :

- `DB_USER=audit_user` et `DB_PASSWORD` pour les acces applicatifs.
- `FLYWAY_USER=audit_migrator` et `FLYWAY_PASSWORD` pour les migrations DDL.

Le schema `audit` appartient a `audit_migrator`. Le bootstrap SQL accorde a
`audit_user` USAGE sur le schema, INSERT/SELECT sur les futures tables et
USAGE/SELECT sur les sequences creees par le migrateur. Ne pas contourner
cette separation en utilisant le migrateur comme utilisateur applicatif.
La validation runtime devra verifier ces privileges et le refus des UPDATE
et DELETE. La simple construction de l'image ne valide pas l'append-only.

### Risk et Notification

Leurs images n'ajoutent pas l'appel ML, les consommateurs de messages ou le
flux SSE. Ces contrats et parcours devront etre testes avec les developpeurs
concernes avant de parler de fonctionnement de bout en bout.

## Etat de validation du lot

Verification locale du 24 octobre 2026 :

- Les quatre builds `fintech-<service>:batch-test` ont termine avec succes.
- Les tests existants de `common` ont ete executes par Maven pendant les builds
  (21 tests reussis par build ; pas de tests propres aux quatre squelettes).
- Le verificateur a valide chaque image : port, entrypoint, repertoire, heap,
  absence des principales variables de secrets, UID/GID 10001 et Java 21.
- Les 32 tests unitaires DevOps ont reussi, dont les 10 nouveaux tests du
  verificateur et les tests existants Transaction et CI-bot.
- Les quatre scans Trivy 0.70.0 ont reussi avec zero vulnerabilite CRITICAL
  detectee, `ignore-unfixed=false`. Ils ont analyse les archives exportees
  des images, sans socket Docker dans le scanner. Les archives et le volume
  temporaire de cache ont ensuite ete supprimes.

Ces scans filtraient uniquement CRITICAL : ils ne prouvent pas l'absence de
vulnerabilites de toutes severites. Trivy a aussi emis un avertissement car
Alpine 3.24 n'est pas dans sa liste EOL embarquee ; l'analyse des paquets
Alpine et des JAR a toutefois ete executee. Ces resultats dependent des bases
chargees le jour du test et ne sont pas une garantie de securite generale.
Le nouveau passage GitHub Actions reste a valider apres push et ouverture de PR.
Avec ces quatre images, le depot comporte neuf Dockerfiles applicatifs :
les sept services Java, ML Service et Simulator. Le frontend reste a traiter
pour la cible des dix images. Ne pas fermer #38 sur cette seule contribution.
