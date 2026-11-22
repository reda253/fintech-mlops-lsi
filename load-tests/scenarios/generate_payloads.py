#!/usr/bin/env python3
"""Build fixed POST /predict payloads from the Sparkov development block.

The final test set is reserved for the D48 measurement: this script refuses
``fraudTest.csv`` before opening it, and only samples the earliest 70 % of
``fraudTrain.csv`` (the development zone), exactly like the pipeline's latency
measurement.

Standard library only, so it runs with the system Python:

    python3 generate_payloads.py --source ~/d48-data/data/raw/fraudTrain.csv \
        --output payloads.json --sample-size 500
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from pathlib import Path
from uuid import uuid4

CATEGORIES = {
    "entertainment",
    "food_dining",
    "gas_transport",
    "grocery_net",
    "grocery_pos",
    "health_fitness",
    "home",
    "kids_pets",
    "misc_net",
    "misc_pos",
    "personal_care",
    "shopping_net",
    "shopping_pos",
    "travel",
}

REQUIRED_COLUMNS = (
    "trans_date_trans_time",
    "amt",
    "category",
    "merch_lat",
    "merch_long",
    "dob",
    "gender",
    "city_pop",
    "lat",
    "long",
    "state",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        required=True,
        help="Full fraudTrain.csv (the development dataset, never fraudTest.csv).",
    )
    parser.add_argument("--output", type=Path, default=Path("payloads.json"))
    parser.add_argument("--sample-size", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--development-share",
        type=float,
        default=0.70,
        help="Earliest share of rows kept as the development block (default 0.70).",
    )
    return parser.parse_args(argv)


def resolve_source(path: Path) -> Path:
    """Only the full development dataset is accepted, whatever the casing."""

    source = path.expanduser()
    if source.name.lower() != "fraudtrain.csv":
        raise SystemExit(
            f"refus: seul fraudTrain.csv est accepte (recu {source.name!r}) ; "
            "fraudTest.csv est reserve a la mesure D48"
        )
    if not source.is_file():
        raise SystemExit(f"source absente: {source}")
    return source


def development_indices(dates: list[str], share: float) -> set[int]:
    """Indices of the canonical chronological development block.

    The split is by position, not by date value: with identical timestamps on
    the boundary, comparing timestamps would keep more than ``share`` of the
    rows. Ties are broken by original row order, so the result is deterministic.
    """

    if not 0.0 < share < 1.0:
        raise ValueError("share doit etre dans ]0, 1[")
    if not dates:
        raise ValueError("aucune date fournie")
    count = int(len(dates) * share)
    if count <= 0:
        raise ValueError("share laisse un bloc de developpement vide")
    ordered = sorted(range(len(dates)), key=lambda index: (dates[index], index))
    return set(ordered[:count])


def to_payload(row: dict[str, str]) -> dict | None:
    category = row["category"].strip()
    if category not in CATEGORIES:
        return None
    try:
        amount = float(row["amt"])
        city_pop = int(float(row["city_pop"]))
        payload = {
            "transaction_id": str(uuid4()),
            "trans_datetime": row["trans_date_trans_time"].strip().replace(" ", "T"),
            "amount": amount,
            "category": category,
            "merch_lat": float(row["merch_lat"]),
            "merch_long": float(row["merch_long"]),
            "customer": {
                "dob": row["dob"].strip()[:10],
                "gender": row["gender"].strip(),
                "city_pop": city_pop,
                "lat": float(row["lat"]),
                "long": float(row["long"]),
                "state": row["state"].strip(),
            },
        }
    except (TypeError, ValueError):
        return None
    if amount <= 0 or payload["customer"]["gender"] not in {"M", "F"}:
        return None
    return payload


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    source = resolve_source(args.source)
    output = args.output.expanduser()

    if output.resolve() == source.resolve():
        raise SystemExit("refus: --output identique a --source ecraserait le CSV")
    if not 0.0 < args.development_share < 1.0:
        raise SystemExit("--development-share doit etre dans ]0, 1[")
    if args.sample_size <= 0:
        raise SystemExit("--sample-size doit etre positif")

    dates: list[str] = []
    with source.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"colonnes absentes du fichier source: {missing}")
        for row in reader:
            dates.append(row["trans_date_trans_time"])
    if not dates:
        raise SystemExit("fichier source vide")

    try:
        development = development_indices(dates, args.development_share)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    cutoff = max(dates[index] for index in development)

    rng = random.Random(args.seed)
    reservoir: list[dict] = []
    seen = 0
    with source.open(newline="", encoding="utf-8") as stream:
        for index, row in enumerate(csv.DictReader(stream)):
            if index not in development:
                continue
            payload = to_payload(row)
            if payload is None:
                continue
            seen += 1
            if len(reservoir) < args.sample_size:
                reservoir.append(payload)
            else:
                slot = rng.randrange(seen)
                if slot < args.sample_size:
                    reservoir[slot] = payload

    if len(reservoir) < args.sample_size:
        raise SystemExit(
            f"seulement {len(reservoir)} lignes exploitables, {args.sample_size} demandees"
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(reservoir, indent=2) + "\n", encoding="utf-8")

    sampled = sorted(p["trans_datetime"] for p in reservoir)
    print(f"source        {source} ({len(dates)} lignes)")
    print(f"development   {len(development)} lignes, cutoff {cutoff}")
    print(f"candidates    {seen}")
    print(f"payloads      {len(reservoir)} -> {output}")
    print(f"date range    {sampled[0]} .. {sampled[-1]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
