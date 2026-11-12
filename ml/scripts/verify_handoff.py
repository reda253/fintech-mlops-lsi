"""Replay P2's D44 synthetic cases against local, registry and HTTP models.

The handoff package is read from the ZIP directly; nothing is extracted. The
three official cases must match exactly (raw probability, rounded value,
prediction set and decision). A fake-threshold model covers ``[0, 1]``, which
cannot occur with the frozen D44 thresholds.

Usage:
    python -m ml.scripts.verify_handoff \
        --zip ~/Documents/d44_handoff_environment.zip \
        --tracking-uri http://localhost:5001 \
        --model-uri models:/fraud-detector/1 \
        --service-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ml.scripts.register_champion import build_model_from_payload
from ml.src.model.calibration import decide
from ml.src.model.fraud_detector import FraudDetectorModel

EXPECTED_ZIP_SHA256 = "4e5669f0e52c2d42e9fb6403f95049414722974056db8a4725b4775efb7b8a04"
EXPECTED_JOBLIB_SHA256 = "aa1565caf7fed3af833a5613fd76416b6489c9a9f31ee8c523d65e5d9113da33"
CASE_NAMES = ("legit", "fraud", "review")


class ParityError(AssertionError):
    """Raised when a replayed case diverges from P2's expected output."""


