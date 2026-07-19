from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import NoReturn, cast

import httpx

from market_trader.catalysts.adapters.http import (
    BoundedJsonFetcher,
    HttpFailure,
    HttpFailureCode,
    RequestLimiter,
)
from market_trader.catalysts.configuration import CatalystConfiguration
from market_trader.catalysts.models import (
    CatalystProviderEvent,
    EventFamily,
    SourceFailure,
    SourceFailureKind,
)
from market_trader.catalysts.providers import ProviderBatch, SecFilingRequest

SOURCE_ID = "sec-edgar-public-v1"
SEC_ORIGIN = "https://data.sec.gov"
_ACCEPTED_FORMS = frozenset(("8-K", "10-Q", "10-K", "6-K", "20-F", "40-F"))
_SUBMISSION_COLUMNS = (
    "accessionNumber",
    "acceptanceDateTime",
    "filingDate",
    "form",
    "items",
    "primaryDocDescription",
)
_XBRL_FACTS = frozenset(
    (
        "EarningsPerShareDiluted",
        "NetIncomeLoss",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
    )
)
_HEADERS = {
    "Accept": "application/json",
    "Accept-Encoding": "gzip, deflate",
}


class _SecParseFailure(ValueError):
    def __init__(self, kind: SourceFailureKind, reason: str) -> None:
        self.kind = kind
        self.reason = reason
        super().__init__(reason)


class SecEdgarAdapter:
    def __init__(
        self,
        *,
        client: httpx.Client,
        configuration: CatalystConfiguration,
        user_agent: str,
        limiter: RequestLimiter,
        sleeper: Callable[[float], None],
    ) -> None:
        if "@" not in user_agent or any(character in user_agent for character in "\r\n"):
            raise ValueError("SEC User-Agent must identify an application and contact")
        source = configuration.sources.by_id[SOURCE_ID]
        if source.origins != (SEC_ORIGIN,) or source.allow_redirects:
            raise ValueError("SEC source origin policy is invalid")
        self._configuration = configuration
        self._headers = {**_HEADERS, "User-Agent": user_agent}
        self._fetcher = BoundedJsonFetcher(
            client=client,
            source_id=SOURCE_ID,
            allowed_origins=source.origins,
            limiter=limiter,
            sleeper=sleeper,
            max_response_bytes=source.max_response_bytes,
        )

    def sec_filings(self, request: SecFilingRequest) -> ProviderBatch | SourceFailure:
        events: list[CatalystProviderEvent] = []
        for symbol in request.symbols:
            cik = self._configuration.sources.company_ciks.get(symbol)
            if cik is None:
                return self._failure(
                    request,
                    SourceFailureKind.UNSUPPORTED,
                    "sec_symbol_unsupported",
                )
            submissions = self._fetch(
                request,
                f"{SEC_ORIGIN}/submissions/CIK{cik}.json",
            )
            if isinstance(submissions, SourceFailure):
                return submissions
            try:
                events.extend(
                    _parse_submissions(
                        submissions,
                        symbol=symbol,
                        cik=cik,
                        as_of=request.as_of,
                    )
                )
            except _SecParseFailure as error:
                return self._failure(request, error.kind, error.reason)

            companyfacts = self._fetch(
                request,
                f"{SEC_ORIGIN}/api/xbrl/companyfacts/CIK{cik}.json",
            )
            if isinstance(companyfacts, SourceFailure):
                return self._failure(
                    request,
                    SourceFailureKind.PARTIAL,
                    "sec_companyfacts_partial",
                )
            try:
                events.extend(
                    _parse_companyfacts(
                        companyfacts,
                        symbol=symbol,
                        cik=cik,
                        as_of=request.as_of,
                    )
                )
            except _SecParseFailure:
                return self._failure(
                    request,
                    SourceFailureKind.PARTIAL,
                    "sec_companyfacts_partial",
                )
        if not events:
            return self._failure(request, SourceFailureKind.PARTIAL, "sec_no_events")
        return ProviderBatch(source_id=SOURCE_ID, as_of=request.as_of, events=tuple(events))

    def _fetch(
        self,
        request: SecFilingRequest,
        url: str,
    ) -> object | SourceFailure:
        result = self._fetcher.get(url, headers=self._headers)
        if result.failure is not None:
            return self._http_failure(request, result.failure)
        return result.payload

    def _http_failure(
        self,
        request: SecFilingRequest,
        failure: HttpFailure,
    ) -> SourceFailure:
        if failure.code is HttpFailureCode.HTTP_STATUS:
            reason = f"sec_http_{failure.status_code}"
        else:
            reason = f"sec_{failure.code.value}"
        return self._failure(request, failure.kind, reason)

    @staticmethod
    def _failure(
        request: SecFilingRequest,
        kind: SourceFailureKind,
        reason: str,
    ) -> SourceFailure:
        return SourceFailure(
            source_id=SOURCE_ID,
            kind=kind,
            occurred_at=request.as_of,
            reasons=(reason,),
        )


