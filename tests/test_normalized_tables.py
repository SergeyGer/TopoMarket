"""Public tests for the normalised table contracts and generators."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from topomarket.data.adapters import import_sources
from topomarket.data.normalized import (
    build_demo_normalized_tables,
    build_normalized_tables,
    read_normalized_table,
    write_normalized_tables,
)
from topomarket.data.schemas import (
    INDUSTRIES_DAILY_COLUMNS,
    NORMALIZED_FILE_NAMES,
    NORMALIZED_TABLE_NAMES,
    SCHEMAS,
    SP500_DAILY_COLUMNS,
    TDA_DAILY_COLUMNS,
)
from topomarket.data.synthetic import SYNTHETIC_FILE_NAMES, generate_synthetic
from topomarket.demo import generate_demo

OPENINTRO = """Date,Open,High,Low,Close,Adj Close,Volume
2024-01-02,100.0,105.0,99.0,104.0,103.0,1000000
2024-01-03,104.0,106.0,101.0,102.5,101.5,1200000
"""

FRED = """observation_date,SP500
2024-01-02,4745.20
2024-01-03,4704.81
2024-01-04,.
"""

FRENCH = """Average Value Weighted Returns -- Daily

,NoDur,Durbl,Manuf,Enrgy,Chems,BusEq,Telcm,Utils,Shops,Hlth,Money,Other
20240102,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0,11.0,12.0
20240103,-1.0,-2.0,-3.0,-4.0,-5.0,-6.0,-7.0,-8.0,-9.0,-10.0,-11.0,-12.0
"""

VIX = """DATE,OPEN,HIGH,LOW,CLOSE
1/2/2024,13.0,14.0,12.5,13.5
1/3/2024,13.5,15.0,13.0,14.2
"""


def _write_inputs(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "sp500.csv").write_text(OPENINTRO, encoding="utf-8")
    (directory / "fred.csv").write_text(FRED, encoding="utf-8")
    (directory / "french.csv").write_text(FRENCH, encoding="utf-8")
    (directory / "vix.csv").write_text(VIX, encoding="utf-8")


def _digests(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


def test_schema_contracts_are_complete() -> None:
    assert SP500_DAILY_COLUMNS == (
        "date",
        "sp500_close",
        "price_source",
        "sp500_log_return",
    )
    assert INDUSTRIES_DAILY_COLUMNS[0] == "date"
    assert len(INDUSTRIES_DAILY_COLUMNS) == 13
    assert TDA_DAILY_COLUMNS[:4] == (
        "date",
        "sp500_close",
        "sp500_log_return",
        "vix_close",
    )
    assert TDA_DAILY_COLUMNS[4:] == INDUSTRIES_DAILY_COLUMNS[1:]
    assert set(SCHEMAS) == set(NORMALIZED_TABLE_NAMES)
    for _table_name, schema in SCHEMAS.items():
        assert schema["date"] == "date"
        valid_types = {"date", "float", "integer", "string"}
        assert all(column_type in valid_types for column_type in schema.values())
    assert SCHEMAS["sp500_daily"]["price_source"] == "string"
    assert SCHEMAS["sp500_daily"]["sp500_log_return"] == "float"
    assert SCHEMAS["tda_daily"]["vix_close"] == "float"


def test_demo_tables_match_every_schema_contract() -> None:
    first = build_demo_normalized_tables(seed=42)
    second = build_demo_normalized_tables(seed=42)

    assert tuple(first) == NORMALIZED_TABLE_NAMES
    for table_name in NORMALIZED_TABLE_NAMES:
        dataset = first[table_name]
        assert tuple(dataset.columns) == tuple(SCHEMAS[table_name])
        assert dataset.schema == SCHEMAS[table_name]
        assert dataset.metadata["synthetic"] is True
        assert dataset.metadata["seed"] == 42
        assert dataset.to_json() == second[table_name].to_json()
        assert tuple(second[table_name].columns) == tuple(SCHEMAS[table_name])


def test_normalized_writer_emits_the_schema_contract(tmp_path: Path) -> None:
    tables = build_normalized_tables(
        sp500=[{"date": "2024-01-02", "close": 100.0}],
        industries=[{"date": "2024-01-02", "industry": "NoDur", "value_weighted_return": 1.0}],
    )
    output = tmp_path / "output"

    written = write_normalized_tables(tables, output)

    assert set(written) == set(NORMALIZED_TABLE_NAMES)
    schema_payload = json.loads(
        (output / "normalized" / "schemas.json").read_text(encoding="utf-8")
    )
    assert set(schema_payload["tables"]) == set(NORMALIZED_TABLE_NAMES)
    for table_name in NORMALIZED_TABLE_NAMES:
        record = schema_payload["tables"][table_name]
        assert record["file"] == f"{table_name}.csv"
        assert record["columns"] == list(SCHEMAS[table_name])
        assert record["types"] == SCHEMAS[table_name]
        primary = output / f"{table_name}.csv"
        mirror = output / "normalized" / f"{table_name}.csv"
        assert primary.is_file()
        assert mirror.is_file()
        assert primary.read_bytes() == mirror.read_bytes()
        assert read_normalized_table(primary).columns == tuple(SCHEMAS[table_name])


def test_synthetic_generator_includes_normalized_tables(tmp_path: Path) -> None:
    out = tmp_path / "synthetic"
    manifest = generate_synthetic(out, seed=42, created_at="2024-02-01T00:00:00Z")

    assert set(NORMALIZED_FILE_NAMES) <= set(SYNTHETIC_FILE_NAMES)
    for filename in NORMALIZED_FILE_NAMES:
        assert (out / filename).is_file()
        assert manifest["row_counts"][filename] == 30
    assert read_normalized_table(out / "sp500_daily.csv").columns == SP500_DAILY_COLUMNS
    assert read_normalized_table(out / "industries_daily.csv").columns == INDUSTRIES_DAILY_COLUMNS
    assert read_normalized_table(out / "tda_daily.csv").columns == TDA_DAILY_COLUMNS


def test_demo_generator_is_byte_identical_for_the_same_seed(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    first_manifest = generate_demo(first, seed=42, created_at="2024-02-01T00:00:00Z")
    generate_demo(second, seed=42, created_at="2024-02-01T00:00:00Z")

    assert first_manifest["synthetic"] is True
    assert first_manifest["private_data"] is False
    assert first_manifest["tables"] == list(NORMALIZED_TABLE_NAMES)
    assert _digests(first) == _digests(second)
    for filename in NORMALIZED_FILE_NAMES:
        data = (first / filename).read_bytes()
        assert b"\r\n" not in data
        assert data.endswith(b"\n")


def test_source_import_writes_the_same_schema(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    _write_inputs(inputs)
    output = tmp_path / "output"

    result = import_sources(inputs, output)

    assert set(result.normalized_tables) == set(NORMALIZED_TABLE_NAMES)
    for table_name, dataset in result.normalized_tables.items():
        assert list(dataset.columns) == list(SCHEMAS[table_name])
        assert (output / f"{table_name}.csv").is_file()
        assert (output / "normalized" / f"{table_name}.csv").is_file()

    # The inner join drops dates that are missing from one source and never
    # forward fills the index or industry values.
    tda = result.normalized_tables["tda_daily"]
    assert tda.first_observation == "2024-01-02"
    assert tda.last_observation == "2024-01-03"
    assert tda.row_count == 2


def test_write_is_deterministic_for_identical_rows(tmp_path: Path) -> None:
    tables = build_normalized_tables(
        sp500=[
            {"date": "2024-01-03", "close": 101.0},
            {"date": "2024-01-02", "close": 100.0},
        ],
        industries=[{"date": "2024-01-02", "industry": "NoDur", "value_weighted_return": 1.0}],
    )
    first = tmp_path / "first"
    second = tmp_path / "second"

    write_normalized_tables(tables, first)
    write_normalized_tables(tables, second)

    assert _digests(first) == _digests(second)
    sp500_lines = (first / "sp500_daily.csv").read_text(encoding="utf-8").splitlines()
    assert sp500_lines[0] == "date,sp500_close,price_source,sp500_log_return"
    assert sp500_lines[1].startswith("2024-01-02")


def test_sp500_cutover_and_industry_decimal_returns() -> None:
    sp500 = build_normalized_tables(
        sp500={
            "openintro_sp500": [
                {"date": "2018-12-07", "close": 100.0},
                {"date": "2018-12-10", "close": 999.0},
            ],
            "fred_sp500": [
                {"date": "2018-12-07", "value": 111.0},
                {"date": "2018-12-10", "value": 110.0},
            ],
        },
        industries=[
            {"date": "2018-12-07", "industry": "NoDur", "value_weighted_return": -8.96},
            {"date": "2018-12-10", "industry": "NoDur", "value_weighted_return": 1.0},
        ],
        compute_tda=False,
    )

    sp500_rows = {row["date"]: row for row in sp500["sp500_daily"]}
    assert sp500_rows["2018-12-07"]["sp500_close"] == 100.0
    assert sp500_rows["2018-12-07"]["price_source"] == "openintro"
    assert sp500_rows["2018-12-10"]["sp500_close"] == 110.0
    assert sp500_rows["2018-12-10"]["price_source"] == "fred"
    assert sp500_rows["2018-12-07"]["sp500_log_return"] is None

    industries_rows = {row["date"]: row for row in sp500["industries_daily"]}
    assert abs(industries_rows["2018-12-07"]["ind_nodur_return"] - (-0.0896)) < 1e-12
