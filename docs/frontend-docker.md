# Frontend : image Docker, Gateway et tests

## Perimetre et limite importante

L'image compile le frontend React/Vite existant et sert ses fichiers statiques
avec Nginx non-root. Elle ne lance pas le serveur de developpement Vite.
Elle conserve le mode de demonstration P5 : comptes fictifs en memoire,
`VITE_AUTH_MODE=demo` et `VITE_USE_MOCKS=true`. Le frontend actuel n'implemente
pas encore l'authentification JWT. Un login demo ne prouve ni une session
backend, ni une autorisation API reelle. Ne pas deployer ce mode en production.

Ce lot ne change ni les ecrans P5 ni les services metier. Il ajoute :

- Build Node 24, `npm ci`, lint, tests et compilation TypeScript/Vite.
- Runtime Nginx unprivileged, UID/GID 10001, port interne 8080.
- Routage SPA, cache des assets hashes et absence de cache long sur index.html.
- Proxy `/api/` vers le Gateway, sans supprimer le prefixe ni les en-tetes
  Authorization/correlation, sans cache ni buffering des reponses SSE.
- Sante locale `/healthz`, independante de la disponibilite du Gateway.
- Tests Docker, proxy, panne/reprise et navigateur desktop/mobile en CI.

## Construire et demarrer (CMD)

Depuis la racine du depot :

```cmd
docker build -t fintech-frontend:local-test frontend
docker compose -f docker-compose.yml -f docker-compose.frontend.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.frontend.yml up -d --build --wait --wait-timeout 180 frontend
docker compose -f docker-compose.yml -f docker-compose.frontend.yml ps frontend api-gateway
curl.exe -i http://127.0.0.1:8087/healthz
curl.exe -i http://127.0.0.1:8087/api/v1/transactions
```

Ouvrir http://127.0.0.1:8087. Attendu : interface de demonstration, sante
HTTP 200 UP, requete transactions sans JWT refusee par le Gateway avec 401.
Ce refus ne valide pas encore un parcours transactions authentifie.
Le complement ne publie pas le port du Gateway et ne demarre que les deux
services demandes ; il ne demarre pas automatiquement Auth, Customer,
Transaction, RabbitMQ ou PostgreSQL. Leurs URI sont preparees pour le reseau
Compose mais les API authentifiees necessitent leurs implementations et leur
demarrage, ainsi que la strategie JWT frontend/back validee par P1/P5.

Le port local evite Grafana sur 3000. Si 8087 est occupe, definir
`set "FRONTEND_PORT=8091"` avant `up`, puis adapter l'URL.
Ne pas utiliser `--remove-orphans` pour supprimer les services des autres
complements de l'equipe. Ne pas lancer `down -v` sur la pile partagee.

Arret cible, sans toucher aux bases ni au broker :

```cmd
docker compose -f docker-compose.yml -f docker-compose.frontend.yml stop frontend api-gateway
```

Le runtime utilise 128 Mio, un filesystem en lecture seule, un tmpfs `/tmp`
de 64 Mio, aucune capability et `no-new-privileges`. Nginx ecrit son PID, sa
configuration generee et tous ses fichiers temporaires dans `/tmp`.
Le script d'entree ne modifie pas `/etc/nginx` au demarrage.

## Configuration publique et secrets

Les variables `VITE_*` sont compilees et visibles par chaque navigateur.
Ne jamais y placer de mot de passe, token ou cle privee. Les fichiers `.env`
locaux et materiels de cles sont exclus du contexte Docker. Le builder genere
le worker MSW via le `postinstall` deja present ; aucun `node_modules` n'est
copie dans le runtime.

| Parametre | Moment | Valeur par defaut |
| --- | --- | --- |
| `VITE_USE_MOCKS` | Argument de build Docker | `true` |
| `VITE_AUTH_MODE` | Argument de build Docker | `demo` |
| `VITE_GRAFANA_URL` | Argument de build Docker | `http://localhost:3000` |
| `VITE_API_BASE_URL` | Fixe au build | `/api/v1` |
| `GATEWAY_UPSTREAM` | Environnement du conteneur | `http://api-gateway:8080` |

Les variables Compose `FRONTEND_IMAGE` et `GATEWAY_IMAGE` permettent aussi de
selectionner des images deja construites, avec `up --no-build` pour ne pas
les reconstruire. Par defaut, les deux tags sont `local-test`.

Compose traduit `FRONTEND_USE_MOCKS`, `FRONTEND_AUTH_MODE` et
`FRONTEND_GRAFANA_URL` en arguments de build. Modifier une variable `VITE_*`
au simple lancement du conteneur ne modifie pas le JavaScript deja compile.
Le mode `jwt` reste un point d'entree non implemente : ne pas l'activer en
pensant obtenir une authentification reelle.

`GATEWAY_UPSTREAM` est valide au lancement : seulement `http://host:port`,
sans identifiants, chemin, espaces, sauts de ligne ni directives Nginx.
Le port doit etre compris entre 1 et 65535. Le proxy conserve l'URI complete.
La resolution du nom passe par le DNS Docker ; la page statique peut rester
disponible si le backend est absent. Une panne API doit produire une erreur
502/504, jamais le HTML de la SPA avec un faux HTTP 200.
TLS/Ingress et l'authentification de bout en bout ne sont pas valides ici.
Les routes `/actuator`, `/internal` et `/predict` ne sont pas exposees par le
serveur statique. `/healthz` n'est pas une sonde de sante de toute la plateforme.

