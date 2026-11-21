"""Private A2 acceptance checks.

The module is deliberately opt-in: it reads the private seed only from
``TOPOMARKET_SEED_DIR`` and skips when the environment variable is absent.  It
never copies seed bytes, prints observations, or writes private data into the
repository.  Temporary-normalised data is kept in memory and compared by hash.
"""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
from typing import Any

import pytest

from topomarket.data.adapters import NormalizedDataset, import_sources, normalize_key
from topomarket.data.schemas import (
    INDUSTRIES_DAILY_COLUMNS,
    NORMALIZED_TABLE_NAMES,
    SP500_DAILY_COLUMNS,
    TDA_DAILY_COLUMNS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_ENV_VAR = "TOPOMARKET_SEED_DIR"

#: Row counts fixed by the A2 acceptance snapshot.
EXPECTED_ROW_COUNTS = {
    "sp500_daily": 19_343,
    "tda_daily": 9_250,
}

#: The supplied FRED export has 96 blank ``SP500`` cells.
EXPECTED_FRED_BLANK_CELLS = 96

#: Known source disagreement and the golden row used by the A2 review.
DISCREPANCY_DATE = "2018-11-29"
GOLDEN_DATE = "2020-03-16"
GOLDEN_SP500_CLOSE = 2_386.13
GOLDEN_VIX_CLOSE = 82.69
GOLDEN_LOG_RETURN = -0.12765214115647325
PRICE_ABS_TOLERANCE = 0.01
RETURN_ABS_TOLERANCE = 1e-6

EXPECTED_INDUSTRY_NAMES = (
    "NoDur",
    "Durbl",
    "Manuf",
    "Enrgy",
    "Chems",
    "BusEq",
    "Telcm",
    "Utils",
    "Shops",
    "Hlth",
    "Money",
    "Other",
)

EXPECTED_INDUSTRY_COLUMNS = (
    "ind_nodur_return",
    "ind_durbl_return",
    "ind_manuf_return",
    "ind_enrgy_return",
    "ind_chems_return",
    "ind_buseq_return",
    "ind_telcm_return",
    "ind_utils_return",
    "ind_shops_return",
    "ind_hlth_return",
    "ind_money_return",
    "ind_other_return",
)

#: Directories that hold repository metadata, caches or policy-excluded inputs.
_REPO_SCAN_SKIP_PARTS = frozenset(
    {
        ".git",
        ".adp",
        ".adp-inputs",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".venv",
        "__pycache__",
        "private_data",
        "venv",
    }
)


def _private_seed_location() -> Path:
    """Return the configured seed path, skipping when it is not configured."""

    configured = os.environ.get(SEED_ENV_VAR)
    if not configured:
        pytest.skip(f"{SEED_ENV_VAR} is not set; private acceptance checks are opt-in")
    location = Path(configured).expanduser()
    if not location.exists():
        pytest.skip(f"{SEED_ENV_VAR} does not point at an existing path")
    return location


def _import_seed(location: Path):
    """Import a seed directory, archive or single file without writing output."""

    if location.is_dir():
        return import_sources(location, write=False)
    if location.suffix.lower() == ".zip":
        return import_sources(input_zip=location, write=False)
    return import_sources(input_path=location, write=False)


@pytest.fixture(scope="session")
def seed_location() -> Path:
    return _private_seed_location()


@pytest.fixture(scope="session")
def imported_seed(seed_location: Path):
    try:
        result = _import_seed(seed_location)
    except Exception as exc:  # pragma: no cover - only on a broken private input
        pytest.fail(
            f"could not import the private seed supplied via {SEED_ENV_VAR}: {type(exc).__name__}"
        )

    if not result.tables:
        pytest.fail(f"the private seed supplied via {SEED_ENV_VAR} has no recognised sources")
    assert result.output_dir is None
    assert result.written == {}
    return result


def _table(result, table_name: str) -> NormalizedDataset:
    dataset = result.normalized_tables.get(table_name)
    assert dataset is not None, f"missing normalised table: {table_name}"
    return dataset


def _rows_by_date(dataset: NormalizedDataset) -> dict[str, Any]:
    return {str(row.get("date")): row for row in dataset}


def _source_rows_by_date(result, source_id: str) -> dict[str, Any]:
    dataset = result.tables.get(source_id)
    assert dataset is not None, f"missing source table: {source_id}"
    return _rows_by_date(dataset)


def _value_weighted_percent(row: Any) -> Any:
    """Read a value-weighted percent return from a wide or tidy French row."""

    value = row.get("value_weighted_return")
    if value is not None:
        return value
    weighting = str(row.get("weighting") or "value").strip().lower()
    if "equal" in weighting:
        return None
    return row.get("return")


def _normalized_table_hashes(result) -> dict[str, str]:
    """Hash the canonical in-memory CSV for every normalised table."""

    hashes: dict[str, str] = {}
    for table_name in NORMALIZED_TABLE_NAMES:
        payload = _table(result, table_name).to_csv().encode("utf-8")
        hashes[table_name] = hashlib.sha256(payload).hexdigest()
    return hashes


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_hashes(seed_location: Path, result) -> set[str]:
    """Return hashes of the raw seed plus its normalised in-memory output."""

    if seed_location.is_file():
        hashes = {_file_sha256(seed_location)}
    else:
        hashes = {_file_sha256(path) for path in seed_location.rglob("*") if path.is_file()}
    for table_name in NORMALIZED_TABLE_NAMES:
        payload = _table(result, table_name).to_csv().encode("utf-8")
        hashes.add(hashlib.sha256(payload).hexdigest())
    return hashes


def _repository_hashes(seed_location: Path) -> set[str]:
    """Hash repository files while ignoring metadata, caches and seed inputs."""

    root = REPO_ROOT.resolve()
    seed = seed_location.resolve()
    hashes: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in _REPO_SCAN_SKIP_PARTS for part in relative.parts):
            continue
        resolved = path.resolve()
        if resolved == seed or (seed.is_dir() and resolved.is_relative_to(seed)):
            continue
        try:
            hashes.add(_file_sha256(path))
        except OSError:  # pragma: no cover - unreadable optional repository file
            continue
    return hashes


