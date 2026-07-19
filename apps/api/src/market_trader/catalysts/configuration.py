import json
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from types import MappingProxyType

from market_trader.catalysts.models import AuthorityClass, CatalystDirection, Materiality
from market_trader.market_data.sanitization import canonical_digest, sanitize_payload

_SOURCE_FILE = "catalyst-source-policy-v1.json"
_CLASSIFICATION_FILE = "catalyst-classification-policy-v1.json"
_RISK_FILE = "event-risk-policy-v1.json"
_SUMMARY_FILE = "catalyst-summary-policy-v1.json"


@dataclass(frozen=True)
class SourceDefinition:
    source_id: str
    authority_class: AuthorityClass
    origins: tuple[str, ...]
    max_requests: int
    rate_period_seconds: int
    daily_request_limit: int | None
    max_response_bytes: int
    allow_redirects: bool


@dataclass(frozen=True)
class SourcePolicy:
    version: str
    by_id: Mapping[str, SourceDefinition]
    company_ciks: Mapping[str, str]
    unsupported_fund_symbols: tuple[str, ...]
    bls_series: Mapping[str, str]


@dataclass(frozen=True)
class ClassificationPolicy:
    version: str
    earnings_surprise_threshold: Decimal
    social_freshness_minutes: int
    categories: Mapping[str, tuple[Materiality, CatalystDirection]]


@dataclass(frozen=True)
class EventRiskPolicy:
    version: str
    earnings_sessions_before: int
    require_full_session_after: bool
    macro_minutes_before: int
    macro_minutes_after: int
    high_impact_macro: tuple[str, ...]


@dataclass(frozen=True)
class SummaryPolicy:
    version: str
    max_text_characters: int
    require_segment_citations: bool


@dataclass(frozen=True)
class CatalystConfiguration:
    sources: SourcePolicy
    classification: ClassificationPolicy
    risk: EventRiskPolicy
    summary: SummaryPolicy
    content_hashes: Mapping[str, str]


def load_catalyst_configuration(path: Path | str) -> CatalystConfiguration:
    root = Path(path)
    source_payload = _load_document(root / _SOURCE_FILE)
    classification_payload = _load_document(root / _CLASSIFICATION_FILE)
    risk_payload = _load_document(root / _RISK_FILE)
    summary_payload = _load_document(root / _SUMMARY_FILE)
    return CatalystConfiguration(
        sources=_parse_sources(source_payload),
        classification=_parse_classification(classification_payload),
        risk=_parse_risk(risk_payload),
        summary=_parse_summary(summary_payload),
        content_hashes=MappingProxyType(
            {
                "classification": _declared_hash(classification_payload),
                "risk": _declared_hash(risk_payload),
                "sources": _declared_hash(source_payload),
                "summary": _declared_hash(summary_payload),
            }
        ),
    )


def _load_document(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(), parse_float=_reject_json_float)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid catalyst configuration: {path.name}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"catalyst configuration must be an object: {path.name}")
    return value


def _reject_json_float(value: str) -> object:
    raise ValueError("catalyst policy decimal values must be strings")


def _verify_document(
    payload: Mapping[str, object],
    *,
    expected_keys: set[str],
    expected_version: str,
) -> None:
    unknown = set(payload) - expected_keys
    missing = expected_keys - set(payload)
    if unknown:
        raise ValueError(f"catalyst policy has unknown keys: {sorted(unknown)}")
    if missing:
        raise ValueError(f"catalyst policy has missing keys: {sorted(missing)}")
    if payload["version"] != expected_version:
        raise ValueError(f"catalyst policy version must be {expected_version}")
    declared = _declared_hash(payload)
    canonical = {key: value for key, value in payload.items() if key != "content_hash"}
    actual = canonical_digest(sanitize_payload(canonical))
    if declared != actual:
        raise ValueError("catalyst policy content hash mismatch")


def _declared_hash(payload: Mapping[str, object]) -> str:
    value = payload.get("content_hash")
    if not isinstance(value, str):
        raise ValueError("catalyst policy content hash must be a string")
    return value