def _parse_submissions(
    payload: object,
    *,
    symbol: str,
    cik: str,
    as_of: datetime,
) -> tuple[CatalystProviderEvent, ...]:
    root = _mapping(payload, "sec_submissions_schema_drift")
    filings = _mapping(root.get("filings"), "sec_submissions_schema_drift")
    recent = _mapping(filings.get("recent"), "sec_submissions_schema_drift")
    missing = [column for column in _SUBMISSION_COLUMNS if column not in recent]
    if missing:
        _parse_fail(SourceFailureKind.PARTIAL, "sec_submission_columns_partial")
    columns = {column: _list(recent[column]) for column in _SUBMISSION_COLUMNS}
    lengths = {len(values) for values in columns.values()}
    if len(lengths) != 1:
        _parse_fail(
            SourceFailureKind.MALFORMED,
            "sec_submission_column_length_mismatch",
        )
    events: list[CatalystProviderEvent] = []
    for index in range(next(iter(lengths), 0)):
        form = _string(columns["form"][index], "sec_invalid_form")
        if form.removesuffix("/A") not in _ACCEPTED_FORMS:
            continue
        accession = _string(columns["accessionNumber"][index], "sec_invalid_accession")
        published_at = _timestamp(columns["acceptanceDateTime"][index])
        filing_date = _date_string(columns["filingDate"][index])
        items = tuple(
            item.strip()
            for item in _string_or_empty(columns["items"][index]).split(",")
            if item.strip()
        )
        description = _string_or_empty(columns["primaryDocDescription"][index])
        events.append(
            CatalystProviderEvent(
                source_id=SOURCE_ID,
                provider_event_id=f"filing:{cik}:{accession}",
                event_family=EventFamily.SEC_FILING,
                provider_schema_version=1,
                published_at=published_at,
                ingested_at=as_of,
                scheduled_for=None,
                symbol_identity=symbol,
                structured_fields={
                    "event_category": "sec_filing",
                    "accession_number": accession,
                    "cik": cik,
                    "filing_date": filing_date,
                    "form": form,
                    "items": items,
                },
                external_text={"description": description},
                source_reference=(
                    f"{SEC_ORIGIN}/submissions/CIK{cik}.json#{accession}"
                ),
                correlation_id=f"sec:{cik}:{accession}",
            )
        )
    return tuple(events)


