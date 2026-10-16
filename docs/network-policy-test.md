# Test NetworkPolicy sur kind

## Contexte

Test effectue le 14 octobre 2026 sur le cluster `fintech`, Kubernetes
v1.37.0, avec les DaemonSets `kindnet` et `kube-proxy` presents.
Resultats observes dans le terminal de l'utilisateur.

Le namespace temporaire `netpol-test` contient un serveur nginx sur
`fintech-worker` et un client BusyBox sur `fintech-worker2`.
La policy selectionne uniquement le serveur et interdit tout trafic entrant.

## Reproduction (CMD Windows, racine du depot)

Utiliser un namespace de test propre, sans policy residuelle.

```cmd
kubectl apply -f deploy\bootstrap\network-policy-test.yaml
kubectl wait --for=condition=Ready pod --all -n netpol-test --timeout=180s
kubectl exec -n netpol-test client -- wget -T 5 -qO- http://server
kubectl apply -f deploy\bootstrap\network-policy-deny.yaml
```

Attendre dix secondes pour la propagation de la policy, puis :

```cmd
kubectl exec -n netpol-test client -- wget -T 5 -qO- http://server
kubectl delete -f deploy\bootstrap\network-policy-deny.yaml
```

Attendre dix secondes, puis :

```cmd
kubectl exec -n netpol-test client -- wget -T 5 -qO- http://server
```

## Resultats observes

| Etape | Resultat |
| --- | --- |
| Avant la policy | Page `Welcome to nginx!` |
| Avec la policy | `wget: download timed out`, code de sortie 1 |
| Apres suppression de la policy | Page `Welcome to nginx!` |

Le blocage ingress entre workers est valide pour ce scenario et cette
configuration du cluster. Aucun passage a Calico n'est justifie par ce test.
La presence de kindnet seule ne prouve pas qu'il est le composant responsable
du filtrage. Ce test ne valide pas encore les policies des services metier,
les exceptions pour les clients autorises, ni le filtrage egress.

## Nettoyage

Supprimer uniquement le namespace temporaire et ses ressources :

```cmd
kubectl delete namespace netpol-test
```
