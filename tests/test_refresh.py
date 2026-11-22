"""Offline tests for the Step 3 refresh, snapshot and recovery pipeline."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from topomarket import cli
from topomarket.data.adapters import import_sources
from topomarket.data.fetch import SOURCES, FetchResult
from topomarket.data.refresh import (
    MAX_SOURCE_BYTES,
    RefreshBusyError,
    RefreshError,
    _normalized_digest,
    _RefreshLock,
    active_snapshot_id,
    load_normalized_tables,
    load_refresh_status,
    refresh_sources,
)

INDUSTRIES = (
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
DATES = ("2018-12-05", "2018-12-06", "2018-12-07", "2018-12-10", "2018-12-12")


def _openintro() -> str:
    lines = ["Date,Open,High,Low,Close,Adj Close,Volume"]
    for index, date in enumerate(DATES[:3]):
        close = 200.0 + index
        lines.append(f"{date},{close},{close + 1},{close - 1},{close},{close},1000")
    return "\n".join(lines) + "\n"


def _fred(dates: tuple[str, ...] = ("2018-12-10", "2018-12-11")) -> str:
    values = {"2018-12-10": "203.00", "2018-12-11": "204.00", "2018-12-12": "260.00"}
    lines = ["observation_date,SP500"]
    for date in dates:
        lines.append(f"{date},{values[date]}")
    return "\n".join(lines) + "\n"


def _vix() -> str:
    lines = ["Date,Open,High,Low,Close"]
    for index, date in enumerate(DATES):
        month, day, year = date.split("-")[1], date.split("-")[2], date.split("-")[0]
        lines.append(f"{int(month)}/{int(day)}/{year},18,20,17,{20 + index}")
    return "\n".join(lines) + "\n"


def _french() -> str:
    lines = ["Average Value Weighted Returns -- Daily", "", "," + ",".join(INDUSTRIES)]
    for index, date in enumerate(DATES):
        values = ",".join(f"{1.0 + index + offset:.2f}" for offset in range(12))
        lines.append(f"{date.replace('-', '')},{values}")
    lines.extend(
        [
            "",
            "Average Equal Weighted Returns -- Daily",
            "",
            "," + ",".join(INDUSTRIES),
            "20181205," + ",".join("0.5" for _ in INDUSTRIES),
        ]
    )
    return "\n".join(lines) + "\n"


def _ofr() -> str:
    return "observation_date,OFR FSI\n2018-12-10,-0.5\n2018-12-12,0.1\n"


def _zip_bytes(text: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("12_Industry_Portfolios_daily_CSV.csv", text)
    return buffer.getvalue()


def _bodies(*, fred: str | None = None) -> dict[str, bytes]:
    return {
        "fred_sp500": (fred or _fred()).encode(),
        "cboe_vix": _vix().encode(),
        "french_12_industries": _zip_bytes(_french()),
        "ofr_fsi": _ofr().encode(),
    }


def _baseline(data_dir: Path) -> None:
    raw = data_dir / "seed"
    raw.mkdir(parents=True)
    fixtures = {
        "sp500_1950_2018.csv": _openintro(),
        "SP500_FRED.csv": _fred(),
        "VIX_History.csv": _vix(),
        "12_Industry_Portfolios_daily_CSV.zip": _zip_bytes(_french()),
        "ofr_fsi.csv": _ofr(),
    }
    for filename, content in fixtures.items():
        path = raw / filename
        if filename.endswith(".zip"):
            path.write_bytes(content if isinstance(content, bytes) else content.encode())
        else:
            path.write_text(
                content if isinstance(content, str) else content.decode(), encoding="utf-8"
            )
    import_sources(raw, data_dir)


def _result(
    source_id: str,
    *,
    body: bytes | None = None,
    status: int | None = 200,
    not_modified: bool = False,
    error: str | None = None,
    etag: str | None = None,
) -> FetchResult:
    return FetchResult(
        source_id=source_id,
        url=SOURCES[source_id],
        status=status,
        not_modified=not_modified,
        conditional_requested=etag is not None or not_modified,
        body=body,
        headers={},
        etag=etag if etag is not None else f'"{source_id}-v1"',
        last_modified="Wed, 12 Dec 2018 00:00:00 GMT",
        attempts=1,
        timeout_seconds=15.0,
        error=error,
        fetched_at_utc="2018-12-12T20:00:00Z",
    )


def _fetcher(
    bodies: dict[str, bytes] | None = None,
    *,
    errors: dict[str, str] | None = None,
    not_modified: set[str] | None = None,
):
    bodies = bodies if bodies is not None else _bodies()
    errors = errors or {}
    not_modified = not_modified or set()

    def fetch(source_id: str, *, etag=None, last_modified=None) -> FetchResult:
        if source_id in not_modified:
            return _result(source_id, status=304, not_modified=True, etag=etag)
        if source_id in errors:
            return _result(source_id, status=None, error=errors[source_id])
        return _result(source_id, body=bodies[source_id])

    return fetch


def _published(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    _baseline(data_dir)
    report = refresh_sources(data_dir, fetcher=_fetcher())
    assert report.published is True
    return data_dir


def test_refresh_publishes_an_atomic_snapshot(tmp_path: Path) -> None:
    data_dir = _published(tmp_path)

    snapshot_id = active_snapshot_id(data_dir)
    assert snapshot_id is not None
    snapshot_dir = data_dir / "snapshots" / snapshot_id
    assert snapshot_dir.is_dir()
    assert (data_dir / "state" / "active_snapshot.json").is_file()
    manifest = json.loads((snapshot_dir / "refresh_manifest.json").read_text(encoding="utf-8"))
    assert manifest["snapshot_id"] == snapshot_id
    assert manifest["latest_data_date"] == "2018-12-11"
    tables = load_normalized_tables(snapshot_dir)
    assert tables["sp500_daily"]
    assert tables["tda_daily"]
    assert _normalized_digest(snapshot_dir) == snapshot_id
    validators = json.loads((data_dir / "state" / "validators.json").read_text(encoding="utf-8"))
    assert validators["snapshot_id"] == snapshot_id
    assert validators["sources"]["fred_sp500"]["etag"] == '"fred_sp500-v1"'


def test_unchanged_content_preserves_the_snapshot(tmp_path: Path) -> None:
    data_dir = _published(tmp_path)
    snapshot_id = active_snapshot_id(data_dir)

    report = refresh_sources(data_dir, fetcher=_fetcher())

    assert report.published is False
    assert report.new_snapshot_id is None
    assert active_snapshot_id(data_dir) == snapshot_id


def test_304_not_modified_keeps_the_snapshot(tmp_path: Path) -> None:
    data_dir = _published(tmp_path)
    snapshot_id = active_snapshot_id(data_dir)

    report = refresh_sources(
        data_dir,
        fetcher=_fetcher(
            not_modified={"fred_sp500", "cboe_vix", "french_12_industries", "ofr_fsi"}
        ),
    )

    assert report.published is False
    assert all(status.outcome == "unchanged" for status in report.sources)
    assert active_snapshot_id(data_dir) == snapshot_id


def test_revised_close_and_shorter_export_retain_history(tmp_path: Path) -> None:
    data_dir = _published(tmp_path)
    before = json.loads((data_dir / "state" / "active_snapshot.json").read_text(encoding="utf-8"))

    bodies = _bodies(fred="observation_date,SP500\n2018-12-10,250.00\n2018-12-12,260.00\n")
    report = refresh_sources(data_dir, fetcher=_fetcher(bodies))

    assert report.published is True
    assert report.new_snapshot_id and report.new_snapshot_id != before["snapshot_id"]
    tables = load_normalized_tables(data_dir / "snapshots" / report.new_snapshot_id)
    dates = [row["date"] for row in tables["sp500_daily"]]
    assert dates == [
        "2018-12-05",
        "2018-12-06",
        "2018-12-07",
        "2018-12-10",
        "2018-12-11",
        "2018-12-12",
    ]
    assert report.latest_data_date == "2018-12-12"
    revisions = {(item.date, item.field): item for item in report.revisions}
    assert ("2018-12-10", "sp500_close") in revisions
    assert revisions[("2018-12-10", "sp500_close")].old_value == "203.0"
    # The clean rebuild of the same merged inputs is deterministic.
    assert (
        _normalized_digest(data_dir / "snapshots" / report.new_snapshot_id)
        == report.new_snapshot_id
    )


def test_broken_archive_keeps_the_previous_snapshot(tmp_path: Path) -> None:
    data_dir = _published(tmp_path)
    snapshot_id = active_snapshot_id(data_dir)
    pointer_before = (data_dir / "state" / "active_snapshot.json").read_bytes()

    bodies = _bodies()
    bodies["french_12_industries"] = b"this is not a zip archive"
    with pytest.raises(RefreshError):
        refresh_sources(data_dir, fetcher=_fetcher(bodies))

    assert active_snapshot_id(data_dir) == snapshot_id
    assert (data_dir / "state" / "active_snapshot.json").read_bytes() == pointer_before
    status = load_refresh_status(data_dir)
    assert status["published"] is False
    assert any(value["outcome"] == "failed" for value in status["sources"].values())


def test_required_source_failure_keeps_last_good_snapshot(tmp_path: Path) -> None:
    data_dir = _published(tmp_path)
    snapshot_id = active_snapshot_id(data_dir)

    with pytest.raises(RefreshError):
        refresh_sources(data_dir, fetcher=_fetcher(errors={"cboe_vix": "timeout"}))

    assert active_snapshot_id(data_dir) == snapshot_id
    status = load_refresh_status(data_dir)
    assert status["sources"]["cboe_vix"]["outcome"] == "failed"
    assert status["sources"]["cboe_vix"]["last_attempt_at"]
    assert status["sources"]["cboe_vix"]["last_success_at"]


def test_optional_source_failure_still_publishes(tmp_path: Path) -> None:
    data_dir = _published(tmp_path)

    report = refresh_sources(
        data_dir,
        fetcher=_fetcher(
            bodies=_bodies(
                fred="observation_date,SP500\n2018-12-10,203.00\n2018-12-11,204.00\n2018-12-12,260.00\n"
            ),
            errors={"ofr_fsi": "404"},
        ),
    )

    assert report.published is True
    statuses = {status.source_id: status.outcome for status in report.sources}
    assert statuses["ofr_fsi"] == "optional_failed"
    assert statuses["fred_sp500"] == "updated"


def test_concurrent_refresh_is_rejected_by_the_lock(tmp_path: Path) -> None:
    data_dir = _published(tmp_path)
    with _RefreshLock(data_dir):
        with pytest.raises(RefreshBusyError):
            refresh_sources(data_dir, fetcher=_fetcher())


def test_oversized_payload_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = _published(tmp_path)
    monkeypatch.setattr("topomarket.data.refresh.MAX_SOURCE_BYTES", 10)
    bodies = _bodies()
    bodies["ofr_fsi"] = b"x" * 32
    with pytest.raises(RefreshError, match="50 MiB|exceeds"):
        refresh_sources(data_dir, fetcher=_fetcher(bodies))
    assert MAX_SOURCE_BYTES > 10


def test_first_refresh_requires_fetched_data_not_304(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    _baseline(data_dir)

    with pytest.raises(RefreshError, match="304"):
        refresh_sources(data_dir, fetcher=_fetcher(not_modified=set(SOURCES)))

    assert active_snapshot_id(data_dir) is None


def test_cli_refresh_sources_and_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    data_dir = tmp_path / "data"
    _baseline(data_dir)
    fake_fetcher = _fetcher()

    def fake_refresh(target, *, source_ids=None, fetcher=None, clock=None):
        return refresh_sources(target, source_ids=source_ids, fetcher=fake_fetcher)

    monkeypatch.setattr(cli, "refresh_sources", fake_refresh)

    assert cli.main(["refresh", "--data-dir", str(data_dir), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["published"] is True
    assert payload["active_snapshot_id"]

    assert cli.main(["sources", "--data-dir", str(data_dir), "--json"]) == 0
    status_payload = json.loads(capsys.readouterr().out)
    assert status_payload["active_snapshot_id"] == payload["active_snapshot_id"]
    assert set(status_payload["sources"]) == set(SOURCES)

    assert cli.main(["validate", "--data-dir", str(data_dir)]) == 0
    output = capsys.readouterr().out
    assert "active snapshot" in output.lower()
    assert "is valid" in output.lower()

    assert cli.main(["status", "--data-dir", str(data_dir)]) == 0
    assert "2018-12-12" in capsys.readouterr().out
