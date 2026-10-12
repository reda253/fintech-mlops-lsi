# FinTech Risk Intelligence — Maquettes UX/UI

> **Projet :** High-Availability MLOps FinTech Platform  
> **Livrable :** Conception des interfaces (Mockups) — issue [#46, Mockups + React Skeleton](https://github.com/reda253/fintech-mlops-lsi/issues/46)  
> **Équipe :** Projet LSI — Frontend & Observabilité (P5)  
> **Statut :** Maquettes initiales de référence ; ajustements fonctionnels et responsive prévus lors de l'implémentation React.

## 1. Présentation

Ce dossier rassemble les **22 visuels PNG** de référence de l'interface *FinTech Risk Intelligence*, une plateforme de supervision du risque et de détection de fraude bancaire reposant sur des microservices, des modèles de machine learning et une infrastructure MLOps.

Ces maquettes définissent l'expérience utilisateur et l'identité graphique avant le développement du frontend **React + TypeScript + Vite**. Elles ne constituent pas une application exécutable.

**Dépôt :** [reda253/fintech-mlops-lsi](https://github.com/reda253/fintech-mlops-lsi)  
**Documentation détaillée :** [maquettes_conformite.md](./maquettes_conformite.md)

## 2. Principes de conception

- **Identité visuelle :** thème sombre premium, accents orange/rouge, sidebar persistante, topbar, cartes KPI, graphiques et tableaux cohérents.
- **Une application, deux espaces humains :** `ADMIN` et `ANALYSTE`, avec connexion commune et affichage conditionné par les permissions.
- **Pages partagées :** clients, transactions, ML et notifications utilisent des interfaces communes, avec actions autorisées selon le rôle.
- **Revue humaine :** l'analyste examine les dossiers et confirme les décisions ; l'administrateur ne décide pas à sa place.
- **Observabilité :** la synthèse React et l'accès externe à Grafana sont distincts ; Grafana n'est pas intégré dans React.
- **Données :** les chiffres et identités affichés dans les images sont illustratifs et ne constituent pas des mesures de production validées.

## 3. Catalogue des maquettes

Les liens ci-dessous ouvrent directement les fichiers PNG depuis GitHub, une fois le dossier publié.

| Fichier | Écran / état | Accès prévu |
|---|---|---|
| [00_COMMUN_logo.png](./00_COMMUN_logo.png) | Identité visuelle — logo (ressource, pas une page) | Commun |
| [01_COMMUN_login.png](./01_COMMUN_login.png) | Connexion | Commun |
| [02_ADMIN_dashboard.png](./02_ADMIN_dashboard.png) | Tableau de bord administratif | ADMIN |
| [03_ANALYSTE_dashboard.png](./03_ANALYSTE_dashboard.png) | Tableau de bord analyste | ANALYSTE |
| [04_ADMIN_clients.png](./04_ADMIN_clients.png) | Liste et recherche des clients | ADMIN / ANALYSTE (lecture seule) |
| [05_ADMIN_detail_client.png](./05_ADMIN_detail_client.png) | Fiche détaillée d'un client | ADMIN / ANALYSTE (lecture seule) |
| [06_ADMIN_creation_modification_client.png](./06_ADMIN_creation_modification_client.png) | Création et modification d'un client | ADMIN |
| [07_ADMIN_transactions.png](./07_ADMIN_transactions.png) | Consultation et filtrage des transactions | ADMIN / ANALYSTE |
| [08_ANALYSTE_investigation_workspace.png](./08_ANALYSTE_investigation_workspace.png) | Investigation et analyse du risque | ANALYSTE |
| [08b_ANALYSTE_investigation_ML_indisponible.png](./08b_ANALYSTE_investigation_ML_indisponible.png) | Investigation — modèle ML indisponible | ANALYSTE |
| [09_ANALYSTE_smart_review_queue.png](./09_ANALYSTE_smart_review_queue.png) | File de revue humaine | ANALYSTE |
| [10_ANALYSTE_decision_humaine.png](./10_ANALYSTE_decision_humaine.png) | Saisie et confirmation d'une décision | ANALYSTE |
| [10b_ANALYSTE_decision_resultat.png](./10b_ANALYSTE_decision_resultat.png) | Résultat de la décision | ANALYSTE |
| [10c_ANALYSTE_erreurs_decision.png](./10c_ANALYSTE_erreurs_decision.png) | Erreurs et conflits de décision | ANALYSTE |
| [11_ADMIN_intelligence_ml_performances.png](./11_ADMIN_intelligence_ml_performances.png) | Performances et informations ML | ADMIN / ANALYSTE |
| [12_ANALYSTE_intelligence_ml_visualisations.png](./12_ANALYSTE_intelligence_ml_visualisations.png) | Visualisations PCA, t-SNE et UMAP | ADMIN / ANALYSTE |
| [13_ANALYSTE_notifications.png](./13_ANALYSTE_notifications.png) | Notifications de blocage et de revue | ADMIN / ANALYSTE |
| [14_ADMIN_gestion_utilisateurs.png](./14_ADMIN_gestion_utilisateurs.png) | Gestion des utilisateurs | ADMIN |
| [15_ADMIN_audit_tracabilite.png](./15_ADMIN_audit_tracabilite.png) | Audit et traçabilité | ADMIN |
| [16_ADMIN_monitoring_observabilite.png](./16_ADMIN_monitoring_observabilite.png) | Synthèse de monitoring | ADMIN |
| [17_ADMIN_grafana.png](./17_ADMIN_grafana.png) | Portail de liens vers Grafana externe | ADMIN |
| [18_COMMUN_etats_transverses.png](./18_COMMUN_etats_transverses.png) | États de chargement, erreurs et confirmations | Commun |

> **Convention de nommage :** les préfixes `ADMIN` et `ANALYSTE` identifient l'espace de conception d'origine ; ils ne signifient pas nécessairement que la page est réservée à ce rôle. Le tableau ci-dessus précise les droits prévus.

## 4. Parcours utilisateurs

**ADMIN :** connexion → dashboard → clients / transactions / ML / notifications → gestion des utilisateurs / audit / monitoring → accès externe à Grafana.

**ANALYSTE :** connexion → dashboard → transactions / clients → file de revue → investigation → décision confirmée → résultat ou gestion du conflit. Accès également aux pages ML et notifications.

Le rôle `SIMULATEUR` est technique : il ne possède pas d'espace React. La création des transactions est assurée par les services prévus à cet effet, et non par un formulaire manuel ADMIN ou ANALYSTE.

## 5. Conformité et sources

La description détaillée des écrans, des permissions, des contrats API et des cas particuliers figure dans **[maquettes_conformite.md](./maquettes_conformite.md)**.

Références principales du dépôt :

- [`docs/specs/00_Commun_1.md`](../specs/00_Commun_1.md)
- [`docs/specs/P5_Frontend_Observabilite_1.md`](../specs/P5_Frontend_Observabilite_1.md)
- [`contracts/gateway-routes.md`](../../contracts/gateway-routes.md)
- [`contracts/`](../../contracts/)

Les comportements interactifs (JWT, autorisation côté serveur, appels API, SSE, gestion des conflits et adaptation responsive) devront être **implémentés et testés dans React** : ils ne peuvent pas être validés à partir de PNG seuls.

## 6. Consulter et utiliser les maquettes

1. Ouvrir le tableau du **catalogue** et sélectionner l'écran souhaité.
2. Lire les variantes `08b`, `10b`, `10c` et `18` pour comprendre les scénarios d'indisponibilité, de résultat et d'erreur.
3. Consulter [`maquettes_conformite.md`](./maquettes_conformite.md) pour les permissions, les données et les correspondances API.
4. Utiliser ces images comme **références visuelles** lors de la création des composants et des routes React dans [`frontend/`](../../frontend/).

## 7. Périmètre du livrable

**Inclus :** 22 PNG, inventaire des écrans, parcours utilisateurs et documentation de conformité.  
**Hors périmètre de ce dossier :** code React, services backend, dashboards Grafana opérationnels et déploiement Kubernetes.

Ce dossier constitue la **partie « Mockups »** de l'issue [#46](https://github.com/reda253/fintech-mlops-lsi/issues/46). La clôture de l'issue complète nécessite également la livraison et la validation du **squelette React**.
