# FinTech Risk Intelligence — Spécification fonctionnelle et conformité des maquettes UX/UI

> **Projet :** High-Availability MLOps FinTech Platform  
> **Dépôt :** [reda253/fintech-mlops-lsi](https://github.com/reda253/fintech-mlops-lsi)  
> **Lot :** P5 — Frontend & Observabilité  
> **Livrable :** Conception UX/UI — partie « Mockups » de l'[issue #46](https://github.com/reda253/fintech-mlops-lsi/issues/46)  
> **Nature :** Documentation de référence des interfaces statiques  
> **Version :** 1.0 — octobre 2026

## 1. Objet et périmètre

Ce document formalise la conception fonctionnelle des interfaces de **FinTech Risk Intelligence**, une plateforme de supervision du risque transactionnel et d'aide à la détection de fraude. La solution cible s'appuie sur des microservices, des modèles de machine learning, une chaîne MLOps et des outils d'observabilité.

Le présent livrable regroupe **22 fichiers PNG** : un logo, les écrans applicatifs et plusieurs variantes d'état (indisponibilité ML, résultat de décision, erreurs, états transverses). Les maquettes constituent la **référence visuelle et fonctionnelle initiale** du frontend React ; elles ne représentent ni une application exécutable ni la preuve de fonctionnement des services.

**Objectifs de conception :**

- proposer une expérience unifiée pour les profils `ADMIN` et `ANALYSTE` ;
- rendre lisibles les transactions, les décisions et les indicateurs de risque ;
- faciliter l'investigation et la revue humaine des dossiers ;
- présenter les résultats et visualisations du machine learning sans masquer l'incertitude ;
- donner accès aux notifications, à l'audit et aux informations de supervision selon les habilitations.

## 2. Référentiel documentaire

Les correspondances fonctionnelles sont établies à partir des références suivantes du dépôt :

| Domaine | Référence |
|---|---|
| Exigences transverses et architecture | [`00_Commun_1.md`](../specs/00_Commun_1.md), [`architecture.md`](../architecture.md), [`decisions.md`](../decisions.md) |
| Périmètre P5 | [`P5_Frontend_Observabilite_1.md`](../specs/P5_Frontend_Observabilite_1.md) |
| Routage et droits | [`gateway-routes.md`](../../contracts/gateway-routes.md) |
| Modèles et erreurs communs | [`common.yaml`](../../contracts/common.yaml) |
| Authentification | [`auth-service.yaml`](../../contracts/auth-service.yaml) |
| Clients | [`customer-service.yaml`](../../contracts/customer-service.yaml) |
| Transactions | [`transaction-service.yaml`](../../contracts/transaction-service.yaml) |
| Évaluation du risque et revue | [`risk-service.yaml`](../../contracts/risk-service.yaml) |
| Machine learning | [`ml-service.yaml`](../../contracts/ml-service.yaml) |
| Notifications | [`notification-service.yaml`](../../contracts/notification-service.yaml) |
| Audit | [`audit-service.yaml`](../../contracts/audit-service.yaml) |
| Événements asynchrones | [`events.md`](../../contracts/events.md) |

Les contrats constituent une **cible d'intégration**. Leur présence dans le dépôt ne signifie pas que chaque endpoint est déjà implémenté ou disponible. Les maquettes emploient des données illustratives lorsque les services réels ne sont pas raccordés.

## 3. Principes de conception de l'interface

### 3.1 Identité visuelle

L'application adopte un **thème sombre premium**, des accents orange et rouge pour la hiérarchisation des informations, une navigation latérale persistante, une barre supérieure et des composants récurrents : cartes KPI, tableaux, badges d'état, filtres, graphiques, panneaux de détail et fenêtres de confirmation.

La présentation privilégie la lisibilité des indicateurs de risque, la cohérence entre les écrans et la distinction visuelle des états normaux, sensibles et indisponibles. Le logo constitue une ressource graphique partagée.

### 3.2 Navigation et habilitations

Une seule application React est prévue, avec une **connexion commune**. Le rôle utilisateur provient de l'authentification ; il n'est pas sélectionné manuellement dans le formulaire.

Les espaces ADMIN et ANALYSTE partagent certains écrans. Les fonctionnalités affichées dépendent des permissions effectives, et non du préfixe du nom de fichier PNG. Le rôle `SIMULATEUR` est technique et ne possède pas d'interface React dédiée.

### 3.3 Données et états

Les identités, montants, répartitions, probabilités et métriques représentés dans les visuels servent à illustrer l'ergonomie. Ils **ne constituent pas des résultats de production ou de benchmarking validés**. Les interfaces prévoient également des états de chargement, d'absence de données et d'erreur.

## 4. Catalogue fonctionnel des maquettes

| Réf. | Fichier | Interface / scénario | Accès prévu | Finalité |
|---|---|---|---|---|
| 00 | [`00_COMMUN_logo.png`](./00_COMMUN_logo.png) | Logo | Commun | Identité visuelle de la plateforme |
| 01 | [`01_COMMUN_login.png`](./01_COMMUN_login.png) | Authentification | Commun | Connexion et accès à l'espace autorisé |
| 02 | [`02_ADMIN_dashboard.png`](./02_ADMIN_dashboard.png) | Dashboard administratif | ADMIN | Vue consolidée des transactions, clients, alertes et du modèle |
| 03 | [`03_ANALYSTE_dashboard.png`](./03_ANALYSTE_dashboard.png) | Dashboard analyste | ANALYSTE | Suivi des revues, dossiers suspects et notifications |
| 04 | [`04_ADMIN_clients.png`](./04_ADMIN_clients.png) | Clients | ADMIN / ANALYSTE | Recherche, filtres et consultation des clients |
| 05 | [`05_ADMIN_detail_client.png`](./05_ADMIN_detail_client.png) | Fiche client | ADMIN / ANALYSTE | Profil, carte masquée et transactions associées |
| 06 | [`06_ADMIN_creation_modification_client.png`](./06_ADMIN_creation_modification_client.png) | Formulaire client | ADMIN | Création et modification du profil autorisé |
| 07 | [`07_ADMIN_transactions.png`](./07_ADMIN_transactions.png) | Transactions | ADMIN / ANALYSTE | Consultation, filtres et détail transactionnel |
| 08 | [`08_ANALYSTE_investigation_workspace.png`](./08_ANALYSTE_investigation_workspace.png) | Investigation | ANALYSTE | Analyse d'une transaction et de son évaluation de risque |
| 08b | [`08b_ANALYSTE_investigation_ML_indisponible.png`](./08b_ANALYSTE_investigation_ML_indisponible.png) | Investigation — ML indisponible | ANALYSTE | Présentation du comportement de repli |
| 09 | [`09_ANALYSTE_smart_review_queue.png`](./09_ANALYSTE_smart_review_queue.png) | File de revue | ANALYSTE | Consultation des dossiers ouverts et traités |
| 10 | [`10_ANALYSTE_decision_humaine.png`](./10_ANALYSTE_decision_humaine.png) | Décision humaine | ANALYSTE | Approbation ou blocage après confirmation |
| 10b | [`10b_ANALYSTE_decision_resultat.png`](./10b_ANALYSTE_decision_resultat.png) | Résultat de décision | ANALYSTE | Restitution de l'issue de la revue |
| 10c | [`10c_ANALYSTE_erreurs_decision.png`](./10c_ANALYSTE_erreurs_decision.png) | Erreurs de décision | ANALYSTE | Validation, indisponibilité et conflit concurrent |
| 11 | [`11_ADMIN_intelligence_ml_performances.png`](./11_ADMIN_intelligence_ml_performances.png) | Performances ML | ADMIN / ANALYSTE | Informations modèle et indicateurs d'évaluation |
| 12 | [`12_ANALYSTE_intelligence_ml_visualisations.png`](./12_ANALYSTE_intelligence_ml_visualisations.png) | Visualisations ML | ADMIN / ANALYSTE | Exploration PCA, t-SNE et UMAP |
| 13 | [`13_ANALYSTE_notifications.png`](./13_ANALYSTE_notifications.png) | Notifications | ADMIN / ANALYSTE | Consultation et suivi des notifications |
| 14 | [`14_ADMIN_gestion_utilisateurs.png`](./14_ADMIN_gestion_utilisateurs.png) | Gestion des utilisateurs | ADMIN | Administration des comptes et habilitations |
| 15 | [`15_ADMIN_audit_tracabilite.png`](./15_ADMIN_audit_tracabilite.png) | Audit et traçabilité | ADMIN | Consultation des événements et de leur contexte |
| 16 | [`16_ADMIN_monitoring_observabilite.png`](./16_ADMIN_monitoring_observabilite.png) | Synthèse d'observabilité | ADMIN | Vue d'ensemble technique illustrative |
| 17 | [`17_ADMIN_grafana.png`](./17_ADMIN_grafana.png) | Portail Grafana | ADMIN | Accès aux dashboards Grafana externes |
| 18 | [`18_COMMUN_etats_transverses.png`](./18_COMMUN_etats_transverses.png) | États transverses | Commun | Chargement, erreurs, confirmations et retours utilisateur |

**Convention :** les préfixes `ADMIN` et `ANALYSTE` présents dans certains noms de fichiers identifient la famille graphique d'origine. Ils ne remplacent pas la matrice d'autorisation ci-dessous.

## 5. Matrice des droits fonctionnels

| Fonction | ADMIN | ANALYSTE | SIMULATEUR |
|---|---|---|---|
| Connexion à l'interface humaine | Oui | Oui | Non |
| Dashboard propre au rôle | Oui | Oui | Non |
| Consulter les clients | Oui | Oui | Non via l'UI |
| Créer / modifier un profil client | Oui | Non | Non |
| Consulter les transactions | Oui | Oui | Non via l'UI |
| Créer des transactions | Non | Non | Oui, via le service prévu |
| Consulter les évaluations de risque | Oui | Oui | Selon flux technique, sans UI |
| Consulter la file de revue et décider | Non | Oui | Non |
| Consulter les pages ML | Oui | Oui | Non via l'UI |
| Consulter / marquer les notifications comme lues | Oui | Oui | Non via l'UI |
| Administrer les comptes | Oui | Non | Non |
| Consulter l'audit | Oui | Non | Non |
| Accéder à la synthèse monitoring et au portail Grafana | Oui | Non | Non |

L'autorisation réelle doit être vérifiée **côté backend**, même lorsque l'interface masque les actions non permises.

## 6. Spécifications par domaine

### 6.1 Authentification et gestion des comptes

Le formulaire de connexion utilise les identifiants prévus par le contrat d'authentification, sans choix manuel de rôle. La session cible repose sur un jeton JWT et les mécanismes de renouvellement prévus par le service. Les pages protégées distinguent l'absence de session (`401`) du refus d'accès (`403`).

**Références d'intégration :**

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/users` et `POST /api/v1/auth/users` pour l'administration, ainsi que les opérations complémentaires définies dans le contrat.

Les comptes exposent notamment un nom d'utilisateur, des rôles, un état d'activation et une date de création. Les habilitations doivent respecter les opérations réellement autorisées par le service.

### 6.2 Gestion des clients

Les pages Clients proposent recherche, filtres, pagination, consultation de fiche et, pour ADMIN seulement, création ou modification du profil. Les informations représentées suivent le modèle client du contrat : identité, données de profil, adresse et informations géographiques lorsqu'elles sont disponibles.

La carte bancaire est présentée **sous forme masquée**, avec ses quatre derniers chiffres uniquement. La modification du profil ne doit pas être assimilée à une modification de la carte.

**Références :** `GET /api/v1/customers`, `GET /api/v1/customers/{id}`, `POST /api/v1/customers`, `PUT /api/v1/customers/{id}`.

### 6.3 Transactions et états métier

Les transactions sont consultables par ADMIN et ANALYSTE. Les filtres représentés couvrent notamment le client, la période, le montant et le statut. La création de transactions relève du flux technique du simulateur, et non d'un formulaire destiné aux utilisateurs humains.

Les statuts de référence sont :

| Statut | Sens dans l'interface |
|---|---|
| `EN_ATTENTE` | Traitement non finalisé ou en attente de reprise |
| `EN_REVUE` | Dossier orienté vers la revue humaine |
| `APPROUVEE` | Transaction approuvée |
| `BLOQUEE` | Transaction bloquée |

**Références :** `GET /api/v1/transactions`, `GET /api/v1/transactions/{id}`.

Les montants illustratifs sont exprimés en **USD**, en cohérence avec les exemples issus du jeu de données Sparkov utilisé dans le projet.

### 6.4 Investigation et décision de risque

L'espace d'investigation rassemble le contexte de la transaction, l'évaluation du risque et les informations du modèle disponibles. Il distingue :

- `fraudProbability` : probabilité de fraude représentée sur une échelle de 0 à 1 ;
- `predictionSet` : ensemble de classes retenues par la prédiction conforme ;
- `uncertainty` et le niveau d'incertitude lorsqu'ils sont fournis ;
- la version du modèle et la raison de décision ;
- le statut de la transaction et son contexte de traitement.

**Interprétation des ensembles conformes :**

| Ensemble | Lecture fonctionnelle |
|---|---|
| `[0]` | Seule la classe 0 figure dans l'ensemble |
| `[1]` | Seule la classe 1 figure dans l'ensemble |
| `[0,1]` | Les deux classes restent possibles dans l'ensemble |
| `[]` | Aucune classe n'est retenue par l'ensemble |

Ces ensembles **ne sont pas des probabilités**. Une cible de couverture conforme, par exemple `1 − α = 95 %`, ne signifie pas qu'une transaction individuelle possède une certitude de 95 %. Son interprétation dépend des hypothèses de la méthode et du protocole de calibration.

Les informations de modèle peuvent être absentes lorsque le service ML est indisponible. La maquette dédiée représente le comportement **fail-safe** : aucune approbation automatique ne doit être déduite d'une prédiction indisponible. Selon le service défaillant, le traitement peut être orienté vers une revue humaine ou demeurer `EN_ATTENTE`.

**Références :** `GET /api/v1/risk/assessments/{transactionId}`, `GET /api/v1/risk/stats` et modèles définis dans `risk-service.yaml`.

### 6.5 Revue humaine

La file de revue permet à ANALYSTE de consulter les dossiers, d'ouvrir leur détail et de soumettre une décision. Les états de revue de référence sont `OUVERTE` et `TRAITEE`.

Le parcours de décision prévoit : sélection **APPROUVER** ou **BLOQUER**, commentaire, confirmation explicite, soumission et affichage du résultat. La gestion de concurrence doit empêcher l'écrasement d'une décision déjà enregistrée ; un conflit peut produire une réponse HTTP `409`.

**Références :**

- `GET /api/v1/risk/reviews`
- `GET /api/v1/risk/reviews/{id}`
- `POST /api/v1/risk/reviews/{id}/decision`

Les maquettes de résultat et d'erreur complètent le parcours principal. Le verrouillage, la soumission unique et la persistance effective seront vérifiés pendant l'implémentation.

### 6.6 Intelligence ML

Les interfaces ML sont partagées entre ADMIN et ANALYSTE.

**Performances :** identification du modèle en production, version, métriques d'évaluation, éléments de calibration et indicateurs d'incertitude. La présentation d'un benchmark de plusieurs algorithmes relève du projet, mais le détail des données doit suivre la réponse effectivement fournie par les équipes ML et serving.

**Visualisations :** sélection de la méthode `pca`, `tsne` ou `umap`, puis du mode `class`, `cluster`, `outlier`, `error` ou `uncertainty`. Les légendes et aides à la lecture doivent éviter de surinterpréter les distances globales sur les projections t-SNE et UMAP.

**Références :**

- `GET /api/v1/ml/model`
- `GET /api/v1/ml/performance`
- `GET /api/v1/ml/viz/{method}?view=...`

Le schéma et les données de performance doivent être confirmés lors de l'intégration avec P2/P3. Les valeurs des PNG restent illustratives.

### 6.7 Notifications

La page Notifications est accessible aux deux rôles humains. Les types métier représentés sont `BLOCAGE` et `REVUE`. L'interface distingue les notifications lues et non lues et prévoit leur consultation et leur marquage individuel comme lu.

**Références :**

- `GET /api/v1/notifications`
- `PATCH /api/v1/notifications/{id}/read`
- `GET /api/v1/notifications/stream` — flux SSE authentifié.

La mise à jour en temps réel est un comportement cible du frontend, non vérifiable sur une image statique.

### 6.8 Audit et traçabilité

L'interface Audit est réservée à ADMIN et reste en **lecture seule**. Les événements sont présentés avec les informations disponibles : type, producteur, acteur, entité concernée, identifiant, version de modèle le cas échéant, `correlationId`, date d'événement, date de réception et détails du payload.

Les filtres permettent de retrouver les événements pertinents. L'interface ne prévoit ni modification ni suppression des traces.

**Référence :** `GET /api/v1/audit` et les événements décrits dans `contracts/events.md`.

### 6.9 Monitoring et Grafana

La maquette Monitoring représente une **synthèse de supervision** dans l'espace ADMIN. Elle illustre la disponibilité des services, la latence, les erreurs, les indicateurs ML et les alertes. Les mesures ne sont pas présentées comme provenant d'une plateforme Prometheus déjà opérationnelle.

Le portail Grafana constitue un **accès à une application externe**, distincte de React. Le périmètre P5 prévoit des dashboards Grafana, des règles Prometheus, des logs Loki, des alertes et des runbooks. Ces livrables techniques sont séparés du présent dossier de maquettes.

Les adresses et liens Grafana doivent être configurés selon l'environnement effectivement déployé. Les sources d'une éventuelle synthèse monitoring React restent à définir lors de l'intégration.

## 7. États transverses et expérience utilisateur

La maquette `18_COMMUN_etats_transverses.png` regroupe les principaux états à prévoir dans les composants React :

| État | Comportement cible |
|---|---|
| Chargement | Indicateur de progression ou skeleton |
| Résultat vide | Message contextualisé et possibilité de modifier les filtres |
| `400` | Validation des champs et retour explicite |
| `401` | Session absente ou expirée, réauthentification |
| `403` | Accès interdit pour le rôle courant |
| `409` | Conflit de traitement, notamment pour une revue déjà décidée |
| `429` | Limitation de requêtes, message adapté |
| `500` / erreur réseau | Erreur technique et possibilité de réessayer lorsque pertinent |
| `503` | Service momentanément indisponible |
| Succès | Confirmation visible de l'action accomplie |

La pagination, les filtres, les notifications visuelles et les fenêtres de confirmation sont prévus dans les parcours concernés. L'adaptation aux résolutions d'écran et l'accessibilité seront contrôlées dans l'application React réelle.

## 8. Sécurité et principes de traitement

La conception tient compte des exigences suivantes :

- **Moindre privilège :** chaque rôle n'accède qu'aux fonctions autorisées.
- **Confidentialité :** aucune donnée complète de carte bancaire n'est exposée dans les fiches.
- **Traçabilité :** les opérations sensibles sont corrélables aux événements d'audit.
- **Décision humaine encadrée :** la revue appartient à ANALYSTE et requiert une confirmation explicite.
- **Gestion prudente de l'incertitude :** l'absence de prédiction ML ne peut justifier une approbation automatique.
- **Assistant IA facultatif :** aide à la compréhension et à la navigation, sans capacité autonome d'approuver ou de bloquer une transaction.

Ces principes doivent être appliqués dans le frontend **et imposés par les services backend**. Le masquage d'un bouton ne constitue pas, à lui seul, une protection d'accès.

## 9. Articulation avec le développement React

Les maquettes fournissent les références nécessaires à la réalisation des composants partagés (sidebar, topbar, cartes KPI, tableaux, badges, graphiques, formulaires et modales) ainsi qu'à l'organisation des routes ADMIN et ANALYSTE.

L'étape d'implémentation devra notamment :

1. initialiser l'application React + TypeScript + Vite ;
2. construire les layouts, composants réutilisables et routes protégées ;
3. utiliser des données mock clairement identifiées pour les écrans non raccordés ;
4. préparer les types et services frontend conformément aux contrats ;
5. intégrer progressivement l'authentification, les API, les notifications SSE et les résultats ML ;
6. tester les permissions, les états d'erreur, la navigation et le comportement responsive.

**Limite de validation :** les PNG ne permettent pas d'attester l'exécution du JWT, l'application des droits serveur, la réception des SSE, la gestion concurrente des revues, la disponibilité de Grafana ou la conformité responsive réelle. Ces propriétés relèvent de tests fonctionnels et d'intégration.

## 10. Synthèse du livrable

Le dossier `docs/mockups/` constitue la **référence UX/UI initiale** du projet FinTech Risk Intelligence. Il rassemble l'identité graphique, les parcours métier ADMIN et ANALYSTE, les écrans partagés, les cas particuliers et les états transverses, avec une correspondance explicite vers les contrats du dépôt.

La présente documentation décrit **le périmètre conçu et les comportements attendus**, sans assimiler les représentations statiques à des fonctionnalités déjà opérationnelles. Elle accompagne le [`README.md`](./README.md) du dossier et sert de base à la réalisation du squelette React puis des pages métier.

---

*Document de conception — P5 Frontend & Observabilité — FinTech Risk Intelligence.*
