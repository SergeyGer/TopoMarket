"""Synthetic-fixture tests for the local seed-file adapters.

These tests deliberately use only in-repository fixture strings and temporary
directories.  No network access, private data or hard-coded input path is
required.
"""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from topomarket.data.adapters import (
    SOURCE_IDS,
    CboeVixAdapter,
    FREDSP500Adapter,
    French12IndustryAdapter,
    OFRFSIAdapter,
    OpenIntroSP500Adapter,
    RawHashRegistry,
    import_sources,
    import_zip,
)
from topomarket.data.adapters.cli import main as adapter_main

OPENINTRO = """OpenIntro S&P 500 daily observations
Date,Open,High,Low,Close,Adj Close,Volume
2024-01-02,100.0,105.0,99.0,104.0,103.0,1000000
2024-01-03,104.0,106.0,101.0,102.5,101.5,1200000
"""

FRED = """observation_date,SP500
2024-01-02,4745.20
2024-01-03,4704.81
2024-01-04,.
"""

CBOE = """Date,Open,High,Low,Close
1/2/2024,13.0,14.0,12.5,13.5
1/3/2024,13.5,15.0,13.0,14.2
"""

FRENCH = """Average Value Weighted Returns -- Daily

,NoDur,Durbl,Manuf,Enrgy,Chems,BusEq,Telcm,Utils,Shops,Hlth,Money,Other
20240102,1.0,2.0,3.0,4.0,5.0,6.0,7.0,8.0,9.0,10.0,11.0,12.0
20240103,-1.0,-2.0,-3.0,-4.0,-5.0,-6.0,-7.0,-8.0,-9.0,-10.0,-11.0,-12.0

Average Equal Weighted Returns -- Daily

,NoDur,Durbl,Manuf,Enrgy,Chems,BusEq,Telcm,Utils,Shops,Hlth,Money,Other
20240102,0.5,1.5,2.5,3.5,4.5,5.5,6.5,7.5,8.5,9.5,10.5,11.5
20240103,-0.5,-1.5,-2.5,-3.5,-4.5,-5.5,-6.5,-7.5,-8.5,-9.5,-10.5,-11.5
"""

OFR = """observation_date,OFR FSI
2024-01-02,-0.5
2024-01-03,0.1
"""

FIXTURES = {
    "sp500_1950_2018.csv": OPENINTRO,
    "SP500_FRED.csv": FRED,
    "VIX_History.csv": CBOE,
    "12_Industry_Portfolios_daily_CSV.csv": FRENCH,
    "ofr_fsi.csv": OFR,
}


def _write_fixtures(directory: Path) -> None:
    for filename, text in FIXTURES.items():
        (directory / filename).write_text(text, encoding="utf-8")


def _digest_map(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_directory_import_writes_registry_reports_and_tables(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _write_fixtures(inputs)
    output = tmp_path / "output"

    result = import_sources(inputs, output)

    assert set(result.tables) == set(SOURCE_IDS)
    assert set(result.reports) == set(SOURCE_IDS)
    assert result.tables["fred_sp500"].row_count == 3
    assert result.reports["fred_sp500"]["missing_values"]["value"] == 1
    assert result.reports["openintro_sp500"]["first_observation"] == "2024-01-02"
    assert result.reports["cboe_vix"]["last_observation"] == "2024-01-03"
    assert result.reports["french_12_industries"]["row_count"] == 24

    registry = json.loads((output / "raw_hashes.json").read_text(encoding="utf-8"))
    assert registry["entry_count"] == len(FIXTURES)
    for entry in registry["entries"]:
        assert {"filename", "sha256", "source_id", "metadata"} <= set(entry)
        expected = hashlib.sha256((inputs / entry["filename"]).read_bytes()).hexdigest()
        assert entry["sha256"] == expected

    reports = json.loads((output / "parser_reports.json").read_text(encoding="utf-8"))
    assert reports["report_count"] == len(SOURCE_IDS)
    assert reports["row_counts"]["cboe_vix"] == 2
    assert (output / "normalized" / "cboe_vix.csv").is_file()
    assert (output / "import_manifest.json").is_file()


def test_import_is_deterministic_for_identical_bytes(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _write_fixtures(inputs)

    first = tmp_path / "first"
    second = tmp_path / "second"
    import_sources(inputs, first)
    import_sources(inputs, second)

    assert _digest_map(first) == _digest_map(second)


def test_zip_import_handles_a_nested_provider_archive(tmp_path: Path) -> None:
    inner = tmp_path / "french.zip"
    with zipfile.ZipFile(inner, "w") as archive:
        archive.writestr("12_Industry_Portfolios_daily_CSV.csv", FRENCH)

    archive = tmp_path / "seed.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for filename, text in FIXTURES.items():
            if filename.startswith("12_"):
                handle.write(inner, filename)
            else:
                handle.writestr(filename, text)

    result = import_zip(archive)

    assert set(result.tables) == set(SOURCE_IDS)
    assert result.tables["french_12_industries"].row_count == 24
    assert result.registry.entry_count == len(FIXTURES)


@pytest.mark.parametrize(
    ("adapter_class", "filename"),
    [
        (OpenIntroSP500Adapter, "sp500_1950_2018.csv"),
        (FREDSP500Adapter, "SP500_FRED.csv"),
        (CboeVixAdapter, "VIX_History.csv"),
        (French12IndustryAdapter, "12_Industry_Portfolios_daily_CSV.csv"),
        (OFRFSIAdapter, "ofr_fsi.csv"),
    ],
)
def test_adapters_parse_bytes_and_build_reports(adapter_class: type, filename: str) -> None:
    adapter = adapter_class()
    dataset = adapter.parse_bytes(FIXTURES[filename].encode("utf-8"), filename=filename)

    assert dataset.row_count > 0
    assert dataset.report is not None
    assert dataset.report["source_id"] == adapter.source_id
    assert dataset.report["filename"] == filename
    assert dataset.report["schema"]
    assert dataset.report["units"]
    assert dataset.report["first_observation"] <= dataset.report["last_observation"]
    assert dataset.report["warnings"] == []
    assert adapter.build_report()["row_count"] == dataset.row_count


def test_french_adapter_exposes_wide_industry_returns() -> None:
    adapter = French12IndustryAdapter()
    dataset = adapter.parse_bytes(FRENCH.encode("utf-8"), filename="french.csv")
    wide = adapter.parse_industry_returns(dataset)

    assert len(wide) == 2
    assert len([column for column in wide.columns if column.startswith("ind_")]) == 12
    assert wide.first_observation == "2024-01-02"


def test_raw_hash_registry_round_trip(tmp_path: Path) -> None:
    registry = RawHashRegistry()
    registry.register_bytes(b"hello", "seed.csv", "demo", metadata={"origin": "fixture"})

    destination = registry.write(tmp_path / "raw_hashes.json")
    loaded = RawHashRegistry.from_file(destination)

    assert len(loaded) == 1
    assert loaded[0]["filename"] == "seed.csv"
    assert loaded[0]["source_id"] == "demo"
    assert loaded[0]["sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert loaded[0]["metadata"]["origin"] == "fixture"


def test_adapter_cli_accepts_input_dir_and_zip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    _write_fixtures(inputs)
    output = tmp_path / "cli-output"
    archive = tmp_path / "seed.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        for filename, text in FIXTURES.items():
            handle.writestr(filename, text)

    assert adapter_main(["--input-dir", str(inputs), "--output-dir", str(output), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source_ids"]
    assert (output / "raw_hashes.json").is_file()

    assert adapter_main(["--input-zip", str(archive), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["registry_entries"] == len(FIXTURES)