def test_private_seed_import_has_the_expected_row_counts(imported_seed) -> None:
    assert set(imported_seed.normalized_tables) == set(NORMALIZED_TABLE_NAMES)

    for table_name, expected_count in EXPECTED_ROW_COUNTS.items():
        dataset = _table(imported_seed, table_name)
        assert dataset.row_count == expected_count

    assert tuple(_table(imported_seed, "sp500_daily").columns) == SP500_DAILY_COLUMNS
    assert tuple(_table(imported_seed, "tda_daily").columns) == TDA_DAILY_COLUMNS


def test_2018_11_29_discrepancy_and_blank_fred_cells_are_reported(imported_seed) -> None:
    fred_report = imported_seed.reports.get("fred_sp500")
    assert fred_report is not None, "FRED source report is missing"
    assert int(fred_report["missing_values"]["value"]) == EXPECTED_FRED_BLANK_CELLS
    assert int(fred_report["missing_total"]) == EXPECTED_FRED_BLANK_CELLS

    openintro = _source_rows_by_date(imported_seed, "openintro_sp500")
    fred = _source_rows_by_date(imported_seed, "fred_sp500")
    fred_missing_dates = {
        str(row.get("date"))
        for row in imported_seed.tables["fred_sp500"]
        if row.get("value") is None
    }
    fred_missing_cells = sum(
        1 for row in imported_seed.tables["fred_sp500"] if row.get("value") is None
    )
    assert fred_missing_cells == EXPECTED_FRED_BLANK_CELLS

    openintro_row = openintro.get(DISCREPANCY_DATE)
    fred_row = fred.get(DISCREPANCY_DATE)
    assert openintro_row is not None or fred_row is not None, (
        "neither source covers the discrepancy date"
    )

    openintro_close = None if openintro_row is None else openintro_row.get("close")
    fred_close = None if fred_row is None else fred_row.get("value")
    assert openintro_close is not None or fred_close is not None
    if fred_row is not None and fred_close is None:
        assert DISCREPANCY_DATE in fred_missing_dates

    # The known discrepancy is a missing FRED observation or a genuinely
    # different FRED close.  Either way the OpenIntro value remains authoritative
    # before the 2018-12-07 cutover.
    if openintro_close is not None and fred_close is not None:
        assert not math.isclose(
            float(openintro_close),
            float(fred_close),
            rel_tol=0.0,
            abs_tol=1e-9,
        ), "expected the supplied OpenIntro and FRED closes to disagree on 2018-11-29"

    if openintro_close is not None:
        normalised = _rows_by_date(_table(imported_seed, "sp500_daily"))
        row = normalised.get(DISCREPANCY_DATE)
        assert row is not None
        assert row.get("price_source") == "openintro"
        assert math.isclose(
            float(row.get("sp500_close")),
            float(openintro_close),
            rel_tol=0.0,
            abs_tol=1e-9,
        )


