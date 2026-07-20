from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from market_trader.domain.time import ensure_utc

MAX_DISPLAY_TEXT = 200
SECRET_KEY_PARTS = ("secret", "token", "password", "credential", "api_key")


class DataState(StrEnum):
    READY = "ready"
    STALE = "stale"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class DashboardModel(BaseModel):
    model_config = ConfigDict(frozen=True)


class SourceSummary(DashboardModel):
    name: str
    state: DataState
    version: str
    observed_at: datetime
    stable_key: str
    digest: str | None = None

    @field_validator("observed_at")
    @classmethod
    def _observed_at_must_be_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class WarningSummary(DashboardModel):
    code: str
    severity: str
    message: str
    source_keys: tuple[str, ...]

    @field_validator("message")
    @classmethod
    def _bound_message(cls, value: str) -> str:
        return value[:MAX_DISPLAY_TEXT]

    @field_validator("source_keys")
    @classmethod
    def _sort_source_keys(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(value))


class DashboardOverview(DashboardModel):
    as_of: datetime
    data_state: DataState
    paper_mode: bool
    market_state: str
    entry_allowed: bool
    sources: tuple[SourceSummary, ...]
    warnings: tuple[WarningSummary, ...]

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("sources")
    @classmethod
    def _sort_sources(cls, value: tuple[SourceSummary, ...]) -> tuple[SourceSummary, ...]:
        return tuple(sorted(value, key=lambda source: source.name))


class CandidateListItem(DashboardModel):
    candidate_key: str
    symbol: str
    direction: str
    strategy: str
    score: str
    qualification_state: str
    catalyst_state: str
    risk_state: str
    data_state: DataState
    observed_at: datetime
    reason_codes: tuple[str, ...]
    source_keys: tuple[str, ...]

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("observed_at")
    @classmethod
    def _observed_at_must_be_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("reason_codes", "source_keys")
    @classmethod
    def _sort_strings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(value))


class CandidateListResponse(DashboardModel):
    as_of: datetime
    data_state: DataState
    candidates: tuple[CandidateListItem, ...]
    next_cursor: str | None
    sources: tuple[SourceSummary, ...]
    warnings: tuple[WarningSummary, ...]

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("candidates")
    @classmethod
    def _sort_candidates(
        cls,
        value: tuple[CandidateListItem, ...],
    ) -> tuple[CandidateListItem, ...]:
        return tuple(
            sorted(value, key=lambda candidate: (candidate.symbol, candidate.candidate_key))
        )

    @field_validator("sources")
    @classmethod
    def _sort_sources(cls, value: tuple[SourceSummary, ...]) -> tuple[SourceSummary, ...]:
        return tuple(sorted(value, key=lambda source: source.name))


class CandidateDetail(DashboardModel):
    candidate_key: str
    symbol: str
    data_state: DataState
    as_of: datetime
    scanner: dict[str, object]
    catalysts: dict[str, object]
    options: dict[str, object]
    risk: dict[str, object]
    sources: tuple[SourceSummary, ...]
    warnings: tuple[WarningSummary, ...]

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("sources")
    @classmethod
    def _sort_sources(cls, value: tuple[SourceSummary, ...]) -> tuple[SourceSummary, ...]:
        return tuple(sorted(value, key=lambda source: source.name))

    @model_validator(mode="after")
    def _reject_secret_payload_keys(self) -> Self:
        for payload in (self.scanner, self.catalysts, self.options, self.risk):
            _reject_secret_like_keys(payload)
        return self


class RiskSummary(DashboardModel):
    as_of: datetime
    data_state: DataState
    latest_decision_key: str | None
    status: str
    checks: tuple[WarningSummary, ...]
    active_locks: tuple[str, ...]
    tax_disclaimer: str
    sources: tuple[SourceSummary, ...]
    warnings: tuple[WarningSummary, ...]

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("active_locks")
    @classmethod
    def _sort_active_locks(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(value))

    @field_validator("sources")
    @classmethod
    def _sort_sources(cls, value: tuple[SourceSummary, ...]) -> tuple[SourceSummary, ...]:
        return tuple(sorted(value, key=lambda source: source.name))


class JournalEventSummary(DashboardModel):
    event_key: str
    event_type: str
    occurred_at: datetime
    correlation_id: str
    actor: str
    source_key: str
    payload_summary: dict[str, object]

    @field_validator("occurred_at")
    @classmethod
    def _occurred_at_must_be_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @model_validator(mode="after")
    def _reject_secret_payload_keys(self) -> Self:
        _reject_secret_like_keys(self.payload_summary)
        return self


class AnalyticsSummary(DashboardModel):
    as_of: datetime
    data_state: DataState
    candidate_counts: dict[str, int]
    strategy_mix: dict[str, int]
    block_reasons: dict[str, int]
    stale_counts: dict[str, int]
    risk_status_distribution: dict[str, int]
    sources: tuple[SourceSummary, ...]
    warnings: tuple[WarningSummary, ...]

    @field_validator("as_of")
    @classmethod
    def _as_of_must_be_utc(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    @field_validator("sources")
    @classmethod
    def _sort_sources(cls, value: tuple[SourceSummary, ...]) -> tuple[SourceSummary, ...]:
        return tuple(sorted(value, key=lambda source: source.name))


def _reject_secret_like_keys(payload: Mapping[str, object]) -> None:
    for key, value in payload.items():
        normalized = key.lower()
        if any(secret_part in normalized for secret_part in SECRET_KEY_PARTS):
            raise ValueError("display payload contains secret-like key")
        if isinstance(value, Mapping):
            _reject_secret_like_keys(value)
        elif isinstance(value, list | tuple):
            for item in value:
                if isinstance(item, Mapping):
                    _reject_secret_like_keys(item)