## Tests et CI

Le job `Frontend image build and scan` construit l'image avec le SHA du commit,
execute Trivy (CRITICAL bloquant, sans ignorer les vulnerabilites non corrigees),
audite aussi les dependances npm de developpement et lance les tests navigateur.
Les captures et traces sont publiees sept jours dans
`frontend-docker-browser-results`. Aucun registre n'est alimente.

Tests locaux, Python 3.10+ et Docker requis :

```cmd
python -B -m unittest discover -s deploy/bootstrap -p test_frontend_smoke_test.py -v
python -B deploy/bootstrap/frontend_compose_ci.py --image fintech-frontend:local-test
```

Pour les tests navigateur, installer les outils depuis `frontend` :

```cmd
cd frontend
npm ci
npx playwright install chromium
cd ..
python -B deploy/bootstrap/frontend_compose_ci.py --image fintech-frontend:local-test --browser-tests
```

Le test complet utilise un projet `frontend-ci-<identifiant>` sans volume
nomme ni nom fixe de conteneur, un port local aleatoire et un faux Gateway
Python explicitement limite aux tests. Il verifie :

- UID 10001 et demarrage en lecture seule avec capabilities supprimees.
- Pages SPA rechargeables, assets reels, cache et erreurs 404 pour assets
  manquants, fichiers caches et routes internes.
- Methode, URI avec query, corps et en-tetes transmis sans modification.
- Conservation d'un refus 401 et livraison du premier evenement SSE avant
  la fermeture de la connexion amont.
- Rejet des configurations amont invalides, y compris avec saut de ligne.
- Pages bienvenue/login/dashboard, image du logo chargee et session demo
  apres rechargement, sur desktop et mobile. Pas de comparaison a des golden
  screenshots absents du depot ; la suite visuelle P5 existante est inchangee.
- Sante locale maintenue lors de l'arret du faux Gateway, erreur API et reprise.

Le faux Gateway permet de tester le contrat du proxy ; il ne remplace pas un
test des vrais services ni un test de messages metier. Le projet prive est
nettoye dans un bloc `finally`, sans toucher aux conteneurs de developpement.

## Correctif de l'outillage de test

Le premier `npm audit` signalait deux alertes critiques liees a Tinypool et
Vitest, et une alerte moderee du mocker. Vitest est passe de la ligne 3 a
`^4.1.12`, compatible avec le Vite 6 du projet ; le lockfile a ete regenere
par npm, sans `npm audit fix --force`. Les types Node 24 necessaires aux
tests sont declares explicitement, plutot que dependants d'un paquet transitif.

References mainteneurs :

- https://github.com/vitest-dev/vitest/security/advisories/GHSA-82fw-gwwq-j7x9
- https://github.com/tinylibs/tinypool/security/advisories/GHSA-85c8-ppgw-ccpr
- https://github.com/nginx/docker-nginx-unprivileged
- https://nodejs.org/en/download

Docker peut signaler `SecretsUsedInArgOrEnv` sur le nom `VITE_AUTH_MODE` :
la valeur est uniquement l'enum publique `demo`/`jwt`, pas un secret.
Ne pas desactiver globalement les controles de secrets pour masquer ce message.

## Etat des preuves

Validation locale du 24 octobre 2026 :

- Build `fintech-frontend:docker-test` reussi : lint, 31 tests Vitest et
  compilation TypeScript/Vite. Lint et typage finaux rejoues avec succes.
- `npm audit` : zero vulnerabilite signalee apres correction de l'outillage.
- 41 tests unitaires DevOps reussis, dont 9 nouveaux tests frontend.
- Test complet isole reussi : UID 10001, lecture seule, assets/cache, sante,
  contrat proxy, premier evenement SSE sans buffering, rejet des cinq
  configurations amont invalides et panne/reprise du faux Gateway.
- Quatre tests Playwright reussis : deux parcours sur chaque viewport,
  desktop 1440x900 et mobile 390x664. Captures examinees. Le badge de donnees
  simulees est volontairement masque sur mobile par la CSS P5 existante ;
  le test verifie sa presence dans le DOM sans modifier ce design.
- Le complement Compose a aussi ete lance avec le vrai Gateway reconstruit,
  dans un projet prive : frontend healthy et API transactions sans JWT 401.
- Trivy 0.70.0 sur archive de l'image : zero CRITICAL detectee, sans ignorer
  les failles non corrigees. Aucun socket Docker donne au scanner.
- Nettoyage reussi des projets de test et des fichiers/cache temporaires ;
  pas de modification des bases, du broker ou des services existants.

Le scan Trivy a emis des avertissements : Alpine 3.24 absent de sa liste EOL
embarquee et details manquants pour CVE-2026-107891 dans sa base. L'analyse
des paquets a termine avec code 0 ; ne pas interpreter ce resultat comme une
garantie d'absence de toute vulnerabilite. Le scan ne detecte pas les paquets
npm dans le JavaScript bundle : l'audit du lockfile complete ce controle.
Ces resultats sont lies aux bases disponibles le jour du test.

Le nouveau passage GitHub Actions est requis avant fusion.
Avec ce Dockerfile, les dix images applicatives ont un Dockerfile
et un job CI ; cela ne suffit pas a declarer toute la plateforme fonctionnelle
ni a fermer #38 sans documentation, preuves CI et demonstration a l'equipe.
