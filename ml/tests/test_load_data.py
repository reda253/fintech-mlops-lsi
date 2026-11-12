"""T21: the development-block loader used by the viz attachment."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from ml.src.data.load_data import DATE_COLUMN, load_development_block

ROW_ORDER = [9, 0, 5, 1, 8, 2, 7, 3, 6, 4]


def _source_frame(rows: int = 10, row_order: list[int] | None = None) -> pd.DataFrame:
    order = row_order or list(range(rows))
    return pd.DataFrame(
        {
            DATE_COLUMN: [
                pd.Timestamp("2020-01-01") + pd.Timedelta(minutes=index) for index in order
            ],
            "trans_num": [f"tx-{index}" for index in order],
            "amt": [float(index) for index in order],
            "is_fraud": [index % 2 for index in order],
        }
    )


def _write_source(tmp_path: Path, frame: pd.DataFrame) -> Path:
    path = tmp_path / "fraudTrain.csv"
    frame.to_csv(path, index=False)
    return path


def test_development_block_keeps_the_earliest_70_percent_after_sort(tmp_path: Path):
    path = _write_source(tmp_path, _source_frame(rows=10, row_order=ROW_ORDER))

    development = load_development_block(path)

    assert sorted(development["trans_num"]) == sorted(f"tx-{index}" for index in range(7))
    assert development[DATE_COLUMN].is_monotonic_increasing


def test_calibration_rows_are_never_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    path = _write_source(tmp_path, _source_frame(rows=10, row_order=ROW_ORDER))
    calls: list[dict] = []
    real_read_csv = pd.read_csv

    def spy(*args, **kwargs):
        calls.append(kwargs)
        return real_read_csv(*args, **kwargs)

    monkeypatch.setattr(pd, "read_csv", spy)
    development = load_development_block(path, columns=["trans_num", "amt"])

    assert len(calls) == 2
    assert calls[0]["usecols"] == [DATE_COLUMN]
    skiprows = calls[1]["skiprows"]
    assert skiprows(0) is False
    position = {f"tx-{index}": rank for rank, index in enumerate(ROW_ORDER)}
    kept_lines = {position[f"tx-{index}"] + 1 for index in range(7)}
    read_lines = {line for line in range(1, 11) if not skiprows(line)}
    assert read_lines == kept_lines
    assert set(development["trans_num"]) == {f"tx-{index}" for index in range(7)}
    assert list(development.columns) == [DATE_COLUMN, "trans_num", "amt"]


def test_development_block_requires_the_date_column(tmp_path: Path):
    path = tmp_path / "fraudTrain.csv"
    pd.DataFrame({"amt": [1.0, 2.0]}).to_csv(path, index=False)

    with pytest.raises(ValueError, match=DATE_COLUMN):
        load_development_block(path)


def test_development_block_rejects_a_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_development_block(tmp_path / "absent.csv")
