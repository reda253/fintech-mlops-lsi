# Validation du bot de deploiement (issue #36)

## Configuration administrateur

App attendue : `fintech-deploy-bot-reda253`, installee uniquement sur ce depot,
avec Contents en lecture/ecriture. La capture partagee confirme sa presence
dans le bypass Always allow du ruleset actif ciblant main. L'enregistrement
de la regle et les autres protections applicables doivent etre confirmes par
l'administrateur lors du test d'ecriture.

Dans Settings > Secrets and variables > Actions :

- Variable de depot DEPLOY_APP_ID : App ID de cette GitHub App.
- Secret de depot DEPLOY_APP_PRIVATE_KEY : contenu de la cle privee PEM.

Ne jamais commiter ces identifiants secrets ou afficher le token dans les logs.
Ne pas utiliser un token personnel administrateur pour ce test.

## Etape 1 : authentification sans ecriture

Faire revoir et fusionner la PR ajoutant validate-deploy-bot.yml.
Depuis Actions, ouvrir Validate deploy bot authentication, choisir Run workflow
avec la branche main, puis lancer manuellement le workflow.
Le job refuse toute autre branche et n'utilise pas de code extrait du depot.

Le workflow verifie la presence de la configuration, cree un token
d'installation limite au depot courant avec Contents write, controle le slug
de l'App, puis liste les chemins sous deploy par une requete API en lecture.
Il ne committe et ne pousse aucun changement.

Source de l'action : https://github.com/actions/create-github-app-token

Un resultat vert confirme l'authentification et la lecture du depot avec
cette App. Il ne prouve pas le contournement des protections de main.

## Etape 2 : test d'ecriture prepare, lancement manuel apres revue

L'issue #36 ne doit pas etre fermee apres le seul test d'authentification.
Le guide P4 section 7.6 exige un test reel d'ecriture sur main protegee,
limite a deploy/overlays/demo/kustomization.yaml. La PR de test ajoute un
squelette Kustomize vide a cet emplacement. Ce n'est pas encore un overlay
applicatif et il ne doit pas etre connecte a Argo CD en l'etat.

Le workflow Validate deploy bot write on main verifie la liste exacte des
fichiers modifies et refuse tout autre chemin avant le push. Le bypass Contents write n'est pas
un droit limite a un chemin ; la verification du workflow est indispensable.
Les permissions GitHub App ne limitent pas Contents a un fichier non plus.

Le test d'ecriture doit etre relu avant execution, conserver les protections,
et consigner le lien du run et du commit obtenu. Il ne faut pas conclure que
le bypass fonctionne a partir du nom de l'auteur d'un commit : c'est le token
de l'App qui doit servir a authentifier le push.

Apres revue et fusion de cette PR :

1. Ouvrir Actions > Validate deploy bot write on main > Run workflow, branche main.
2. Laisser confirm_write decoche pour le premier lancement. Un resultat vert
   valide la preparation du changement et le controle, pas le bypass.
3. Avec l'accord de l'equipe sur le commit de test, relancer sur main avec
   confirm_write coche. Cette fois le job committe et pousse directement.
4. Verifier le succes de la derniere etape et le commit sur main. Enregistrer
   les deux liens dans l'issue #36 et mettre a jour cette documentation.

Le changement de test est uniquement un commentaire `# ci-bot-write-test:`
identifie par le run et sa tentative ; les champs YAML et les images restent
inchanges. Les lancements suivants remplacent ce commentaire. La CI teste
le controle avec unittest, sans token, dans des depots Git temporaires.
Le script refuse les liens symboliques, les modifications hors cible, les
changements non stages, les fichiers non suivis et les changements de champs YAML.
Le jeton d'installation authentifie le checkout puis le push. Le workflow
utilise le commit main selectionne au lancement et refuse les autres branches.
Il n'utilise aucun force-push : si main avance entre-temps, le push doit
echouer ; relancer depuis le nouveau main apres verification.
Le commit contient [skip ci], comme prevu par le guide. Ce test ne publie
aucune image et n'active ni Argo CD ni le deploiement continu final.

## Etat

- Test NetworkPolicy isole : valide, voir network-policy-test.md.
- Bypass App : visible sur la capture de l'administrateur.
- Authentification depuis Actions : run manuel #1 reussi sur main 9d07b73,
  d'apres la capture partagee par l'utilisateur.
- Ecriture sur main protegee : non testee.