def _parse_companyfacts(
    payload: object,
    *,
    symbol: str,
    cik: str,
    as_of: datetime,
) -> tuple[CatalystProviderEvent, ...]:
    root = _mapping(payload, "sec_companyfacts_schema_drift")
    facts = _mapping(root.get("facts"), "sec_companyfacts_schema_drift")
    us_gaap = _mapping(facts.get("us-gaap"), "sec_companyfacts_schema_drift")
    events: list[CatalystProviderEvent] = []
    for fact_name in sorted(set(us_gaap) & _XBRL_FACTS):
        fact = _mapping(us_gaap[fact_name], "sec_companyfact_malformed")
        units = _mapping(fact.get("units"), "sec_companyfact_malformed")
        for unit, raw_records in sorted(units.items()):
            records = _list(raw_records)
            if not records:
                continue
            record = _mapping(records[-1], "sec_companyfact_malformed")
            accession = _string(record.get("accn"), "sec_companyfact_malformed")
            form = _string(record.get("form"), "sec_companyfact_malformed")
            if form.removesuffix("/A") not in _ACCEPTED_FORMS:
                continue
            filed = _date_string(record.get("filed"))
            value = _numeric_string(record.get("val"))
            fiscal_year = _integer(record.get("fy"))
            fiscal_period = _string(record.get("fp"), "sec_companyfact_malformed")
            event_id = f"fact:{cik}:{fact_name}:{unit}:{accession}:{fiscal_year}:{fiscal_period}"
            events.append(
                CatalystProviderEvent(
                    source_id=SOURCE_ID,
                    provider_event_id=event_id,
                    event_family=EventFamily.SEC_FILING,
                    provider_schema_version=1,
                    published_at=datetime.combine(
                        date.fromisoformat(filed),
                        datetime.min.time(),
                        tzinfo=UTC,
                    ),
                    ingested_at=as_of,
                    scheduled_for=None,
                    symbol_identity=symbol,
                    structured_fields={
                        "event_category": "sec_filing",
                        "accession_number": accession,
                        "cik": cik,
                        "fact_name": fact_name,
                        "filing_date": filed,
                        "fiscal_period": fiscal_period,
                        "fiscal_year": fiscal_year,
                        "form": form,
                        "unit": unit,
                        "value": value,
                    },
                    external_text={
                        "description": fact.get("description", ""),
                        "label": fact.get("label", ""),
                    },
                    source_reference=(
                        f"{SEC_ORIGIN}/api/xbrl/companyfacts/CIK{cik}.json#{fact_name}"
                    ),
                    correlation_id=f"sec:{cik}:{accession}",
                )
            )
    return tuple(events)


def _mapping(value: object, reason: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        _parse_fail(SourceFailureKind.MALFORMED, reason)
    return cast(Mapping[str, object], value)


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        _parse_fail(SourceFailureKind.MALFORMED, "sec_companyfact_malformed")
    return value


def _string(value: object, reason: str) -> str:
    if not isinstance(value, str) or not value:
        _parse_fail(SourceFailureKind.MALFORMED, reason)
    return value


def _string_or_empty(value: object) -> str:
    if not isinstance(value, str):
        _parse_fail(SourceFailureKind.MALFORMED, "sec_invalid_string")
    return value


def _timestamp(value: object) -> datetime:
    raw = _string(value, "sec_invalid_timestamp")
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        _parse_fail(SourceFailureKind.MALFORMED, "sec_invalid_timestamp")
    if parsed.tzinfo is None:
        _parse_fail(SourceFailureKind.MALFORMED, "sec_invalid_timestamp")
    return parsed.astimezone(UTC)


def _date_string(value: object) -> str:
    raw = _string(value, "sec_invalid_date")
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        _parse_fail(SourceFailureKind.MALFORMED, "sec_invalid_date")


def _numeric_string(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        _parse_fail(SourceFailureKind.MALFORMED, "sec_invalid_numeric_fact")
    try:
        parsed = Decimal(value)
    except Exception:
        _parse_fail(SourceFailureKind.MALFORMED, "sec_invalid_numeric_fact")
    if not parsed.is_finite():
        _parse_fail(SourceFailureKind.MALFORMED, "sec_invalid_numeric_fact")
    return format(parsed, "f")


def _integer(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        _parse_fail(SourceFailureKind.MALFORMED, "sec_invalid_integer")
    return value


def _parse_fail(kind: SourceFailureKind, reason: str) -> NoReturn:
    raise _SecParseFailure(kind, reason)
