"""Pipeline de preprocessing Sparkov pour P2.

Le module ne contient aucun modele de classification. Il transforme les champs
bruts en features utilisables par les futurs benchmarks, avec validations
explicites pour eviter les erreurs silencieuses entre entrainement et service.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.utils.validation import check_is_fitted

TARGET_COLUMN = "is_fraud"
DATE_COLUMN = "trans_date_trans_time"
DOB_COLUMN = "dob"
TRANSACTION_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DOB_DATE_FORMAT = "%Y-%m-%d"

REQUIRED_COLUMNS = [
    DATE_COLUMN,
    DOB_COLUMN,
    "amt",
    "category",
    "gender",
    "state",
    "city_pop",
    "lat",
    "long",
    "merch_lat",
    "merch_long",
]

NUMERIC_REQUIRED_COLUMNS = ["amt", "city_pop", "lat", "long", "merch_lat", "merch_long"]
CATEGORICAL_REQUIRED_COLUMNS = ["category", "gender", "state"]
ENGINEERED_FEATURE_NAMES = np.array(
    [
        "amount_log",
        "hour_sin",
        "hour_cos",
        "day_of_week_sin",
        "day_of_week_cos",
        "is_weekend",
        "is_night",
        "age",
        "distance_km",
        "city_pop_log",
        "gender",
        "category",
        "state",
        "hour",
    ],
    dtype=object,
)
NUMERIC_ENGINEERED_FEATURES = [
    "amount_log",
    "hour_sin",
    "hour_cos",
    "day_of_week_sin",
    "day_of_week_cos",
    "is_weekend",
    "is_night",
    "age",
    "distance_km",
    "city_pop_log",
]
CATEGORICAL_ENGINEERED_FEATURES = ["gender", "category", "state"]
CONTINUOUS_FEATURES = ["amount_log", "age", "distance_km", "city_pop_log"]
UNSCALED_FEATURES = [
    name for name in NUMERIC_ENGINEERED_FEATURES if name not in CONTINUOUS_FEATURES
]

EXCLUDED_COLUMNS = {
    "Unnamed: 0": "colonne parasite d'index CSV",
    "trans_num": "identifiant de transaction, reserve a l'idempotence",
    "cc_num": "identifiant carte, hache cote customer-service",
    "unix_time": "identifiant temporel redondant avec trans_date_trans_time",
    "first": "donnee personnelle exclue",
    "last": "donnee personnelle exclue",
    "street": "donnee personnelle exclue",
    "zip": "donnee personnelle exclue",
    "merchant": "forte cardinalite, risque de sur-apprentissage",
    "job": "forte cardinalite, risque de sur-apprentissage",
    "city": "forte cardinalite, moins stable que state",
}

RAW_INPUT_SPECS = [
    (DATE_COLUMN, "datetime string", "format %Y-%m-%d %H:%M:%S, temps local naïf sans conversion"),
    (DOB_COLUMN, "date string", "format %Y-%m-%d"),
    ("amt", "float", "montant >= 0, source de amount_log"),
    ("category", "string", "categorie transactionnelle encodee"),
    ("gender", "string", "genre conserve pour feature et audit"),
    ("state", "string", "etat encode"),
    ("city_pop", "integer", "population >= 0, source de city_pop_log"),
    ("lat", "float", "latitude client dans [-90, 90]"),
    ("long", "float", "longitude client dans [-180, 180]"),
    ("merch_lat", "float", "latitude marchand dans [-90, 90]"),
    ("merch_long", "float", "longitude marchand dans [-180, 180]"),
]


@dataclass(frozen=True)
class FeatureSpec:
    """Description versionnable d'une feature finale ou derivee."""

    name: str
    kind: str
    transformation: str
    justification: str
    scaled: bool = False


