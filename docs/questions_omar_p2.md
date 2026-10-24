# Questions P2 pour Omar - 23/10/2026

Aucune modification du code P3 n'est effectuee pour cette preparation.

1. La spec 4.5 impose LogisticRegression, RandomForest, XGBoost,
   Nystroem + LinearSVC et MLPClassifier. L'endpoint performance utilise
   LightGBM a la place du SVM. Confirmes-tu l'alignement sur la spec et le nom
   de sortie du SVM ? Proposition : nystroem_svc en interne ; etiquette API SVM.
2. Confirmes-tu MultiLayerPerceptron comme etiquette API du modele interne mlp ?
3. Le handoff S6 est provisoire : tag provisional, sans champion automatique.
   Quel packaging veux-tu recevoir avant la validation statistique et conforme ?
4. Valider les contrats proposes folds.parquet (250 lignes) et
   repeat_means.parquet (50 lignes). Aucun lecteur de ces Parquet n'est etabli.
   Noms proposes : name, repeat, fold, seed, run_id, pr_auc, roc_auc,
   brier_score, log_loss, ece, precision, recall, f1, mcc, beta et effectifs.
5. Confirmer millisecondes pour inference_p50_ms / inference_p95_ms ; le
   squelette actuel emploie latency_p95_sec. Un adaptateur explicite est requis.
6. Les resultats et tests statistiques fixes du endpoint restent des mocks,
   jamais des resultats P2. Qui prend en charge leur remplacement par les
   artefacts reels et les controles des noms des cinq modeles ?

Sampler, delai par essai et adequation du decoupage restent ouverts dans
benchmark_requirements.md. Pas de calcul officiel ni de promotion ici.
