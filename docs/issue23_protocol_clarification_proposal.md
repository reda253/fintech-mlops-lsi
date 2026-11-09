# Proposition de clarification du protocole statistique P2 — issue #23

**Statut : seuil d'effet décidé par Basma le 9 novembre 2026 (post hoc) ; départage Brier encore ouvert.**
Rédigée le 5 novembre 2026, **après observation** du benchmark et de son
rapport statistique. Cette chronologie interdit de présenter un seuil choisi
maintenant comme préenregistré ou comme confirmation indépendante.

## État conservé

- XGBoost reste **candidat** : sa PR-AUC moyenne observée est la plus élevée.
- `ml/stats/validate.py` renvoie `model: null`,
  `status: effect_threshold_required`, `candidates: ["xgb"]` sur les résultats
  existants. La sélection reste en attente ; aucune promotion automatique.
- La PR-AUC est confirmatoire. Le Brier et la latence sont des critères de
  départage éventuels, pas des preuves d'équivalence en PR-AUC.

## Ambiguïté 1 — « effet non négligeable »

`docs/benchmark_requirements.md` prévoit un IC bootstrap apparié sur les dix
moyennes de répétition et indique qu'un IC contenant zéro signifie
« supériorité non démontrée » (lignes 200–203). Il ne donne **aucun seuil de
taille d'effet pertinente en pratique**. Le sens de l'effet, un p de Holm
inférieur à 0,05 et un IC qui exclut zéro établissent une supériorité
statistique, mais ne définissent pas à eux seuls « non négligeable ».

| Option à valider | Avantage | Risque ou limite |
|---|---|---|
| E1. Définir une différence minimale de PR-AUC pertinente pour le métier, avec P1/P2 et justification fondée sur les coûts d'erreur et de revue. La fixer dans une décision datée avant une **nouvelle évaluation indépendante**. | Sens opérationnel explicite ; un effet statistiquement détectable ne suffit pas à lui seul. | Décision prise après consultation du benchmark actuel : son application à ces résultats reste exploratoire. Il faut une évaluation indépendante pour une confirmation honnête. |
| E2. Retirer l'expression « non négligeable » de la règle confirmatoire et publier séparément la différence moyenne, son IC apparié et la corrélation rang-bisériale, sans seuil pratique. | Aucun seuil arbitraire introduit après coup ; résultats statistiques vérifiables. | C'est une modification explicite du critère de sélection initial. Elle ne démontre pas l'intérêt métier d'un gain faible et exige l'accord de l'équipe. |

**En attente de décision :** ne fixer aucune valeur numérique à partir du
classement déjà connu. Conserver XGBoost comme candidat, sans verdict final.

## Ambiguïté 2 — quand utiliser le Brier ?

`docs/benchmark_requirements.md` (lignes 194–199) réserve le Brier aux
**égalités numériques** de moyenne PR-AUC à `1e-12` près, puis départage par
latence p95 et identifiant stable. Le code de sélection actuel considère aussi
les modèles dont la supériorité du leader n'est pas démontrée par Holm et l'IC
apparié. Une absence de preuve de supériorité **n'est pas une équivalence**.

| Option à valider | Avantage | Risque ou limite |
|---|---|---|
| B1. Appliquer le Brier uniquement aux égalités numériques de PR-AUC à `1e-12` près, conformément au texte actuel. Si la supériorité est incertaine mais les moyennes diffèrent, signaler « sélection en attente » avec tous les candidats concernés. | Fidélité au protocole écrit ; évite que le critère secondaire remplace la PR-AUC après observation. | Peut différer le choix opérationnel lorsqu'un IC contient zéro. |
| B2. Traiter les modèles sans supériorité démontrée comme un ensemble à départager par Brier, puis par latence p95 mesurée dans les conditions prévues. Documenter ce changement comme **postérieur aux résultats** et exploratoire. | Fournit une règle opérationnelle lorsque le test n'est pas concluant. | Peut changer le candidat à cause d'un critère secondaire ; non-significativité ne prouve pas équivalence. Nécessite validation explicite et contrôle indépendant avant une conclusion confirmatoire. |

Le seuil `1e-12` concerne une **égalité numérique** déjà documentée. Il ne
définit ni une taille d'effet non négligeable, ni une marge d'équivalence. La
marge de `0,03` employée pour les essais Optuna ne doit pas être réutilisée
pour départager les modèles du benchmark.

## Décision attendue et traçabilité

Faire valider une option E et une option B par les responsables P2 et P3,
indiquer la date, la justification indépendante des scores observés et la
portée de la décision (exploratoire sur le benchmark actuel ou confirmatoire
sur de nouvelles données). Ensuite seulement, aligner la documentation,
`select_model`, ses tests et la description du modèle provisoire. Le rapport
actuel et ses artefacts restent inchangés jusqu'à cette validation.


## Décision partielle du 9 novembre 2026 — post hoc

Basma fixe le seuil d'effet non négligeable à **0,01 point de PR-AUC**,
après observation du benchmark. Cette décision correspond à l'option E1,
mais **n'était pas préenregistrée** et ne démontre pas indépendamment
l'intérêt métier du seuil. Le module reçoit la valeur par l'option CLI
`--effect-threshold`, sans valeur chiffrée codée en dur.

La borne inférieure de l'IC bootstrap apparié pour XGBoost − RandomForest
est 0,023695277277932792 (≈ 0,0237). Le candidat XGBoost satisfait
la règle statistique et le seuil de 0,01 ; il reste **provisoire**,
sans promotion automatique. La sélection reste identique pour tout seuil
non négatif jusqu'à cette borne incluse. Au-delà, la supériorité pratique
selon ce critère n'est plus établie par cet IC.

Le choix entre B1 et B2 pour le départage Brier reste **ouvert**. Les
paragraphes précédents décrivent l'état antérieur à cette décision et ne
doivent pas être lus comme un préenregistrement du seuil.