FEATURE_SPECS = [
    FeatureSpec("amount_log", "numeric", "log1p(amt)", "Montant asymetrique.", True),
    FeatureSpec("hour_sin", "numeric", "sin(2*pi*hour/24)", "Circularite; sans standardisation."),
    FeatureSpec("hour_cos", "numeric", "cos(2*pi*hour/24)", "Circularite; sans standardisation."),
    FeatureSpec("day_of_week_sin", "numeric", "sin(2*pi*dow/7)", "Circularite; sans standardisation."),
    FeatureSpec("day_of_week_cos", "numeric", "cos(2*pi*dow/7)", "Circularite; sans standardisation."),
    FeatureSpec("is_weekend", "binary", "day_of_week in {5,6}", "Indicateur 0/1 sans standardisation."),
    FeatureSpec("is_night", "binary", "hour in {22,23,0,1,2,3}", "Palier horaire et rappel des fraudes; indicateur 0/1."),
    FeatureSpec("age", "numeric", "annees revolues a la transaction", "Age entier pour reduire la precision identifiante.", True),
    FeatureSpec("distance_km", "numeric", "haversine client-marchand", "Distance transactionnelle.", True),
    FeatureSpec("city_pop_log", "numeric", "log1p(city_pop)", "Population asymetrique.", True),
    FeatureSpec("gender", "categorical", "OneHotEncoder(handle_unknown=ignore, drop=if_binary)", "Conserve, avec audit d'equite.", False),
    FeatureSpec("category", "categorical", "OneHotEncoder(handle_unknown=ignore)", "Cardinalite faible.", False),
    FeatureSpec("state", "categorical", "OneHotEncoder(handle_unknown=ignore)", "Cardinalite moderee sur Sparkov.", False),
    FeatureSpec("hour", "categorical", "OneHotEncoder(categories=0..23) optionnel", "Option pour effets horaires non sinusoidaux."),
]


def _ensure_no_missing_or_infinite(data: pd.DataFrame) -> None:
    missing = data[REQUIRED_COLUMNS].isna().sum()
    missing = missing[missing > 0]
    if not missing.empty:
        raise ValueError(f"Valeurs manquantes detectees: {missing.to_dict()}")

    numeric = data[NUMERIC_REQUIRED_COLUMNS].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any():
        bad = numeric.columns[numeric.isna().any()].tolist()
        raise ValueError(f"Colonnes numeriques non convertibles: {bad}")
    if not np.isfinite(numeric.to_numpy(dtype="float64")).all():
        raise ValueError("Valeur infinie detectee dans les colonnes numeriques requises.")

    for column in CATEGORICAL_REQUIRED_COLUMNS:
        if (data[column].astype("string").str.len() == 0).any():
            raise ValueError(f"Modalite vide detectee dans la colonne {column}.")


def _parse_datetime_strict(values: pd.Series, column: str, fmt: str) -> pd.Series:
    """Parse une colonne datetime naïve avec format exact, sans conversion de fuseau."""

    try:
        parsed = pd.to_datetime(values, format=fmt, errors="raise")
        if parsed.dt.tz is not None or parsed.isna().any():
            raise ValueError("Dates locales naives requises.")
        return parsed
    except Exception as exc:  # pandas renvoie plusieurs types selon l'erreur
        raise ValueError(f"Colonne {column}: format attendu {fmt}.") from exc


def haversine_km(lat1, lon1, lat2, lon2):
    """Calcule la distance haversine en kilometres avec bornage numerique."""

    radius = 6371.0
    lat1 = np.radians(lat1.astype("float64"))
    lon1 = np.radians(lon1.astype("float64"))
    lat2 = np.radians(lat2.astype("float64"))
    lon2 = np.radians(lon2.astype("float64"))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    a = np.clip(a, 0, 1)
    return 2 * radius * np.arcsin(np.sqrt(a))


