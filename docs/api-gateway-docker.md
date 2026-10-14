# API Gateway : image Docker et test local

## Construction (CMD Windows)

Depuis la racine du depot, avec Docker Desktop demarre :

```cmd
docker build -f services\api-gateway\Dockerfile -t fintech-api-gateway:local-test services
```

Le contexte est `services` car la gateway depend du module `common` et du
POM parent. Le Dockerfile utilise le wrapper Maven du depot avec Java 21,
execute `verify`, puis extrait les couches Spring Boot. L'image finale
utilise `eclipse-temurin:21-jre-alpine` et UID/GID 10001.
Les repertoires target locaux sont exclus par `services/.dockerignore`.

Le tag `local-test` est reserve au test sur ce PC. Les images publiees et
deployees devront utiliser un tag correspondant au commit SHA, selon P4.
Le test ne valide pas encore le routage vers les services metier.

## Execution et controles

Le port local 8088 doit etre disponible. Le nom du conteneur doit etre libre.

```cmd
docker run -d --name fintech-gateway-test --memory=512m --read-only --tmpfs /tmp:rw,noexec,nosuid,size=64m -p 127.0.0.1:8088:8080 fintech-api-gateway:local-test
docker logs --tail 80 fintech-gateway-test
docker exec fintech-gateway-test id
curl.exe -i http://localhost:8088/actuator/health/liveness
curl.exe -i http://localhost:8088/actuator/health/readiness
```

Attendre le message `Started ApiGatewayApplication` avant les requetes HTTP.
Les sondes doivent retourner HTTP 200 et `{"status":"UP"}`.
L'utilisateur doit etre `uid=10001(fintech)`.
La JVM utilise `-XX:MaxRAMPercentage=70`.

Le tmpfs noexec empeche Netty de charger sa bibliotheque native depuis /tmp.
Un message de diagnostic peut apparaitre ; le demarrage et les sondes ont
fonctionne dans cette configuration. Les performances restent a mesurer.

Verifier egalement que les autres endpoints exigent toujours un JWT :

```cmd
curl.exe -i http://localhost:8088/actuator/prometheus
curl.exe -i http://localhost:8088/api/v1/customers
```

Resultat attendu sans JWT : HTTP 401. La configuration ProbeSecurityConfig
autorise uniquement GET sur les deux chemins exacts des sondes et conserve
l'authentification JWT ailleurs. Ce n'est pas encore la matrice complete des
roles et des routes publiques du projet, qui reste a integrer avec P1.
Le test ProbeSecurityTest couvre les sondes publiques et quatre chemins
proteges. Il est execute par Maven lors de la construction Docker.

## Reconstruction et nettoyage

Apres une modification, reconstruire l'image avant de recreer le conteneur.
La reconstruction ne met pas a jour un conteneur deja lance.
Pour arreter et retirer uniquement le conteneur de test :

```cmd
docker stop fintech-gateway-test
docker rm fintech-gateway-test
```

## Validation observee

Le 14 octobre 2026, les sorties partagees par l'utilisateur confirment :
construction Docker reussie, demarrage sous Java 21, utilisateur non-root,
et liveness/readiness HTTP 200 apres correction des reponses initiales 401.
La verification manuelle des endpoints proteges et le scan Trivy de cette
image restent a effectuer. Le scan filesystem de la CI ne remplace pas un
scan des paquets presents dans l'image Docker.
