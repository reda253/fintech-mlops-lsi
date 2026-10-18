# SonarQube Cloud : premiere integration Java (issue #37)

## Projet et perimetre

- Organisation : reda253.
- Project key : reda253_fintech-mlops-lsi.
- Instance : https://sonarcloud.io.
- Secret GitHub Actions requis : SONAR_TOKEN, deja cree selon la capture fournie.

Le workflow SonarCloud Java analyse le reactor Maven services : common et les
sept services Java. Cette premiere integration n'analyse pas le frontend,
ml-service, ml ou simulator. Ne pas lancer un scanner partiel pour ces dossiers
avec la meme project key : cela remplacerait l'analyse du projet au lieu de
la completer. Une analyse multi-langage coherente reste a definir avec l'equipe.

## Configuration dans SonarQube Cloud

Reda doit verifier que l'App SonarQube Cloud est installee sur le depot, que
le token a le droit Execute Analysis sur ce projet, et que la branche principale
du projet est main.

Dans le projet, Administration > Analysis Method : desactiver Automatic Analysis
si elle est active, puis utiliser l'analyse CI GitHub Actions/Maven.
Cette modification concerne uniquement ce projet, pas tous les projets de
l'organisation. Ne pas modifier le Quality Gate pour contourner un resultat rouge.

Source : https://docs.sonarsource.com/sonarqube-cloud/getting-started/github

## Fonctionnement CI

Le workflow est declenche sur les PR vers main, les pushes sur main et
manuellement depuis main. Les PR de forks sont ignorees car leur contexte
ne recoit pas le token. Aucun pull_request_target n'est utilise.
Le job recupere l'historique complet, utilise Java 21 et le wrapper Maven,
execute clean verify avec le profil coverage, puis le scanner Maven 5.7.0.6970
dans la meme invocation Maven. Il analyse tous les modules sans ignorer les tests.

Le profil coverage active JaCoCo 0.8.15 uniquement lorsqu'il est demande ; les
builds habituels et Docker restent inchanges. Les modules ayant des tests
produisent target/site/jacoco/jacoco.xml, chemin detecte par defaut par Sonar.
Les modules sans tests ne sont pas presentes comme ayant une couverture valide.
Les rapports JaCoCo et Surefire disponibles sont archives dans Actions pendant
sept jours. La generation de rapports ne cree pas les tests metier manquants.

sonar.qualitygate.wait=true fait attendre le resultat du Quality Gate pendant
300 secondes maximum. Le job echoue si le gate echoue, si le serveur ne repond
pas a temps ou si l'analyse echoue. Le token vient uniquement du secret Actions.

Sources :
- https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/scanners/sonarscanner-for-maven
- https://docs.sonarsource.com/sonarqube-cloud/analyzing-source-code/analysis-parameters/parameters-not-settable-in-ui
- https://www.jacoco.org/jacoco/trunk/doc/changes.html

## Verification locale sans token

Depuis CMD, a la racine du depot :

```cmd
cd services
mvnw.cmd -B -ntp -Pcoverage clean verify
```

Cette commande ne contacte pas SonarQube Cloud et n'a pas besoin de SONAR_TOKEN.
Elle peut telecharger les dependances Maven et les plugins. Ne pas lancer le
scanner localement en collant un token dans la ligne de commande ou dans Git.

## Validation et mise en service

Creer une PR depuis devops/sonarcloud vers main. Dans Checks, ouvrir
SonarCloud Java / Java analysis and Quality Gate puis consulter le tableau
de bord du projet SonarQube Cloud.

Si la premiere analyse de PR echoue parce que main n'a pas encore ete analysee,
faire initialiser l'analyse de main avec Reda. Le workflow doit etre disponible
sur main pour son lancement manuel. Ne pas confondre ce probleme de configuration
avec un echec de tests ou de Quality Gate ; conserver les logs pour diagnostiquer.

Apres le premier succes sur main et sur une PR, Reda peut ajouter le check
Java analysis and Quality Gate aux checks obligatoires du ruleset de main.
Un check configure dans le YAML n'est pas automatiquement obligatoire pour la
fusion si le ruleset ne l'exige pas.

Un echec de Quality Gate peut signaler de vrais problemes de qualite ou de
couverture : examiner les mesures et corriger avec P1, sans masquer des fichiers
ou reduire les seuils pour obtenir artificiellement du vert.

## Etat

Identifiants fournis par l'equipe et secret present sur GitHub. Verification
locale du 18 octobre 2026 : clean verify avec le profil coverage reussi sur
les neuf modules Maven, 12 tests executes sans echec (six gateway, six customer).
Les rapports JaCoCo XML des deux services testes ont ete generes. La JVM locale
etait Java 25 avec compilation release 21 ; GitHub Actions utilisera Java 21.
Les autres modules n'ont pas encore de tests.
La premiere analyse distante et le Quality Gate restent a valider.
L'issue #37 ne doit pas etre fermee avant cette validation.
