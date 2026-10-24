"""Verifie MLflow sans charger Sparkov ni entrainer de modele."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from ml.tracking_smoke import check_tracking_connection, get_tracking_uri


def main() -> int:
    """Affiche un resultat sans secret ; SQLite n'est jamais implicite."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tracking-uri")
    parser.add_argument("--allow-local-sqlite", action="store_true")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    try:
        uri = get_tracking_uri(
            args.tracking_uri, allow_local_sqlite=args.allow_local_sqlite
        )
    except ValueError as exc:
        print(
            json.dumps({"status": "UNVERIFIED", "reason": str(exc)}, ensure_ascii=True)
        )
        return 2
    result = check_tracking_connection(uri, timeout_seconds=args.timeout)
    result["backend"] = (
        "local_sqlite" if uri.startswith("sqlite:") else "configured_server"
    )
    if args.report is not None:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
