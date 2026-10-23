"""Construit des classifieurs non ajustes ; aucun acces aux donnees sources."""

from numbers import Integral

from benchmark.config import MODEL_NAMES
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.kernel_approximation import Nystroem
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from xgboost import XGBClassifier

ALLOWED = {
    "logreg": {"C", "solver", "max_iter", "tol", "fit_intercept"},
    "rf": {
        "n_estimators",
        "max_depth",
        "min_samples_leaf",
        "min_samples_split",
        "max_features",
    },
    "xgb": {
        "n_estimators",
        "max_depth",
        "learning_rate",
        "subsample",
        "colsample_bytree",
        "min_child_weight",
        "reg_alpha",
        "reg_lambda",
        "tree_method",
        "objective",
        "eval_metric",
    },
    "nystroem_svc": {
        "C",
        "gamma",
        "n_components",
        "kernel",
        "max_iter",
        "tol",
        "calibration_cv",
    },
    "mlp": {
        "hidden_layer_sizes",
        "alpha",
        "learning_rate_init",
        "max_iter",
        "early_stopping",
        "solver",
        "validation_fraction",
        "n_iter_no_change",
        "tol",
    },
}


def build_model(name, params, seed):
    """Renvoie un modele a predict_proba, sans ponderation des classes.

    Le SVM calibre par CV sigmoide sur les seules lignes passees a fit ; la
    transformation Nystroem est elle aussi re-ajustee dans chaque sous-pli.
    Le preprocessing et le sous-echantillonnage restent dans make_fold_data.
    """
    if name not in MODEL_NAMES:
        raise ValueError(f"Modele inconnu : {name}. Attendus : {MODEL_NAMES}")
    if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
        raise ValueError("seed doit etre un entier positif ou nul.")
    if not isinstance(params, dict):
        raise TypeError("params doit etre un dictionnaire.")
    p = dict(params)
    unknown = set(p) - ALLOWED[name]
    if unknown:
        raise ValueError(f"Parametres interdits pour {name} : {sorted(unknown)}")
    seed = int(seed)
    if name == "logreg":
        return LogisticRegression(random_state=seed, **p)
    if name == "rf":
        return RandomForestClassifier(random_state=seed, n_jobs=1, **p)
    if name == "xgb":
        fixed = {
            "tree_method": "hist",
            "objective": "binary:logistic",
            "eval_metric": "logloss",
        }
        for key, value in fixed.items():
            if p.pop(key, value) != value:
                raise ValueError(f"xgb.{key} doit rester {value}.")
        return XGBClassifier(random_state=seed, n_jobs=1, device="cpu", **fixed, **p)
    if name == "mlp":
        if p.pop("early_stopping", True) is not True:
            raise ValueError("MLP : early_stopping=True est obligatoire.")
        if "hidden_layer_sizes" in p:
            p["hidden_layer_sizes"] = tuple(p["hidden_layer_sizes"])
        return MLPClassifier(random_state=seed, early_stopping=True, **p)
    calibration_cv = p.pop("calibration_cv", 3)
    if (
        isinstance(calibration_cv, bool)
        or not isinstance(calibration_cv, Integral)
        or calibration_cv < 2
    ):
        raise ValueError("calibration_cv doit etre un entier >= 2.")
    feature_map = Nystroem(
        random_state=seed,
        n_jobs=1,
        kernel=p.pop("kernel", "rbf"),
        gamma=p.pop("gamma", None),
        n_components=p.pop("n_components", 100),
    )
    estimator = Pipeline(
        [("nystroem", feature_map), ("svc", LinearSVC(random_state=seed, **p))]
    )
    return CalibratedClassifierCV(
        estimator=estimator,
        method="sigmoid",
        n_jobs=1,
        ensemble=False,
        cv=StratifiedKFold(
            n_splits=int(calibration_cv), shuffle=True, random_state=seed
        ),
    )
