"""Chargement et decoupage chronologique du dataset Sparkov sans entrainement."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pandas as pd

TARGET_COLUMN = "is_fraud"
DATE_COLUMN = "trans_date_trans_time"
ID_COLUMN = "trans_num"
UNNAMED_COLUMN = "Unnamed: 0"
TRAIN_COLUMNS = [
    DATE_COLUMN, "cc_num", "amt", "category", "gender", "state",
    "city_pop", "lat", "long", "dob", "merch_lat", "merch_long",
    TARGET_COLUMN, ID_COLUMN,
]


@dataclass(frozen=True)
class DatasetSummary:
    """Resume simple d'un fichier Sparkov charge en memoire."""

    name: str
    rows: int
    columns: int
    fraud_rate: float


@dataclass(frozen=True)
class SplitSummary:
    """Resume d'une zone chronologique de fraudTrain.csv."""

    name: str
    rows: int
    fraud_count: int
    fraud_rate: float
    start_date: pd.Timestamp
    end_date: pd.Timestamp


@dataclass(frozen=True)
class IntegrityReport:
    """Resultats des controles d'integrite non destructifs."""

    is_chronologically_sorted: bool
    duplicate_rows: int
    trans_num_is_unique: bool | None
    trans_num_duplicates: int | None
    has_unnamed_column: bool
    distinct_counts: pd.Series


def load_sparkov_csv(path: str | Path) -> pd.DataFrame:
    """Charge un fichier CSV Sparkov et verifie la presence de la cible.

    Cette fonction ne modifie pas les donnees originales, ne supprime aucune
    colonne et ne lance aucune operation de preprocessing ou d'entrainement.
    """

    csv_path = Path(path)
    data = pd.read_csv(csv_path)
    validate_target_column(data, csv_path)
    return data


def validate_target_column(data: pd.DataFrame, source: str | Path) -> None:
    """Verifie que la colonne cible `is_fraud` existe dans le dataset."""

    if TARGET_COLUMN not in data.columns:
        raise ValueError(
            f"La colonne cible '{TARGET_COLUMN}' est absente du fichier {source}."
        )


def summarize_dataset(data: pd.DataFrame, name: str) -> DatasetSummary:
    """Retourne le nombre de lignes, colonnes et le taux de fraude."""

    validate_target_column(data, name)
    return DatasetSummary(
        name=name,
        rows=len(data),
        columns=len(data.columns),
        fraud_rate=float(data[TARGET_COLUMN].mean()),
    )


def load_training_dataset(path: str | Path) -> tuple[pd.DataFrame, DatasetSummary]:
    """Lit les champs autorises de fraudTrain, tries sans changer l'index source."""

    csv_path = Path(path)
    if csv_path.name != "fraudTrain.csv":
        raise ValueError("Ce chargeur accepte uniquement un fichier nomme fraudTrain.csv.")
    data = pd.read_csv(
        csv_path,
        usecols=TRAIN_COLUMNS,
        dtype={name: "category" for name in ["category", "gender", "state"]},
        parse_dates=[DATE_COLUMN, "dob"],
        date_format={DATE_COLUMN: "%Y-%m-%d %H:%M:%S", "dob": "%Y-%m-%d"},
    )
    validate_target_column(data, csv_path)
    for column in [DATE_COLUMN, "dob"]:
        if not pd.api.types.is_datetime64_any_dtype(data[column]):
            raise ValueError(f"Dates invalides ou format incorrect dans {column}.")
        if data[column].isna().any():
            raise ValueError(f"Dates manquantes dans {column}.")
    data = data.sort_values(DATE_COLUMN, kind="mergesort")
    return data, summarize_dataset(data, "fraudTrain.csv")


def load_final_test_dataset(path: str | Path) -> tuple[pd.DataFrame, DatasetSummary]:
    """Charge `fraudTest.csv`, reserve exclusivement au test final."""

    data = load_sparkov_csv(path)
    return data, summarize_dataset(data, "fraudTest.csv")


def parse_transaction_dates(data: pd.DataFrame) -> pd.Series:
    """Convertit les dates de transaction en levant une erreur si une date est invalide."""

    if DATE_COLUMN not in data.columns:
        raise ValueError(f"La colonne '{DATE_COLUMN}' est absente du dataset.")

    dates = pd.to_datetime(data[DATE_COLUMN], errors="coerce")
    invalid_count = int(dates.isna().sum())
    if invalid_count:
        raise ValueError(
            f"{invalid_count} valeur(s) de '{DATE_COLUMN}' sont non parsables."
        )
    return dates


