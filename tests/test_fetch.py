"""Offline contract tests for the fixed-source fetch layer (Step 3a)."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError

import httpx
import pytest

from topomarket.data.fetch import SOURCES, fetch_all, fetch_source, source_ids

# Independent literal URLs from the specification/contract; deliberately not
# imported from the implementation constants.
EXPECTED_URLS = {
    "fred_sp500": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",
    "cboe_vix": "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
    "french_12_industries": (
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
        "12_Industry_Portfolios_daily_CSV.zip"
    ),
    "ofr_fsi": "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv",
}


def _transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> tuple[httpx.MockTransport, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return handler(request)

    return httpx.MockTransport(wrapped), requests


def test_source_registry_matches_the_specification() -> None:
    assert dict(SOURCES) == EXPECTED_URLS
    assert source_ids() == tuple(EXPECTED_URLS)


def test_sources_registry_is_immutable() -> None:
    with pytest.raises(TypeError):
        SOURCES["fred_sp500"] = "https://example.com"  # type: ignore[index]
    with pytest.raises(AttributeError):
        SOURCES.update({"x": "y"})  # type: ignore[attr-defined]


@pytest.mark.parametrize("source_id", sorted(EXPECTED_URLS))
def test_successful_fetch_uses_the_literal_provider_url(source_id: str) -> None:
    transport, requests = _transport(
        lambda request: httpx.Response(
            200,
            content=b"date,value\n2024-01-01,1\n",
            headers={
                "content-type": "text/csv",
                "etag": '"abc"',
                "last-modified": "Wed, 01 Jan 2024 00:00:00 GMT",
            },
        )
    )
    result = fetch_source(source_id, transport=transport)

    assert result.ok is True
    assert result.status == 200
    assert result.error is None
    assert result.body == b"date,value\n2024-01-01,1\n"
    assert result.headers["content-type"].startswith("text/csv")
    assert result.etag == '"abc"'
    assert result.last_modified == "Wed, 01 Jan 2024 00:00:00 GMT"
    assert result.attempts == 1
    assert result.timeout_seconds == 15.0
    assert len(requests) == 1
    assert str(requests[0].url) == EXPECTED_URLS[source_id]
    headers = {key.lower(): value for key, value in requests[0].headers.items()}
    assert "authorization" not in headers
    assert "cookie" not in headers
    assert "user-agent" in headers


def test_conditional_headers_are_sent_only_when_validators_are_provided() -> None:
    transport, requests = _transport(lambda request: httpx.Response(200, content=b"ok"))

    fetch_source("fred_sp500", transport=transport, etag='"etag-1"')
    first = {key.lower(): value for key, value in requests[0].headers.items()}
    assert first["if-none-match"] == '"etag-1"'
    assert "if-modified-since" not in first

    fetch_source(
        "fred_sp500",
        transport=transport,
        etag='"etag-2"',
        last_modified="Wed, 01 Jan 2024 00:00:00 GMT",
    )
    second = {key.lower(): value for key, value in requests[1].headers.items()}
    assert second["if-none-match"] == '"etag-2"'
    assert second["if-modified-since"] == "Wed, 01 Jan 2024 00:00:00 GMT"

    fetch_source("fred_sp500", transport=transport)
    third = {key.lower(): value for key, value in requests[2].headers.items()}
    assert "if-none-match" not in third
    assert "if-modified-since" not in third


def test_304_preserves_supplied_validators_when_response_omits_them() -> None:
    transport, _ = _transport(lambda request: httpx.Response(304))
    result = fetch_source(
        "cboe_vix",
        transport=transport,
        etag='"etag-1"',
        last_modified="Wed, 01 Jan 2024 00:00:00 GMT",
    )
    assert result.ok is True
    assert result.not_modified is True
    assert result.conditional_requested is True
    assert result.body is None
    assert result.etag == '"etag-1"'
    assert result.last_modified == "Wed, 01 Jan 2024 00:00:00 GMT"


def test_304_response_validators_win_when_present() -> None:
    transport, _ = _transport(
        lambda request: httpx.Response(
            304, headers={"etag": '"new"', "last-modified": "Thu, 02 Jan 2024 00:00:00 GMT"}
        )
    )
    result = fetch_source("cboe_vix", transport=transport, etag='"old"')
    assert result.not_modified is True
    assert result.etag == '"new"'
    assert result.last_modified == "Thu, 02 Jan 2024 00:00:00 GMT"


def test_unsolicited_304_is_an_error_result() -> None:
    transport, _ = _transport(lambda request: httpx.Response(304))
    result = fetch_source("cboe_vix", transport=transport)
    assert result.ok is False
    assert result.not_modified is False
    assert result.status == 304
    assert result.etag is None
    assert result.error is not None


def test_retryable_status_is_retried_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, content=b"ok")

    sleeps: list[float] = []
    transport, requests = _transport(handler)
    result = fetch_source(
        "fred_sp500", transport=transport, backoff_seconds=0.5, sleep=sleeps.append
    )
    assert result.ok is True
    assert result.attempts == 2
    assert len(requests) == 2
    assert sleeps == [0.5]


def test_retry_exhaustion_keeps_final_response_metadata() -> None:
    transport, requests = _transport(
        lambda request: httpx.Response(429, headers={"retry-after": "7"})
    )
    sleeps: list[float] = []
    result = fetch_source("fred_sp500", transport=transport, max_attempts=3, sleep=sleeps.append)
    assert result.ok is False
    assert result.attempts == 3
    assert result.status == 429
    assert result.headers["retry-after"] == "7"
    assert result.body is None
    assert len(requests) == 3
    assert all(delay >= 7 for delay in sleeps)


def test_timeout_is_retried_then_succeeds() -> None:
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=b"ok")

    transport, _ = _transport(handler)
    result = fetch_source("fred_sp500", transport=transport, sleep=lambda _delay: None)
    assert result.ok is True
    assert result.attempts == 2


def test_transport_error_on_final_attempt_has_no_stale_success_state() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    transport, _ = _transport(handler)
    result = fetch_source(
        "fred_sp500",
        transport=transport,
        etag='"etag"',
        max_attempts=2,
        sleep=lambda _delay: None,
    )
    assert result.ok is False
    assert result.status is None
    assert result.body is None
    assert result.etag is None
    assert result.last_modified is None
    assert result.headers == {}
    assert result.conditional_requested is True


def test_redirects_are_rejected() -> None:
    transport, requests = _transport(
        lambda request: httpx.Response(302, headers={"location": "https://example.com/elsewhere"})
    )
    result = fetch_source("ofr_fsi", transport=transport)
    assert result.ok is False
    assert result.status == 302
    assert "redirect" in (result.error or "")
    assert len(requests) == 1


def test_non_retryable_client_error_fails_immediately() -> None:
    transport, requests = _transport(lambda request: httpx.Response(400))
    result = fetch_source("ofr_fsi", transport=transport)
    assert result.ok is False
    assert result.attempts == 1
    assert result.status == 400
    assert len(requests) == 1


def test_unknown_source_is_rejected_without_network() -> None:
    transport, requests = _transport(lambda request: httpx.Response(200))
    with pytest.raises(ValueError):
        fetch_source("fred", transport=transport)
    with pytest.raises(ValueError):
        fetch_source(
            "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500", transport=transport
        )
    assert requests == []


def test_invalid_parameters_are_rejected() -> None:
    transport, _ = _transport(lambda request: httpx.Response(200))
    with pytest.raises(ValueError):
        fetch_source("fred_sp500", transport=transport, max_attempts=0)
    with pytest.raises(ValueError):
        fetch_source("fred_sp500", transport=transport, timeout_seconds=0)
    with pytest.raises(ValueError):
        fetch_source("fred_sp500", transport=transport, backoff_seconds=-1)


def test_configured_timeout_reaches_the_request() -> None:
    transport, requests = _transport(lambda request: httpx.Response(200))
    result = fetch_source("fred_sp500", transport=transport, timeout_seconds=7.5)
    assert result.timeout_seconds == 7.5
    timeout = requests[0].extensions.get("timeout")
    assert isinstance(timeout, dict)
    assert timeout.get("read") == 7.5


def test_injected_transport_is_not_closed_by_the_fetcher() -> None:
    class TrackingTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.closed = False
            self.calls = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.calls += 1
            return httpx.Response(200, content=b"ok")

        def close(self) -> None:
            self.closed = True

    transport = TrackingTransport()
    fetch_source("fred_sp500", transport=transport)
    fetch_source("cboe_vix", transport=transport)
    assert transport.closed is False
    assert transport.calls == 2


def test_fetch_all_returns_one_result_per_source_and_propagates_errors() -> None:
    transport, requests = _transport(
        lambda request: httpx.Response(
            200 if "fred" in str(request.url) else 503,
            content=b"ok" if "fred" in str(request.url) else b"",
        )
    )
    results = fetch_all(
        ["fred_sp500", "cboe_vix"], transport=transport, max_attempts=1, backoff_seconds=0
    )
    assert set(results) == {"fred_sp500", "cboe_vix"}
    assert results["fred_sp500"].ok is True
    assert results["cboe_vix"].ok is False
    assert str(requests[0].url) in EXPECTED_URLS.values()
    with pytest.raises(ValueError):
        fetch_all(["fred_sp500", "unknown"], transport=transport)


def test_result_is_a_frozen_dataclass() -> None:
    transport, _ = _transport(lambda request: httpx.Response(200, content=b"ok"))
    result = fetch_source("fred_sp500", transport=transport)
    with pytest.raises(FrozenInstanceError):
        result.status = 500  # type: ignore[misc]
    assert json.dumps({"source": result.source_id, "status": result.status})
