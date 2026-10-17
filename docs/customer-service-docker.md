# Customer-service : test Docker local

## Construction

Commandes CMD Windows depuis la racine du depot, Docker Desktop demarre :

```cmd
docker build -f services\customer-service\Dockerfile -t fintech-customer-service:local-test services
docker compose up -d postgres
```

Le contexte `services` inclut le POM parent et common. Maven verify s'execute
avec Java 21 pendant la construction, puis les couches Spring Boot sont
copiees dans une image JRE 21. L'application tourne sous UID/GID 10001.
Le tag local-test est temporaire ; les futurs deploiements doivent utiliser
des tags SHA.

Le job CI `Customer image build and scan` construit cette image et execute
les tests Maven, puis lance Trivy sur les paquets de l'image. Toute
vulnerabilite CRITICAL bloque le job, meme sans correctif disponible.
Le tag CI correspond au SHA du commit ; l'image n'est pas publiee.
Ce nouveau job reste a valider sur GitHub apres le push et l'ouverture de la PR.

## Compte PostgreSQL local

Verifier d'abord si le compte et le schema existent :

```cmd
docker exec fintech-postgres psql -U fintech -d fintech -c "\du customer_user"
docker exec fintech-postgres psql -U fintech -d fintech -c "\dn customer"
```

Pour une base ou ils sont absents, ouvrir psql comme administrateur local :

```cmd
docker exec -it fintech-postgres psql -U fintech -d fintech
```

Saisir dans psql (ne pas recreer un compte/schema existant) :

```sql
CREATE ROLE customer_user LOGIN;
```

Definir le mot de passe avec la commande interactive, puis creer le schema :

```text
\password customer_user
```

```sql
CREATE SCHEMA customer AUTHORIZATION customer_user;
ALTER ROLE customer_user SET search_path = customer;
```

Quitter avec `\q`. Verification du compte par TCP :

```cmd
docker exec -it fintech-postgres psql -h 127.0.0.1 -U customer_user -d fintech -W -c "SELECT current_user, current_schema();"
```

Resultats attendus : customer_user et customer. Ce bootstrap local limite au
service correspond aux objets customer du script complet
`deploy/sql/00_schemas_users.sql`. Ne pas executer ensuite ce script complet
sans traiter les roles et schemas deja presents.

## Configuration et execution

Creer un fichier local hors du depot, sans partager son contenu :

```cmd
mkdir "%LOCALAPPDATA%\fintech-env"
notepad "%LOCALAPPDATA%\fintech-env\customer.env"
```

Si le dossier existe, continuer. Contenu du fichier (remplacer uniquement le
placeholder du mot de passe par celui choisi dans psql, sans guillemets) :

```dotenv
DB_URL=jdbc:postgresql://fintech-postgres:5432/fintech
DB_USER=customer_user
DB_PASSWORD=REPLACE_WITH_LOCAL_PASSWORD
```

Verifier le reseau de PostgreSQL :

```cmd
docker inspect --format "{{json .NetworkSettings.Networks}}" fintech-postgres
```

Le reseau observe est fintech-mlops-lsi_default. Adapter --network si le nom
du projet Compose differe. Le nom fintech-postgres se resout sur ce reseau.
Utiliser un nom de conteneur libre et le port local 8089 disponible :

```cmd
docker run -d --name fintech-customer-test --network fintech-mlops-lsi_default --memory=512m --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m --env-file "%LOCALAPPDATA%\fintech-env\customer.env" -p 127.0.0.1:8089:8082 fintech-customer-service:local-test
docker logs --tail 80 fintech-customer-test
docker exec fintech-customer-test id
```

Attendre Started CustomerServiceApplication. Flyway doit appliquer ou valider
la migration V1 du schema customer. Pour une configuration modifiee, recreer
le conteneur ; un simple redemarrage ne recharge pas le fichier env.

## Validation observee le 17 octobre 2026

Les sorties partagees par l'utilisateur confirment : construction reussie
avec Maven verify, demarrage sous Java 21, UID/GID 10001, connexion au schema
customer et migration Flyway V1 appliquee.

```cmd
curl.exe -i http://localhost:8089/actuator/health/liveness
curl.exe -i http://localhost:8089/actuator/health/readiness
curl.exe -i http://localhost:8089/actuator/prometheus
```

| Requete sans JWT | Resultat observe |
| --- | --- |
| GET /actuator/health/liveness | HTTP 200, status UP |
| GET /actuator/health/readiness | HTTP 200, status UP |
| GET /actuator/prometheus | HTTP 401, challenge Bearer |

La configuration inclut readinessState et db dans la readiness, uniquement
livenessState dans la liveness. La reaction lors d'une panne DB reste a tester.
ProbeSecurityTest verifie les permissions HTTP avec des endpoints de test,
sans lancer PostgreSQL ; il ne teste pas la connectivite DB ou Flyway.
La matrice metier des roles et les operations clients restent a integrer avec P1.

Le passage par host.docker.internal avait produit un refus d'authentification.
La connexion directe sur le reseau Docker a resolu cet echec sans changement
du mot de passe ; l'identite du serveur atteint initialement n'a pas ete prouvee.

## Nettoyage du conteneur de test

```cmd
docker stop fintech-customer-test
docker rm fintech-customer-test
```

Cela conserve PostgreSQL, son volume et le schema customer.