def _parse_sources(payload: Mapping[str, object]) -> SourcePolicy:
    _verify_document(
        payload,
        expected_keys={
            "version",
            "content_hash",
            "sources",
            "company_ciks",
            "unsupported_fund_symbols",
            "bls_series",
        },
        expected_version="catalyst-source-policy-v1",
    )
    raw_sources = _list(payload["sources"], "sources")
    parsed: dict[str, SourceDefinition] = {}
    source_keys = {
        "source_id",
        "authority_class",
        "origins",
        "max_requests",
        "rate_period_seconds",
        "daily_request_limit",
        "max_response_bytes",
        "allow_redirects",
    }
    for item in raw_sources:
        record = _mapping(item, "source")
        _exact_keys(record, source_keys, "source")
        source_id = _string(record["source_id"], "source_id")
        if source_id in parsed:
            raise ValueError(f"duplicate catalyst source: {source_id}")
        parsed[source_id] = SourceDefinition(
            source_id=source_id,
            authority_class=AuthorityClass(_string(record["authority_class"], "authority_class")),
            origins=tuple(
                _string(value, "origin")
                for value in _list(record["origins"], "origins")
            ),
            max_requests=_integer(record["max_requests"], "max_requests"),
            rate_period_seconds=_integer(record["rate_period_seconds"], "rate_period_seconds"),
            daily_request_limit=(
                None
                if record["daily_request_limit"] is None
                else _integer(record["daily_request_limit"], "daily_request_limit")
            ),
            max_response_bytes=_integer(record["max_response_bytes"], "max_response_bytes"),
            allow_redirects=_boolean(record["allow_redirects"], "allow_redirects"),
        )
    company_ciks = _string_mapping(payload["company_ciks"], "company_ciks")
    invalid_cik = any(
        len(value) != 10 or not value.isdigit() for value in company_ciks.values()
    )
    if len(company_ciks) != 15 or invalid_cik:
        raise ValueError("company CIK policy must contain 15 ten-digit values")
    raw_funds = _list(
        payload["unsupported_fund_symbols"],
        "unsupported_fund_symbols",
    )
    funds = tuple(sorted(_string(value, "fund symbol") for value in raw_funds))
    if len(funds) != 15 or len(set(funds)) != 15:
        raise ValueError("unsupported fund policy must contain 15 unique symbols")
    bls_series = _string_mapping(payload["bls_series"], "bls_series")
    return SourcePolicy(
        version="catalyst-source-policy-v1",
        by_id=MappingProxyType(dict(sorted(parsed.items()))),
        company_ciks=MappingProxyType(dict(sorted(company_ciks.items()))),
        unsupported_fund_symbols=funds,
        bls_series=MappingProxyType(dict(sorted(bls_series.items()))),
    )


def _parse_classification(payload: Mapping[str, object]) -> ClassificationPolicy:
    _verify_document(
        payload,
        expected_keys={
            "version",
            "content_hash",
            "earnings_surprise_threshold",
            "social_freshness_minutes",
            "categories",
        },
        expected_version="catalyst-classification-policy-v1",
    )
    threshold = _decimal_string(payload["earnings_surprise_threshold"])
    categories: dict[str, tuple[Materiality, CatalystDirection]] = {}
    for name, value in _mapping(payload["categories"], "categories").items():
        record = _mapping(value, f"category {name}")
        _exact_keys(record, {"materiality", "direction"}, f"category {name}")
        categories[name] = (
            Materiality(_string(record["materiality"], "materiality")),
            CatalystDirection(_string(record["direction"], "direction")),
        )
    if len(categories) != 10:
        raise ValueError("classification policy must contain 10 categories")
    return ClassificationPolicy(
        version="catalyst-classification-policy-v1",
        earnings_surprise_threshold=threshold,
        social_freshness_minutes=_integer(
            payload["social_freshness_minutes"],
            "social_freshness_minutes",
        ),
        categories=MappingProxyType(dict(sorted(categories.items()))),
    )


def _parse_risk(payload: Mapping[str, object]) -> EventRiskPolicy:
    _verify_document(
        payload,
        expected_keys={
            "version",
            "content_hash",
            "earnings_sessions_before",
            "require_full_session_after",
            "macro_minutes_before",
            "macro_minutes_after",
            "high_impact_macro",
        },
        expected_version="event-risk-policy-v1",
    )
    return EventRiskPolicy(
        version="event-risk-policy-v1",
        earnings_sessions_before=_integer(
            payload["earnings_sessions_before"],
            "earnings_sessions_before",
        ),
        require_full_session_after=_boolean(
            payload["require_full_session_after"],
            "require_full_session_after",
        ),
        macro_minutes_before=_integer(payload["macro_minutes_before"], "macro_minutes_before"),
        macro_minutes_after=_integer(payload["macro_minutes_after"], "macro_minutes_after"),
        high_impact_macro=tuple(
            sorted(
                _string(value, "macro category")
                for value in _list(payload["high_impact_macro"], "high_impact_macro")
            )
        ),
    )


def _parse_summary(payload: Mapping[str, object]) -> SummaryPolicy:
    _verify_document(
        payload,
        expected_keys={
            "version",
            "content_hash",
            "max_text_characters",
            "require_segment_citations",
        },
        expected_version="catalyst-summary-policy-v1",
    )
    return SummaryPolicy(
        version="catalyst-summary-policy-v1",
        max_text_characters=_integer(payload["max_text_characters"], "max_text_characters"),
        require_segment_citations=_boolean(
            payload["require_segment_citations"],
            "require_segment_citations",
        ),
    )


def _exact_keys(value: Mapping[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} has unknown or missing keys")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _string_mapping(value: object, label: str) -> dict[str, str]:
    return {str(key): _string(item, label) for key, item in _mapping(value, label).items()}


def _list(value: object, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty string")
    return value


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean")
    return value


def _decimal_string(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("catalyst policy decimal values must be strings")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("catalyst policy decimal string is invalid") from exc
