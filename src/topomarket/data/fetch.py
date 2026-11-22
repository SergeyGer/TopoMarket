"""Credential-free HTTP fetch primitive for the fixed TopoMarket provider sources.

The fetch layer is deliberately small and strict:

* the source registry is immutable and contains exactly the four documented URLs;
* callers cannot supply generic headers, credentials, cookies, auth or a client -
  the only test hook is an optional ``httpx.BaseTransport`` (mock transport);
* conditional requests are built only from explicit validator arguments;
* redirects are never followed, retries are bounded and deterministic, and the
  final response metadata (including ``Retry-After``) is preserved on failures.

The module performs no work at import time and never touches private data.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

import httpx

#: Immutable authoritative registry: source id -> exact provider URL.
SOURCES: Mapping[str, str] = MappingProxyType(
    {
        "fred_sp500": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=SP500",
        "cboe_vix": "https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv",
        "french_12_industries": (
            "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
            "12_Industry_Portfolios_daily_CSV.zip"
        ),
        "ofr_fsi": "https://www.financialresearch.gov/financial-stress-index/data/fsi.csv",
    }
)

_USER_AGENT = "topomarket-fetch/1.0 (+https://github.com/SergeyGer/TopoMarket)"
_RETRYABLE_STATUSES = frozenset({429, *range(500, 600)})


@dataclass(frozen=True, slots=True)
class FetchResult:
    """Outcome of one bounded provider fetch attempt sequence."""

    source_id: str
    url: str
    status: int | None
    not_modified: bool
    conditional_requested: bool
    body: bytes | None
    headers: Mapping[str, str]
    etag: str | None
    last_modified: str | None
    attempts: int
    timeout_seconds: float
    error: str | None
    fetched_at_utc: str

    @property
    def ok(self) -> bool:
        return self.error is None and (self.status == 200 or self.not_modified)


class _NonClosingTransport(httpx.BaseTransport):
    """Delegate to a caller-owned transport without letting the client close it."""

    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return self._transport.handle_request(request)

    def close(self) -> None:  # pragma: no cover - intentionally does nothing
        return None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _header_map(response: httpx.Response) -> Mapping[str, str]:
    return MappingProxyType({key.lower(): value for key, value in response.headers.items()})


def _retry_after_seconds(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("retry-after")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except ValueError:
        return None


def fetch_source(
    source_id: str,
    *,
    etag: str | None = None,
    last_modified: str | None = None,
    timeout_seconds: float = 15.0,
    max_attempts: int = 3,
    backoff_seconds: float = 1.0,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] | None = None,
) -> FetchResult:
    """Fetch one fixed provider source with conditional GET and bounded retries.

    Only ``SOURCES`` keys are accepted; aliases and literal URLs are rejected before any
    network work. No credentials, cookies or custom auth headers can be supplied.
    """
    if source_id not in SOURCES:
        raise ValueError(f"unknown source id {source_id!r}; expected one of {sorted(SOURCES)}")
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    if backoff_seconds < 0:
        raise ValueError("backoff_seconds must not be negative")

    url = SOURCES[source_id]
    conditional_headers: dict[str, str] = {}
    if etag:
        conditional_headers["If-None-Match"] = etag
    if last_modified:
        conditional_headers["If-Modified-Since"] = last_modified
    conditional_requested = bool(conditional_headers)
    sleeper = sleep or time.sleep
    client_transport = _NonClosingTransport(transport) if transport is not None else None

    attempts = 0
    status: int | None = None
    headers: Mapping[str, str] = MappingProxyType({})
    error: str | None = None

    for attempt_number in range(1, max_attempts + 1):
        attempts = attempt_number
        retry_after: float | None = None
        try:
            with httpx.Client(
                transport=client_transport,
                timeout=timeout_seconds,
                follow_redirects=False,
                headers={"User-Agent": _USER_AGENT},
            ) as client:
                response = client.get(url, headers=conditional_headers or None)
        except httpx.TimeoutException as exc:
            status = None
            headers = MappingProxyType({})
            error = f"provider request timed out after {timeout_seconds:g}s: {type(exc).__name__}"
            retryable = True
        except httpx.TransportError as exc:
            status = None
            headers = MappingProxyType({})
            error = f"provider transport error: {type(exc).__name__}"
            retryable = True
        else:
            status = response.status_code
            headers = _header_map(response)
            retry_after = _retry_after_seconds(headers)
            if status == 200:
                return FetchResult(
                    source_id=source_id,
                    url=url,
                    status=status,
                    not_modified=False,
                    conditional_requested=conditional_requested,
                    body=response.content,
                    headers=headers,
                    etag=headers.get("etag"),
                    last_modified=headers.get("last-modified"),
                    attempts=attempts,
                    timeout_seconds=timeout_seconds,
                    error=None,
                    fetched_at_utc=_now_iso(),
                )
            if status == 304:
                if not conditional_requested:
                    return FetchResult(
                        source_id=source_id,
                        url=url,
                        status=status,
                        not_modified=False,
                        conditional_requested=False,
                        body=None,
                        headers=headers,
                        etag=None,
                        last_modified=None,
                        attempts=attempts,
                        timeout_seconds=timeout_seconds,
                        error="provider returned 304 Not Modified for an unconditional request",
                        fetched_at_utc=_now_iso(),
                    )
                return FetchResult(
                    source_id=source_id,
                    url=url,
                    status=status,
                    not_modified=True,
                    conditional_requested=True,
                    body=None,
                    headers=headers,
                    etag=headers.get("etag") or etag,
                    last_modified=headers.get("last-modified") or last_modified,
                    attempts=attempts,
                    timeout_seconds=timeout_seconds,
                    error=None,
                    fetched_at_utc=_now_iso(),
                )
            if 300 <= status < 400:
                error = (
                    f"provider returned an unexpected redirect/status {status} (redirects disabled)"
                )
                retryable = False
            elif status in _RETRYABLE_STATUSES:
                error = f"provider returned retryable HTTP {status}"
                retryable = True
            else:
                error = f"provider returned HTTP {status}"
                retryable = False

        if not retryable or attempt_number >= max_attempts:
            break
        delay = backoff_seconds * (2 ** (attempt_number - 1))
        if retry_after is not None:
            delay = max(delay, retry_after)
        if delay > 0:
            sleeper(delay)

    return FetchResult(
        source_id=source_id,
        url=url,
        status=status,
        not_modified=False,
        conditional_requested=conditional_requested,
        body=None,
        headers=headers,
        etag=None,
        last_modified=None,
        attempts=attempts,
        timeout_seconds=timeout_seconds,
        error=error or "fetch failed",
        fetched_at_utc=_now_iso(),
    )


def fetch_all(
    source_ids: list[str] | tuple[str, ...],
    **kwargs: object,
) -> dict[str, FetchResult]:
    """Fetch multiple known sources with the same settings; one result per source."""
    return {source_id: fetch_source(source_id, **kwargs) for source_id in source_ids}


def source_ids() -> tuple[str, ...]:
    """Return the authoritative source ids in stable order."""
    return tuple(SOURCES)


__all__ = ["SOURCES", "FetchResult", "fetch_all", "fetch_source", "source_ids"]
