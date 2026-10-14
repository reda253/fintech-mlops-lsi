# Demarrage DevOps local (Windows CMD)

## Perimetre et prerequis

Ce guide configure l'infrastructure locale, pas encore les services metier.
Executer les commandes dans CMD, a la racine du depot clone. Ouvrir Docker
Desktop et attendre que son moteur soit pret. Les ports 80, 443, 5432, 5672
et 15672 doivent etre disponibles.

Outils : Git, Docker Desktop (conteneurs Linux), Docker Compose, kubectl,
kind, Helm et mkcert. Versions observees : Kubernetes v1.37.0, Helm v4.3.0,
mkcert v1.4.4, chart Traefik 41.7.1 (Traefik v3.7.14).

```cmd
git --version
docker version
docker compose version
kubectl version --client
kind version
helm version
mkcert -version
```

Si Helm ou mkcert manque :

```cmd
winget install --id Helm.Helm --exact --source winget
winget install --id FiloSottile.mkcert --exact --source winget
```

Ouvrir un nouveau CMD apres installation pour actualiser le PATH.

## PostgreSQL et RabbitMQ (Compose)

```cmd
docker compose config --quiet
docker compose up -d
docker compose ps
docker exec fintech-postgres psql -U fintech -d fintech -c "SELECT version();"
docker exec fintech-rabbitmq rabbitmq-diagnostics -q ping
```

Les deux conteneurs doivent etre Up. PostgreSQL ecoute sur localhost:5432.
L'interface RabbitMQ est sur http://localhost:15672 (fintech / fintech).
Ces identifiants sont reserves au developpement local.
Compose s'execute hors Kubernetes. PostgreSQL utilise un volume persistant ;
le Compose actuel ne configure pas de volume persistant pour RabbitMQ.

## Cluster kind

```cmd
kind get clusters
```

Si le cluster `fintech` n'existe pas, le creer :

```cmd
kind create cluster --name fintech --image kindest/node:v1.37.0 --config deploy\bootstrap\kind-config.yaml
```

Ne pas recreer un cluster existant. Verifier :

```cmd
kubectl config use-context kind-fintech
kubectl get nodes
```

Les trois noeuds doivent etre Ready. Creer les namespaces manquants :

```cmd
kubectl create namespace fintech
kubectl create namespace ml
kubectl create namespace data
kubectl create namespace tools
kubectl create namespace monitoring
```

`AlreadyExists` indique qu'un namespace est deja present.

## Metrics-server

La version du manifeste est fixee pour eviter un changement silencieux.
Source : https://github.com/kubernetes-sigs/metrics-server/releases/tag/v0.9.0

```cmd
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/download/v0.9.0/components.yaml
kubectl patch deployment metrics-server -n kube-system --type=json -p="[{\"op\":\"add\",\"path\":\"/spec/template/spec/containers/0/args/-\",\"value\":\"--kubelet-insecure-tls\"}]"
kubectl rollout status deployment/metrics-server -n kube-system --timeout=180s
kubectl top nodes
kubectl top pods -A
```

L'option TLS est reservee au laboratoire kind local. Si les metriques ne sont
pas encore disponibles, attendre une minute et reessayer.

## Traefik et HTTPS local

Les ports 80/443 de Windows sont relies au control-plane par le fichier kind.
Traefik utilise les hostPorts correspondants sur ce noeud, avec un seul replica.
Cette installation d'entree n'est pas hautement disponible.

```cmd
helm repo add traefik https://traefik.github.io/charts
helm repo update
helm template traefik traefik/traefik --version 41.7.1 --namespace traefik -f deploy\bootstrap\traefik-values.yaml > NUL
```

Si le rendu ne produit aucune erreur, installer :

```cmd
helm upgrade --install traefik traefik/traefik --version 41.7.1 --namespace traefik --create-namespace -f deploy\bootstrap\traefik-values.yaml --wait --timeout 180s
kubectl get pods -n traefik -o wide
```

Le pod doit etre Ready sur fintech-control-plane.
Installer l'autorite locale et generer le certificat sur chaque PC :

```cmd
mkcert -install
mkdir "%LOCALAPPDATA%\fintech-certs"
mkcert -cert-file "%LOCALAPPDATA%\fintech-certs\fintech.pem" -key-file "%LOCALAPPDATA%\fintech-certs\fintech-key.pem" "*.fintech.local" fintech.local localhost 127.0.0.1
```

Si le dossier existe deja, continuer. Ne jamais commiter ou partager les cles
privees, y compris rootCA-key.pem. Les certificats restent hors du depot.

Creer le Secret TLS dans le meme namespace que l'Ingress :

```cmd
kubectl create secret tls fintech-local-tls -n fintech --cert="%LOCALAPPDATA%\fintech-certs\fintech.pem" --key="%LOCALAPPDATA%\fintech-certs\fintech-key.pem" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f deploy\bootstrap\ingress-smoke-test.yaml
kubectl rollout status deployment/ingress-test -n fintech --timeout=180s
curl.exe -i --resolve test.fintech.local:80:127.0.0.1 http://test.fintech.local
curl.exe -i --resolve test.fintech.local:443:127.0.0.1 https://test.fintech.local
```

Resultat attendu : HTTP 200 et `Welcome to nginx!` pour les deux requetes.
Ne pas ajouter `-k` : le test HTTPS doit verifier le certificat.
`--resolve` evite de modifier le fichier hosts ; il ne configure pas le DNS
du navigateur. HTTPS ne force pas ici la redirection du trafic HTTP.

## NetworkPolicies

Suivre [le test isole](network-policy-test.md). Resultats observes : nginx
accessible avant la policy, timeout avec la policy, connexion retablie apres
suppression. Cela valide ce scenario ingress entre workers, pas encore les
policies des services metier ou le filtrage egress.

## Reprise apres redemarrage et nettoyage

Ouvrir Docker Desktop, puis verifier sans recreer le cluster :

```cmd
docker ps -a
kind get clusters
kubectl config use-context kind-fintech
kubectl get nodes
docker compose up -d
kubectl top nodes
```

Si les conteneurs des noeuds sont arretes, les demarrer :

```cmd
docker start fintech-control-plane fintech-worker fintech-worker2
```

Pour retirer seulement l'application temporaire de test (Traefik reste installe) :

```cmd
kubectl delete -f deploy\bootstrap\ingress-smoke-test.yaml
```

Pour arreter Compose sans supprimer le volume PostgreSQL :

```cmd
docker compose down
```

## GitHub et transmission a l'equipe

La CI dans `.github/workflows/ci.yml` valide la structure du depot et Compose,
puis execute Gitleaks et Trivy. Elle ne recree pas ce cluster et n'execute pas
automatiquement les tests locaux HTTP, HTTPS ou NetworkPolicy.

Apres un push, ouvrir la PR correspondant a la branche, puis l'onglet Checks.
Verifier le dernier commit et attendre Repository checks et Security scans
verts. Une revue du code owner reste requise avant fusion.

Les sorties partagees par l'utilisateur confirment les tests locaux : trois
noeuds Ready, PostgreSQL accessible, metriques disponibles, HTTP/HTTPS 200,
et blocage NetworkPolicy reversible. Le controle RabbitMQ par ping et une
reinstallation complete par un coequipier restent a valider.
Le livrable doit ensuite etre presente a l'equipe selon le guide P4.