class SparkovFeatureEngineer(BaseEstimator, TransformerMixin):
    """Cree les features derivees a partir des champs bruts Sparkov."""

    def __init__(self, night_hours: Iterable[int] = (22, 23, 0, 1, 2, 3)):
        self.night_hours = tuple(night_hours)

    def fit(self, X, y=None):
        self._validate_input(X)
        return self

    def transform(self, X):
        self._validate_input(X)
        data = X.copy()
        transaction_dates = _parse_datetime_strict(data[DATE_COLUMN], DATE_COLUMN, TRANSACTION_DATETIME_FORMAT)
        birth_dates = _parse_datetime_strict(data[DOB_COLUMN], DOB_COLUMN, DOB_DATE_FORMAT)

        numeric = data[NUMERIC_REQUIRED_COLUMNS].apply(pd.to_numeric, errors="raise")
        if (numeric["amt"] < 0).any():
            raise ValueError("La colonne amt contient au moins un montant negatif.")
        if (numeric["city_pop"] < 0).any():
            raise ValueError("La colonne city_pop contient au moins une valeur negative.")
        self._validate_geo_ranges(numeric)

        hour = transaction_dates.dt.hour.astype("int16")
        day_of_week = transaction_dates.dt.dayofweek.astype("int16")
        before_birthday = (
            (transaction_dates.dt.month < birth_dates.dt.month)
            | ((transaction_dates.dt.month == birth_dates.dt.month)
               & (transaction_dates.dt.day < birth_dates.dt.day))
        )
        age = (transaction_dates.dt.year - birth_dates.dt.year
               - before_birthday.astype(int)).astype("float32")
        if ((age < 0) | (age > 120)).any():
            raise ValueError("Age aberrant detecte hors de l'intervalle [0, 120].")

        distance = haversine_km(numeric["lat"], numeric["long"], numeric["merch_lat"], numeric["merch_long"])
        result = pd.DataFrame(index=data.index)
        result["amount_log"] = np.log1p(numeric["amt"]).astype("float32")
        result["hour_sin"] = np.sin(2 * np.pi * hour / 24).astype("float32")
        result["hour_cos"] = np.cos(2 * np.pi * hour / 24).astype("float32")
        result["day_of_week_sin"] = np.sin(2 * np.pi * day_of_week / 7).astype("float32")
        result["day_of_week_cos"] = np.cos(2 * np.pi * day_of_week / 7).astype("float32")
        result["is_weekend"] = day_of_week.isin([5, 6]).astype("int8")
        result["is_night"] = hour.isin(self.night_hours).astype("int8")
        result["age"] = age
        result["distance_km"] = distance.astype("float32")
        result["city_pop_log"] = np.log1p(numeric["city_pop"]).astype("float32")
        result["gender"] = data["gender"].astype("string")
        result["category"] = data["category"].astype("string")
        result["state"] = data["state"].astype("string")
        result["hour"] = hour
        return result

    def get_feature_names_out(self, input_features=None):
        """Retourne les noms des colonnes produites par ce transformeur."""

        return ENGINEERED_FEATURE_NAMES.copy()

    @staticmethod
    def _validate_geo_ranges(numeric: pd.DataFrame) -> None:
        for column in ["lat", "merch_lat"]:
            if ((numeric[column] < -90) | (numeric[column] > 90)).any():
                raise ValueError(f"{column} hors de l'intervalle [-90, 90].")
        for column in ["long", "merch_long"]:
            if ((numeric[column] < -180) | (numeric[column] > 180)).any():
                raise ValueError(f"{column} hors de l'intervalle [-180, 180].")

    @staticmethod
    def _validate_input_columns(X) -> None:
        missing = [column for column in REQUIRED_COLUMNS if column not in X.columns]
        if missing:
            raise ValueError(f"Colonnes manquantes pour le preprocessing: {missing}")

    def _validate_input(self, X) -> None:
        self._validate_input_columns(X)
        _ensure_no_missing_or_infinite(X)


def _record_missing_message(missing_columns: list[str]) -> str:
    return "Valeurs manquantes detectees: {" + ", ".join(f"'{name}': 1" for name in missing_columns) + "}"