def test_2020_03_16_golden_row_values_within_tolerance(imported_seed) -> None:
    sp500 = _table(imported_seed, "sp500_daily")
    tda = _table(imported_seed, "tda_daily")
    industries = _table(imported_seed, "industries_daily")

    sp500_rows = _rows_by_date(sp500)
    tda_rows = _rows_by_date(tda)
    industry_rows = _rows_by_date(industries)
    assert GOLDEN_DATE in sp500_rows
    assert GOLDEN_DATE in tda_rows
    assert GOLDEN_DATE in industry_rows

    golden = sp500_rows[GOLDEN_DATE]
    assert float(golden["sp500_close"]) == pytest.approx(
        GOLDEN_SP500_CLOSE, abs=PRICE_ABS_TOLERANCE
    )
    assert float(golden["sp500_log_return"]) == pytest.approx(
        GOLDEN_LOG_RETURN, abs=RETURN_ABS_TOLERANCE
    )

    tda_row = tda_rows[GOLDEN_DATE]
    assert float(tda_row["sp500_close"]) == pytest.approx(float(golden["sp500_close"]), abs=1e-9)
    assert float(tda_row["sp500_log_return"]) == pytest.approx(
        float(golden["sp500_log_return"]), abs=1e-9
    )
    assert float(tda_row["vix_close"]) == pytest.approx(GOLDEN_VIX_CLOSE, abs=PRICE_ABS_TOLERANCE)

    french_rows = [
        row
        for row in imported_seed.tables["french_12_industries"]
        if str(row.get("date")) == GOLDEN_DATE
    ]
    assert french_rows, "French industry source does not cover the golden date"
    french_by_industry = {
        normalize_key(row.get("industry")): _value_weighted_percent(row)
        for row in french_rows
        if _value_weighted_percent(row) is not None
    }
    industry_row = industry_rows[GOLDEN_DATE]
    for industry_name, column in zip(
        EXPECTED_INDUSTRY_NAMES, INDUSTRIES_DAILY_COLUMNS[1:], strict=True
    ):
        value = industry_row.get(column)
        assert value is not None, f"missing golden industry return: {industry_name}"
        assert -1.0 < float(value) < 1.0
        raw_percent = french_by_industry.get(normalize_key(industry_name))
        assert raw_percent is not None, f"missing raw French observation for {industry_name}"
        assert float(value) == pytest.approx(float(raw_percent) / 100.0, abs=1e-12)
        assert float(tda_row[column]) == pytest.approx(float(value), abs=1e-12)


def test_reimport_produces_identical_normalised_table_hashes(seed_location, imported_seed) -> None:
    reimported = _import_seed(seed_location)

    assert _normalized_table_hashes(imported_seed) == _normalized_table_hashes(reimported)
    for table_name in NORMALIZED_TABLE_NAMES:
        assert (
            _table(imported_seed, table_name).row_count == _table(reimported, table_name).row_count
        )


def test_industry_columns_and_no_private_data_in_repository(seed_location, imported_seed) -> None:
    industries = _table(imported_seed, "industries_daily")
    assert tuple(industries.columns[1:]) == EXPECTED_INDUSTRY_COLUMNS
    assert len(EXPECTED_INDUSTRY_COLUMNS) == 12
    assert len(set(EXPECTED_INDUSTRY_COLUMNS)) == 12
    assert tuple(_table(imported_seed, "tda_daily").columns[4:]) == EXPECTED_INDUSTRY_COLUMNS

    assert _private_hashes(seed_location, imported_seed).isdisjoint(
        _repository_hashes(seed_location)
    ), "private seed or normalised output was found inside the repository"
