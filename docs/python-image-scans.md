# Builds et scans des images Python

## Perimetre

Le workflow `.github/workflows/ci.yml` construit les Dockerfiles existants de
`ml-service` et `simulator` a chaque PR et push sur `main`. Chaque image est
etiquetee avec le SHA du commit analyse, puis scannee par Trivy.
Les deux controles sont independants : un echec ne coupe pas l'autre scan.

Comme pour Gateway et Customer, toute vulnerabilite CRITICAL detectee fait
echouer le job, y compris sans correctif disponible (`ignore-unfixed: false`).
Ne pas desactiver le controle pour obtenir une CI verte : examiner le paquet,
la version et le correctif signales dans les logs.

Ces jobs ne publient aucune image, ne deploient rien et ne remplacent pas les
tests applicatifs du workflow `python-ci.yml`. Un build reussi ne prouve pas
que le service demarre ni que son scan est sans vulnerabilite.

## Validation locale

Depuis la racine du depot, en CMD :

```cmd
docker build -t fintech-ml-service:local-test ./ml-service
docker build -t fintech-simulator:local-test ./simulator
```

Les sorties partagees par l'utilisateur confirment la construction reussie des
deux images. Aucun resultat de scan Trivy n'a encore ete fourni pour ces images.

## Validation CI et preuves

Apres ouverture de la PR, verifier les deux jobs :

- `ML service image build and scan`
- `Simulator image build and scan`

Verifier le build ET le scan de chacun. Conserver le lien de l'execution et son
SHA dans l'issue #38 apres validation. La validation distante reste a effectuer.
Ne pas fermer #38 sur cette seule contribution : les autres images demandees
doivent aussi etre couvertes.