def _parse_record_datetime(value, column: str, fmt: str) -> datetime:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        raise ValueError(_record_missing_message([column]))
    try:
        if isinstance(value, (datetime, pd.Timestamp)):
            if value.tzinfo is not None:
                raise ValueError("Date avec fuseau refusee.")
            return value.to_pydatetime() if isinstance(value, pd.Timestamp) else value
        parsed = datetime.strptime(str(value), fmt)
        if parsed.strftime(fmt) != str(value):
            raise ValueError("Format non exact.")
        return parsed
    except Exception as exc:
        raise ValueError(f"Colonne {column}: format attendu {fmt}.") from exc


def _record_float(record: dict, column: str) -> float:
    value = record.get(column)
    if value is None or pd.isna(value):
        raise ValueError(_record_missing_message([column]))
    try:
        number = float(value)
    except Exception as exc:
        raise ValueError(f"Colonnes numeriques non convertibles: ['{column}']") from exc
    if not math.isfinite(number):
        raise ValueError("Valeur infinie detectee dans les colonnes numeriques requises.")
    return number


def _record_str(record: dict, column: str) -> str:
    value = record.get(column)
    if value is None or pd.isna(value):
        raise ValueError(_record_missing_message([column]))
    text = str(value)
    if len(text) == 0:
        raise ValueError(f"Modalite vide detectee dans la colonne {column}.")
    return text


def _validate_record_columns(record: dict) -> None:
    missing = [column for column in REQUIRED_COLUMNS if column not in record]
    if missing:
        raise ValueError(f"Colonnes manquantes pour le preprocessing: {missing}")


def _haversine_one(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(min(1.0, max(0.0, a))))


def _engineer_record(record: dict, night_hours: tuple[int, ...]) -> tuple[list[float], list[str]]:
    _validate_record_columns(record)
    transaction_date = _parse_record_datetime(record[DATE_COLUMN], DATE_COLUMN, TRANSACTION_DATETIME_FORMAT)
    birth_date = _parse_record_datetime(record[DOB_COLUMN], DOB_COLUMN, DOB_DATE_FORMAT)

    amt = _record_float(record, "amt")
    city_pop = _record_float(record, "city_pop")
    lat = _record_float(record, "lat")
    lon = _record_float(record, "long")
    merch_lat = _record_float(record, "merch_lat")
    merch_lon = _record_float(record, "merch_long")
    category = _record_str(record, "category")
    gender = _record_str(record, "gender")
    state = _record_str(record, "state")

    if amt < 0:
        raise ValueError("La colonne amt contient au moins un montant negatif.")
    if city_pop < 0:
        raise ValueError("La colonne city_pop contient au moins une valeur negative.")
    for column, value in (("lat", lat), ("merch_lat", merch_lat)):
        if value < -90 or value > 90:
            raise ValueError(f"{column} hors de l'intervalle [-90, 90].")
    for column, value in (("long", lon), ("merch_long", merch_lon)):
        if value < -180 or value > 180:
            raise ValueError(f"{column} hors de l'intervalle [-180, 180].")

    age = transaction_date.year - birth_date.year - (
        (transaction_date.month, transaction_date.day) < (birth_date.month, birth_date.day)
    )
    if age < 0 or age > 120:
        raise ValueError("Age aberrant detecte hors de l'intervalle [0, 120].")

    hour = transaction_date.hour
    day_of_week = transaction_date.weekday()
    numeric = [
        math.log1p(amt),
        math.sin(2 * math.pi * hour / 24),
        math.cos(2 * math.pi * hour / 24),
        math.sin(2 * math.pi * day_of_week / 7),
        math.cos(2 * math.pi * day_of_week / 7),
        1.0 if day_of_week in (5, 6) else 0.0,
        1.0 if hour in night_hours else 0.0,
        age,
        _haversine_one(lat, lon, merch_lat, merch_lon),
        math.log1p(city_pop),
    ]
    return numeric, [gender, category, state]


