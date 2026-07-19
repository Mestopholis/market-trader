import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from urllib.parse import urlsplit

import httpx

from market_trader.catalysts.models import SourceFailureKind

MAX_RETRIES = 2
MAX_RETRY_DELAY_SECONDS = 5.0


class RequestLimiter(Protocol):
    def acquire(self, source_id: str) -> bool: ...


class HttpFailureCode(StrEnum):
    LOCAL_RATE_LIMIT = "local_rate_limit"
    TIMEOUT = "timeout"
    RESPONSE_TOO_LARGE = "response_too_large"
    REDIRECT_REJECTED = "redirect_rejected"
    INVALID_JSON = "invalid_json"
    HTTP_STATUS = "http_status"


@dataclass(frozen=True)
class HttpFailure:
    kind: SourceFailureKind
    code: HttpFailureCode
    status_code: int | None = None
    retry_after: str | None = None


@dataclass(frozen=True)
class JsonFetchResult:
    payload: object | None = None
    failure: HttpFailure | None = None

    def __post_init__(self) -> None:
        if (self.payload is None) == (self.failure is None):
            raise ValueError("JSON fetch result requires exactly one outcome")


class BoundedJsonFetcher:
    def __init__(
        self,
        *,
        client: httpx.Client,
        source_id: str,
        allowed_origins: tuple[str, ...],
        limiter: RequestLimiter,
        sleeper: Callable[[float], None],
        max_response_bytes: int,
    ) -> None:
        _validate_client(client)
        self._client = client
        self._source_id = source_id
        self._allowed_origins = allowed_origins
        self._limiter = limiter
        self._sleeper = sleeper
        self._max_response_bytes = max_response_bytes

    def get(self, url: str, *, headers: Mapping[str, str]) -> JsonFetchResult:
        if _origin(url) not in self._allowed_origins:
            return JsonFetchResult(
                failure=HttpFailure(
                    SourceFailureKind.SECURITY_REJECTED,
                    HttpFailureCode.REDIRECT_REJECTED,
                )
            )
        for attempt in range(MAX_RETRIES + 1):
            if not self._limiter.acquire(self._source_id):
                return JsonFetchResult(
                    failure=HttpFailure(
                        SourceFailureKind.THROTTLED,
                        HttpFailureCode.LOCAL_RATE_LIMIT,
                    )
                )
            try:
                result = self._request(url, headers=headers)
            except httpx.TimeoutException:
                if attempt < MAX_RETRIES:
                    self._sleeper(_retry_delay(None, attempt))
                    continue
                return JsonFetchResult(
                    failure=HttpFailure(
                        SourceFailureKind.UNAVAILABLE,
                        HttpFailureCode.TIMEOUT,
                    )
                )
            if result.failure is None:
                return result
            failure = result.failure
            retryable = failure.status_code == 429 or (
                failure.status_code is not None and 500 <= failure.status_code <= 599
            )
            if retryable and attempt < MAX_RETRIES:
                self._sleeper(_retry_delay(failure.retry_after, attempt))
                continue
            return result
        raise AssertionError("unreachable bounded retry state")

    def _request(self, url: str, *, headers: Mapping[str, str]) -> JsonFetchResult:
        with self._client.stream("GET", url, headers=headers) as response:
            if 300 <= response.status_code <= 399:
                return JsonFetchResult(
                    failure=HttpFailure(
                        SourceFailureKind.SECURITY_REJECTED,
                        HttpFailureCode.REDIRECT_REJECTED,
                        response.status_code,
                    )
                )
            if response.status_code >= 400:
                kind = (
                    SourceFailureKind.THROTTLED
                    if response.status_code == 429
                    else SourceFailureKind.UNAVAILABLE
                )
                result = JsonFetchResult(
                    failure=HttpFailure(
                        kind,
                        HttpFailureCode.HTTP_STATUS,
                        response.status_code,
                        response.headers.get("Retry-After"),
                    )
                )
                return result
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > self._max_response_bytes:
                    return JsonFetchResult(
                        failure=HttpFailure(
                            SourceFailureKind.SECURITY_REJECTED,
                            HttpFailureCode.RESPONSE_TOO_LARGE,
                        )
                    )
        try:
            return JsonFetchResult(payload=json.loads(body))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return JsonFetchResult(
                failure=HttpFailure(
                    SourceFailureKind.MALFORMED,
                    HttpFailureCode.INVALID_JSON,
                )
            )


def _validate_client(client: httpx.Client) -> None:
    if client.follow_redirects:
        raise ValueError("HTTP client redirect policy must be disabled")
    timeout = client.timeout
    values = (timeout.read, timeout.write, timeout.pool)
    if timeout.connect is None or timeout.connect > 10.0:
        raise ValueError("HTTP client connect timeout exceeds policy")
    if any(value is None or value > 20.0 for value in values):
        raise ValueError("HTTP client total timeout exceeds policy")


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return ""
    port = "" if parsed.port is None else f":{parsed.port}"
    return f"{parsed.scheme}://{parsed.hostname}{port}"


def _retry_delay(retry_after: object, attempt: int) -> float:
    if isinstance(retry_after, str):
        try:
            requested = float(retry_after)
        except ValueError:
            requested = 0.0
        if requested >= 0:
            return min(requested, MAX_RETRY_DELAY_SECONDS)
    return min(float(attempt + 1), MAX_RETRY_DELAY_SECONDS)
