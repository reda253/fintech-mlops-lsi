"""Tests for the k6 payload generator (development block only, no final test)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scenarios" / "generate_payloads.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("generate_payloads", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


generate_payloads = _load_module()

HEADER = [
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
]


def _row(datetime_value: str, amount: float = 42.5, category: str = "shopping_net"):
    return [
        datetime_value,
        amount,
        category,
        "40.1",
        "-73.1",
        "1985-04-12",
        "F",
        "125000",
        "40.0",
        "-73.0",
        "NY",
    ]


def _write_csv(path: Path, rows):
    path.write_text(
        ",".join(HEADER)
        + "\n"
        + "\n".join(",".join(str(value) for value in row) for row in rows)
        + "\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "name", ["fraudTest.csv", "FRAUDTEST.CSV", "FraudTest.Csv", "fraud_test.csv"]
)
def test_refuses_any_file_that_is_not_the_development_set(tmp_path, name):
    candidate = tmp_path / name
    candidate.write_text("x", encoding="utf-8")

    with pytest.raises(SystemExit, match="fraudTrain.csv"):
        generate_payloads.main(
            ["--source", str(candidate), "--output", str(tmp_path / "out.json")]
        )


def test_refuses_the_final_test_before_opening_it(tmp_path):
    final_test = tmp_path / "FRAUDTEST.CSV"
    final_test.write_text("contenu", encoding="utf-8")

    with pytest.raises(SystemExit, match="fraudTrain.csv"):
        generate_payloads.main(
            ["--source", str(final_test), "--output", str(tmp_path / "out.json")]
        )
    assert final_test.read_text(encoding="utf-8") == "contenu"


def test_accepts_the_development_set_whatever_the_case(tmp_path):
    source = _write_csv(
        tmp_path / "FraudTrain.CSV",
        [_row(f"2020-01-0{day}T10:00:00") for day in range(1, 10)],
    )

    assert (
        generate_payloads.main(
            [
                "--source",
                str(source),
                "--output",
                str(tmp_path / "out.json"),
                "--sample-size",
                "3",
            ]
        )
        == 0
    )


def test_missing_source_is_reported(tmp_path):
    with pytest.raises(SystemExit, match="absente"):
        generate_payloads.main(
            ["--source", str(tmp_path / "fraudTrain.csv"), "--output", "out.json"]
        )


def test_output_cannot_overwrite_the_source(tmp_path):
    source = _write_csv(tmp_path / "fraudTrain.csv", [_row("2020-01-01T10:00:00")])

    with pytest.raises(SystemExit, match="identique"):
        generate_payloads.main(["--source", str(source), "--output", str(source)])


def test_development_block_is_selected_by_position_not_by_date():
    identical = ["2020-01-01 10:00:00"] * 10

    indices = generate_payloads.development_indices(identical, 0.70)

    assert indices == set(range(7)), "les dates identiques ne doivent pas deborder"


def test_development_block_breaks_ties_by_row_order():
    dates = ["b", "a", "b", "a"]

    # sorted by (date, original index): a0, a1, b2, b3 -> first two rows are {1, 3}
    assert generate_payloads.development_indices(dates, 0.5) == {1, 3}


def test_development_share_must_leave_rows():
    with pytest.raises(ValueError, match="vide"):
        generate_payloads.development_indices(["2020-01-01"], 0.10)


def test_generates_contract_shaped_payloads_from_the_development_block(tmp_path):
    rows = [
        _row(f"2020-01-01T10:{minute:02d}:00", amount=10.0 + minute)
        for minute in range(10)
    ] + [
        _row(f"2020-02-01T10:{minute:02d}:00", amount=100.0 + minute)
        for minute in range(10)
    ]
    source = _write_csv(tmp_path / "fraudTrain.csv", rows)
    output = tmp_path / "payloads.json"

    assert (
        generate_payloads.main(
            [
                "--source",
                str(source),
                "--output",
                str(output),
                "--sample-size",
                "6",
                "--seed",
                "7",
                "--development-share",
                "0.5",
            ]
        )
        == 0
    )

    payloads = json.loads(output.read_text(encoding="utf-8"))
    assert len(payloads) == 6
    for payload in payloads:
        assert payload["category"] in generate_payloads.CATEGORIES
        assert payload["amount"] > 0
        assert payload["trans_datetime"].startswith("2020-01-01T")
        assert set(payload["customer"]) == {
            "dob",
            "gender",
            "city_pop",
            "lat",
            "long",
            "state",
        }
        assert payload["customer"]["gender"] in {"M", "F"}


def test_skips_rows_that_do_not_fit_the_contract(tmp_path):
    rows = [
        _row("2020-01-01T10:00:00", category="unknown_category"),
        _row("2020-01-01T11:00:00", amount=0.0),
        _row("2020-01-01T12:00:00"),
    ]
    source = _write_csv(tmp_path / "fraudTrain.csv", rows)

    with pytest.raises(SystemExit, match="exploitables"):
        generate_payloads.main(
            [
                "--source",
                str(source),
                "--output",
                str(tmp_path / "out.json"),
                "--sample-size",
                "2",
            ]
        )