def _transform_one_with_fitted_pipeline(pipeline: Pipeline, record: dict) -> np.ndarray:
    feature_step = pipeline.named_steps["features"]
    column_step = pipeline.named_steps["columns"]
    check_is_fitted(column_step)
    numeric_values, categorical_values = _engineer_record(record, tuple(feature_step.night_hours))

    numeric_by_name = dict(zip(NUMERIC_ENGINEERED_FEATURES, numeric_values))
    numeric_transformer = column_step.named_transformers_["numeric"]
    numeric_output = np.asarray([numeric_by_name[name] for name in CONTINUOUS_FEATURES], dtype=np.float32)
    if isinstance(numeric_transformer, StandardScaler):
        numeric_output -= numeric_transformer.mean_
        numeric_output /= numeric_transformer.scale_
    unscaled = np.asarray([numeric_by_name[name] for name in UNSCALED_FEATURES], dtype=np.float32)

    categorical_parts = [numeric_output, unscaled]
    for transformer_name, values in [
        ("gender", categorical_values[:1]), ("categorical", categorical_values[1:])
    ]:
        encoder = column_step.named_transformers_[transformer_name]
        for i, (value, categories) in enumerate(zip(values, encoder.categories_)):
            encoded = np.asarray(categories == value, dtype=np.float32)
            if encoder.drop_idx_ is not None and encoder.drop_idx_[i] is not None:
                encoded = np.delete(encoded, int(encoder.drop_idx_[i]))
            categorical_parts.append(encoded)
    if "hour" in column_step.named_transformers_:
        categories = column_step.named_transformers_["hour"].categories_[0]
        hour = _parse_record_datetime(record[DATE_COLUMN], DATE_COLUMN, TRANSACTION_DATETIME_FORMAT).hour
        encoded = np.zeros(len(categories), dtype=np.float32)
        matches = np.flatnonzero(categories == hour)
        if matches.size:
            encoded[int(matches[0])] = 1.0
        categorical_parts.append(encoded)
    return np.concatenate(categorical_parts).astype(np.float32)


def split_features_target(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Separe strictement X et y sans modifier le DataFrame source."""

    if TARGET_COLUMN not in data.columns:
        raise ValueError(f"La colonne cible {TARGET_COLUMN} est absente.")
    return data.drop(columns=[TARGET_COLUMN]), data[TARGET_COLUMN].copy()


class SparkovPreprocessingPipeline(Pipeline):
    """Pipeline sklearn avec chemin serving rapide pour une transaction."""

    def transform_one(self, record: dict) -> np.ndarray:
        """Transforme une transaction déjà en dictionnaire avec les paramètres ajustés."""

        return _transform_one_with_fitted_pipeline(self, record)


def build_preprocessing_pipeline(
    scale_numeric: bool = True, hour_onehot: bool = False
) -> Pipeline:
    """Construit le pipeline sklearn de preprocessing."""

    numeric_transformer = StandardScaler() if scale_numeric else "passthrough"
    encoder = OneHotEncoder(handle_unknown="ignore", sparse_output=False, dtype=np.float32)
    transformers = [
        ("numeric", numeric_transformer, CONTINUOUS_FEATURES),
        ("unscaled", "passthrough", UNSCALED_FEATURES),
        ("gender", OneHotEncoder(handle_unknown="ignore", drop="if_binary",
                                 sparse_output=False, dtype=np.float32), ["gender"]),
        ("categorical", encoder, ["category", "state"]),
    ]
    if hour_onehot:
        transformers.append((
            "hour", OneHotEncoder(categories=[np.arange(24)], handle_unknown="ignore",
                                  sparse_output=False, dtype=np.float32), ["hour"]
        ))
    column_transformer = ColumnTransformer(
        transformers=transformers,
        remainder="drop",
        verbose_feature_names_out=True,
    )
    return SparkovPreprocessingPipeline(steps=[("features", SparkovFeatureEngineer()), ("columns", column_transformer)])


def get_excluded_columns() -> dict[str, str]:
    """Retourne les colonnes exclues et leur justification."""

    return dict(EXCLUDED_COLUMNS)


def get_raw_input_specs() -> list[tuple[str, str, str]]:
    """Retourne les champs bruts attendus: nom, type et usage."""

    return list(RAW_INPUT_SPECS)