def _sha256(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def load_package(zip_path: Path) -> dict[str, Any]:
    """Read and verify the handoff ZIP without extracting it."""

    blob = Path(zip_path).read_bytes()
    zip_sha = _sha256(blob)
    if zip_sha != EXPECTED_ZIP_SHA256:
        raise ParityError(f"ZIP sha256 mismatch: {zip_sha} != {EXPECTED_ZIP_SHA256}")

    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        joblib_bytes = archive.read("candidate_model.joblib")
        joblib_sha = _sha256(joblib_bytes)
        if joblib_sha != EXPECTED_JOBLIB_SHA256:
            raise ParityError(
                f"joblib sha256 mismatch: {joblib_sha} != {EXPECTED_JOBLIB_SHA256}"
            )
        import joblib

        payload = joblib.load(io.BytesIO(joblib_bytes))
        metadata = json.loads(archive.read("metadata.json"))
        cases = json.loads(archive.read("synthetic_cases.json"))["cases"]

    if len(cases) != 3:
        raise ParityError(f"expected 3 synthetic cases, got {len(cases)}")
    return {
        "zip_sha256": zip_sha,
        "joblib_sha256": joblib_sha,
        "payload": payload,
        "metadata": metadata,
        "cases": cases,
    }


def build_local_model(package: dict[str, Any]) -> FraudDetectorModel:
    metadata = package["metadata"]
    return build_model_from_payload(
        package["payload"],
        alpha=float(metadata.get("alpha", 0.02)),
        git_commit=str(metadata.get("git_commit", "unknown")),
        data_sha256=str(metadata.get("data_sha256", "unknown")),
    )


def _check_case(name: str, expected: dict[str, Any], actual: dict[str, Any]) -> None:
    problems = []
    expected_raw = expected.get("raw_probability")
    if (
        expected_raw is not None
        and "raw_probability" in actual
        and abs(actual["raw_probability"] - expected_raw) > 1e-12
    ):
        problems.append(
            f"raw_probability {actual['raw_probability']!r} != {expected_raw!r}"
        )
    if actual.get("fraud_probability") != expected["fraud_probability"]:
        problems.append(
            f"fraud_probability {actual.get('fraud_probability')!r} "
            f"!= {expected['fraud_probability']!r}"
        )
    if list(actual.get("prediction_set", [])) != expected["prediction_set"]:
        problems.append(
            f"prediction_set {actual.get('prediction_set')!r} "
            f"!= {expected['prediction_set']!r}"
        )
    if actual.get("uncertainty") != expected["uncertainty"]:
        problems.append(
            f"uncertainty {actual.get('uncertainty')!r} != {expected['uncertainty']!r}"
        )
    if actual.get("decision") != expected["decision"]:
        problems.append(
            f"decision {actual.get('decision')!r} != {expected['decision']!r}"
        )
    if problems:
        raise ParityError(f"{name}: " + "; ".join(problems))


def verify_local(package: dict[str, Any]) -> list[dict[str, Any]]:
    model = build_local_model(package)
    results = []
    for name, case in zip(CASE_NAMES, package["cases"], strict=True):
        expected = case["expected"]
        output = model.predict_one(case["input"])
        actual = {
            **output,
            "raw_probability": model.calibrated_probability(case["input"]),
            "decision": decide(output["prediction_set"]),
        }
        _check_case(name, expected, actual)
        results.append({"case": name, **actual})
    return results


def verify_prediction_sets() -> dict[str, Any]:
    """Check ``[]`` passthrough and ``[0, 1]`` with synthetic thresholds."""

    class _ConstantClassifier:
        def predict_proba(self, features: pd.DataFrame) -> np.ndarray:
            return np.tile([0.95, 0.05], (len(features), 1))

    transaction = {
        "transaction_id": "00000000-0000-4000-8000-000000000000",
        "trans_datetime": "2020-06-01T02:00:00",
        "amount": 31.06,
        "category": "entertainment",
        "merch_lat": 40.1,
        "merch_long": -73.1,
        "customer": {
            "dob": "1980-01-01",
            "gender": "M",
            "state": "NY",
            "city_pop": 50000,
            "lat": 40.0,
            "long": -73.0,
        },
    }
    model = FraudDetectorModel(
        classifier=_ConstantClassifier(),
        threshold_legit=0.10,
        threshold_fraud=0.98,
        alpha=0.02,
    )
    full_set = model.predict_one(transaction)["prediction_set"]
    if full_set != [0, 1]:
        raise ParityError(f"fake-threshold model should yield [0, 1], got {full_set}")
    if decide(full_set) != "REVUE":
        raise ParityError("a [0, 1] set must map to REVUE")
    if decide([]) != "REVUE":
        raise ParityError("an empty set must map to REVUE")
    return {"full_set": full_set, "empty_decision": "REVUE"}


def _check_served_output(name: str, expected: dict[str, Any], output: dict[str, Any]) -> None:
    actual = {
        "fraud_probability": output.get("fraud_probability"),
        "prediction_set": list(output.get("prediction_set", [])),
        "uncertainty": output.get("uncertainty"),
        "decision": decide(list(output.get("prediction_set", []))),
        "alpha": output.get("alpha"),
    }
    if actual["fraud_probability"] != expected["fraud_probability"]:
        raise ParityError(
            f"{name}: served fraud_probability {actual['fraud_probability']!r} "
            f"!= {expected['fraud_probability']!r}"
        )
    if actual["prediction_set"] != expected["prediction_set"]:
        raise ParityError(
            f"{name}: served prediction_set {actual['prediction_set']!r} "
            f"!= {expected['prediction_set']!r}"
        )
    if actual["decision"] != expected["decision"]:
        raise ParityError(
            f"{name}: served decision {actual['decision']!r} != {expected['decision']!r}"
        )


def verify_pyfunc(
    model_uri: str,
    package: dict[str, Any],
    tracking_uri: str | None = None,
) -> list[dict[str, Any]]:
    import mlflow

    if tracking_uri:
        mlflow.set_tracking_uri(tracking_uri)
    loaded = mlflow.pyfunc.load_model(model_uri)
    results = []
    for name, case in zip(CASE_NAMES, package["cases"], strict=True):
        frame = pd.DataFrame([case["input"]])
        row = loaded.predict(frame).iloc[0].to_dict()
        _check_served_output(name, case["expected"], row)
        results.append({"case": name, **row})
    return results


def verify_service(base_url: str, package: dict[str, Any]) -> list[dict[str, Any]]:
    import urllib.request

    results = []
    for name, case in zip(CASE_NAMES, package["cases"], strict=True):
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/predict",
            data=json.dumps(case["input"]).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            row = json.loads(response.read())
        _check_served_output(name, case["expected"], row)
        results.append({"case": name, **row})
    return results


def verify_handoff(
    zip_path: Path,
    *,
    tracking_uri: str | None = None,
    model_uri: str | None = None,
    service_url: str | None = None,
) -> dict[str, Any]:
    package = load_package(zip_path)
    summary: dict[str, Any] = {
        "zip_sha256": package["zip_sha256"],
        "joblib_sha256": package["joblib_sha256"],
        "status": package["metadata"].get("status"),
        "alpha": package["metadata"].get("alpha"),
        "beta": package["metadata"].get("beta"),
        "local": verify_local(package),
        "sets": verify_prediction_sets(),
    }
    if model_uri:
        summary["pyfunc"] = verify_pyfunc(model_uri, package, tracking_uri)
    if service_url:
        summary["service"] = verify_service(service_url, package)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay P2's D44 handoff cases")
    parser.add_argument("--zip", type=Path, required=True)
    parser.add_argument("--tracking-uri", default=None)
    parser.add_argument("--model-uri", default=None)
    parser.add_argument("--service-url", default=None)
    args = parser.parse_args(argv)

    summary = verify_handoff(
        args.zip,
        tracking_uri=args.tracking_uri,
        model_uri=args.model_uri,
        service_url=args.service_url,
    )
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
