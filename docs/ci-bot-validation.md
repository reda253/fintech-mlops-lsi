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

## Etape 2 : test d'ecriture a preparer ensuite

L'issue #36 ne doit pas etre fermee apres le seul test d'authentification.
Le guide P4 section 7.6 exige un test reel d'ecriture sur main protegee,
limite a deploy/overlays/demo/kustomization.yaml. Ce fichier n'existe pas
encore lors de la preparation du workflow d'authentification.

Le futur workflow devra verifier la liste exacte des fichiers modifies et
refuser tout autre chemin avant le push. Le bypass Contents write n'est pas
un droit limite a un chemin ; la verification du workflow est indispensable.
Les permissions GitHub App ne limitent pas Contents a un fichier non plus.

Le test d'ecriture doit etre relu avant execution, conserver les protections,
et consigner le lien du run et du commit obtenu. Il ne faut pas conclure que
le bypass fonctionne a partir du nom de l'auteur d'un commit : c'est le token
de l'App qui doit servir a authentifier le push.

## Etat

- Test NetworkPolicy isole : valide, voir network-policy-test.md.
- Bypass App : visible sur la capture de l'administrateur.
- Authentification depuis Actions : workflow prepare, execution a confirmer.
- Ecriture sur main protegee : non testee.