def is_chronologically_sorted(data: pd.DataFrame) -> bool:
    """Indique si le dataset est deja trie par date de transaction croissante."""

    dates = parse_transaction_dates(data)
    return bool(dates.is_monotonic_increasing)


def split_chronologically(
    data: pd.DataFrame,
    dev_ratio: float = 0.70,
    proba_calibration_ratio: float = 0.15,
    conformal_calibration_ratio: float = 0.15,
    sort_if_needed: bool = False,
) -> dict[str, pd.DataFrame]:
    """Renvoie les zones dev, calibration proba et calibration conforme.

    Par defaut, le fichier doit deja etre trie chronologiquement. Si
    `sort_if_needed=True`, une copie triee en memoire est utilisee ; le fichier
    source et le DataFrame recu ne sont jamais modifies.
    """

    ratios = [Fraction(str(value)) for value in (
        dev_ratio, proba_calibration_ratio, conformal_calibration_ratio
    )]
    if any(ratio <= 0 for ratio in ratios):
        raise ValueError("Les ratios de decoupage doivent etre strictement positifs.")
    if sum(ratios) != 1:
        raise ValueError("La somme des ratios de decoupage doit etre egale a 1.")
    dev, proba, conformal = ratios
    assert dev + proba + conformal == 1
    working_data = data
    if not is_chronologically_sorted(data):
        if not sort_if_needed:
            raise ValueError(
                f"Le dataset n'est pas trie par '{DATE_COLUMN}'. "
                "Passe sort_if_needed=True seulement apres avoir signale ce point."
            )
        working_data = data.assign(
            __transaction_date=parse_transaction_dates(data)
        ).sort_values("__transaction_date", kind="mergesort").drop(
            columns="__transaction_date"
        )

    n_rows = len(working_data)
    dev_end = n_rows * dev.numerator // dev.denominator
    proba_end = dev_end + n_rows * proba.numerator // proba.denominator

    return {
        "development": working_data.iloc[:dev_end].copy(),
        "probability_calibration": working_data.iloc[dev_end:proba_end].copy(),
        "conformal_calibration": working_data.iloc[proba_end:].copy(),
    }


def summarize_split(name: str, data: pd.DataFrame) -> SplitSummary:
    """Calcule les bornes temporelles, effectifs et taux de fraude d'une zone."""

    validate_target_column(data, name)
    dates = parse_transaction_dates(data)
    fraud_count = int(data[TARGET_COLUMN].sum())
    return SplitSummary(
        name=name,
        rows=len(data),
        fraud_count=fraud_count,
        fraud_rate=float(data[TARGET_COLUMN].mean()),
        start_date=dates.min(),
        end_date=dates.max(),
    )


def summarize_splits(splits: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Retourne un tableau de synthese pour les zones chronologiques."""

    rows = []
    for name, split_data in splits.items():
        summary = summarize_split(name, split_data)
        rows.append(
            {
                "zone": summary.name,
                "start_date": summary.start_date,
                "end_date": summary.end_date,
                "rows": summary.rows,
                "fraud_count": summary.fraud_count,
                "fraud_rate": summary.fraud_rate,
            }
        )
    return pd.DataFrame(rows)


def check_integrity(data: pd.DataFrame) -> IntegrityReport:
    """Effectue des controles d'integrite sans modifier le dataset."""

    duplicate_rows = int(data.duplicated().sum())
    if ID_COLUMN in data.columns:
        trans_num_duplicates = int(data[ID_COLUMN].duplicated().sum())
        trans_num_is_unique = trans_num_duplicates == 0
    else:
        trans_num_duplicates = None
        trans_num_is_unique = None

    return IntegrityReport(
        is_chronologically_sorted=is_chronologically_sorted(data),
        duplicate_rows=duplicate_rows,
        trans_num_is_unique=trans_num_is_unique,
        trans_num_duplicates=trans_num_duplicates,
        has_unnamed_column=UNNAMED_COLUMN in data.columns,
        distinct_counts=data.nunique(dropna=False).sort_values(ascending=False),
    )


def print_dataset_summary(summary: DatasetSummary) -> None:
    """Affiche clairement les dimensions du dataset et son taux de fraude."""

    print(f"Dataset : {summary.name}")
    print(f"Lignes : {summary.rows}")
    print(f"Colonnes : {summary.columns}")
    print(f"Taux de fraude : {summary.fraud_rate:.6f}")

