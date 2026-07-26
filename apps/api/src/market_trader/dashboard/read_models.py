from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from market_trader.api.health import database_state
from market_trader.config import get_settings
from market_trader.dashboard.models import (
    AnalyticsSummary,
    CandidateDetail,
    CandidateListItem,
    CandidateListResponse,
    DashboardOverview,
    DataState,
    JournalEventListResponse,
    JournalEventSummary,
    RiskSummary,
    SourceSummary,
    WarningSummary,
)
from market_trader.db.engine import create_engine_from_url
from market_trader.db.models import (
    CandidateORM,
    JournalEventORM,
    RiskCheckORM,
    RiskDecisionORM,
    RiskLockORM,
    SymbolORM,
)
from market_trader.domain.time import SystemClock
from market_trader.market_calendar.models import CalendarUnavailableError
from market_trader.market_calendar.service import MarketStateService


class DashboardReadModel:
    def __init__(self, market_state_service: MarketStateService | None = None) -> None:
        self._clock = SystemClock()
        self._market_state_service = market_state_service

    def overview(self) -> DashboardOverview:
        settings = get_settings()
        as_of = self._clock.now()
        market_state = "unavailable"
        entry_allowed = False
        sources: list[SourceSummary] = [
            SourceSummary(
                name="database",
                state=_database_data_state(settings.database_url),
                version="storage-v1",
                observed_at=as_of,
                stable_key="database:health",
            ),
            SourceSummary(
                name="scanner",
                state=DataState.UNAVAILABLE,
                version="scanner-policy-v1",
                observed_at=as_of,
                stable_key="scanner:latest",
            ),
            SourceSummary(
                name="catalysts",
                state=DataState.UNAVAILABLE,
                version="catalyst-policy-v1",
                observed_at=as_of,
                stable_key="catalysts:latest",
            ),
            SourceSummary(
                name="options",
                state=DataState.UNAVAILABLE,
                version="options-analysis-policy-v1",
                observed_at=as_of,
                stable_key="options:latest",
            ),
            SourceSummary(
                name="risk",
                state=DataState.UNAVAILABLE,
                version="risk-policy-v1",
                observed_at=as_of,
                stable_key="risk:latest",
            ),
        ]
        warnings: list[WarningSummary] = []

        try:
            snapshot = self._market_state().current()
        except CalendarUnavailableError:
            sources.append(
                SourceSummary(
                    name="market_state",
                    state=DataState.UNAVAILABLE,
                    version="entry-window-v1",
                    observed_at=as_of,
                    stable_key="market-state:current",
                )
            )
            warnings.append(
                WarningSummary(
                    code="market_state.unavailable",
                    severity="warning",
                    message="Market schedule is unavailable",
                    source_keys=("market-state:current",),
                )
            )
            data_state = DataState.UNAVAILABLE
        else:
            as_of = snapshot.observed_at
            market_state = snapshot.market_state.value
            entry_allowed = snapshot.entry_allowed
            sources.append(
                SourceSummary(
                    name="market_state",
                    state=DataState.READY,
                    version=snapshot.policy_version,
                    observed_at=snapshot.observed_at,
                    stable_key=f"market-state:{snapshot.calendar}",
                )
            )
            data_state = DataState.PARTIAL

        return DashboardOverview(
            as_of=as_of,
            data_state=data_state,
            paper_mode=True,
            market_state=market_state,
            entry_allowed=entry_allowed,
            sources=tuple(sources),
            warnings=tuple(warnings),
        )

    def candidates(self, *, limit: int, cursor: str | None) -> CandidateListResponse:
        as_of = self._clock.now()
        engine = create_engine_from_url(get_settings().database_url)
        try:
            with Session(engine) as session:
                statement = (
                    select(CandidateORM, SymbolORM)
                    .join(SymbolORM, SymbolORM.id == CandidateORM.symbol_id)
                    .where(CandidateORM.candidate_key.is_not(None))
                    .order_by(desc(CandidateORM.created_at), CandidateORM.candidate_key)
                    .limit(limit + 1)
                )
                if cursor is not None:
                    statement = statement.where(CandidateORM.candidate_key > cursor)
                rows = session.execute(statement).all()
        finally:
            engine.dispose()

        if rows:
            page = rows[:limit]
            observed_at = max(_db_utc(candidate.created_at) for candidate, _symbol in page)
            return CandidateListResponse(
                as_of=observed_at,
                data_state=DataState.READY,
                candidates=tuple(
                    _candidate_list_item(candidate, symbol)
                    for candidate, symbol in page
                ),
                next_cursor=rows[limit][0].candidate_key if len(rows) > limit else None,
                sources=(
                    SourceSummary(
                        name="scanner",
                        state=DataState.READY,
                        version="scanner-policy-v1",
                        observed_at=observed_at,
                        stable_key="scanner:latest",
                    ),
                ),
                warnings=(),
            )

        return CandidateListResponse(
            as_of=as_of,
            data_state=DataState.UNAVAILABLE,
            candidates=(),
            next_cursor=None,
            sources=(
                SourceSummary(
                    name="scanner",
                    state=DataState.UNAVAILABLE,
                    version="scanner-policy-v1",
                    observed_at=as_of,
                    stable_key="scanner:latest",
                ),
            ),
            warnings=(
                WarningSummary(
                    code="candidates.unavailable",
                    severity="warning",
                    message="Candidate records are unavailable",
                    source_keys=("scanner:latest",),
                ),
            ),
        )

    def candidate_detail(self, candidate_key: str) -> CandidateDetail | None:
        engine = create_engine_from_url(get_settings().database_url)
        try:
            with Session(engine) as session:
                row = session.execute(
                    select(CandidateORM, SymbolORM)
                    .join(SymbolORM, SymbolORM.id == CandidateORM.symbol_id)
                    .where(CandidateORM.candidate_key == candidate_key)
                ).one_or_none()
        finally:
            engine.dispose()

        if row is None:
            return None

        candidate, symbol = row
        return CandidateDetail(
            candidate_key=candidate.candidate_key or candidate.id,
            symbol=symbol.display_symbol,
            data_state=DataState.PARTIAL,
            as_of=_db_utc(candidate.created_at),
            scanner={
                "strategy": candidate.strategy_id or "unknown",
                "direction": candidate.direction or "unknown",
                "status": candidate.status,
                "score": _decimal_text(candidate.score),
                "reason_codes": _reason_codes(candidate.explanation_payload),
            },
            catalysts={},
            options={},
            risk={},
            sources=(
                SourceSummary(
                    name="scanner",
                    state=DataState.READY,
                    version=candidate.scoring_policy_version or "scanner-policy-v1",
                    observed_at=_db_utc(candidate.created_at),
                    stable_key=candidate.candidate_key or candidate.id,
                ),
            ),
            warnings=(),
        )

    def risk(self) -> RiskSummary:
        as_of = self._clock.now()
        engine = create_engine_from_url(get_settings().database_url)
        try:
            with Session(engine) as session:
                decision = session.scalar(
                    select(RiskDecisionORM).order_by(desc(RiskDecisionORM.as_of)).limit(1)
                )
                active_locks = tuple(
                    session.scalars(
                        select(RiskLockORM.lock_type)
                        .where(RiskLockORM.status == "active")
                        .order_by(RiskLockORM.lock_type)
                    )
                )
                checks = (
                    list(
                        session.scalars(
                            select(RiskCheckORM)
                            .where(RiskCheckORM.decision_id == decision.id)
                            .order_by(RiskCheckORM.check_key)
                        )
                    )
                    if decision is not None
                    else []
                )
        finally:
            engine.dispose()

        if decision is not None:
            observed_at = _db_utc(decision.as_of)
            return RiskSummary(
                as_of=observed_at,
                data_state=DataState.READY,
                latest_decision_key=decision.decision_key,
                status=decision.status,
                checks=tuple(_risk_check_summary(check, decision) for check in checks),
                active_locks=active_locks,
                tax_disclaimer="Informational estimate only; not tax advice.",
                sources=(
                    SourceSummary(
                        name="risk",
                        state=DataState.READY,
                        version=decision.policy_version,
                        observed_at=observed_at,
                        stable_key=decision.decision_key,
                    ),
                ),
                warnings=(),
            )

        return RiskSummary(
            as_of=as_of,
            data_state=DataState.UNAVAILABLE,
            latest_decision_key=None,
            status="unavailable",
            checks=(),
            active_locks=(),
            tax_disclaimer="Informational estimate only; not tax advice.",
            sources=(
                SourceSummary(
                    name="risk",
                    state=DataState.UNAVAILABLE,
                    version="risk-policy-v1",
                    observed_at=as_of,
                    stable_key="risk:latest",
                ),
            ),
            warnings=(
                WarningSummary(
                    code="risk.unavailable",
                    severity="warning",
                    message="Risk decisions are unavailable",
                    source_keys=("risk:latest",),
                ),
            ),
        )

    def journal(
        self,
        *,
        limit: int,
        cursor: str | None,
        event_type: str | None,
        correlation_id: str | None,
    ) -> JournalEventListResponse:
        as_of = self._clock.now()
        engine = create_engine_from_url(get_settings().database_url)
        try:
            with Session(engine) as session:
                statement = select(JournalEventORM).order_by(
                    desc(JournalEventORM.occurred_at),
                    JournalEventORM.id,
                )
                if cursor is not None:
                    statement = statement.where(JournalEventORM.id > cursor)
                if event_type is not None:
                    statement = statement.where(JournalEventORM.event_type == event_type)
                if correlation_id is not None:
                    statement = statement.where(
                        JournalEventORM.correlation_id == correlation_id
                    )
                rows = list(session.scalars(statement.limit(limit + 1)))
        finally:
            engine.dispose()

        if rows:
            page = rows[:limit]
            observed_at = max(_db_utc(event.occurred_at) for event in page)
            return JournalEventListResponse(
                as_of=observed_at,
                data_state=DataState.READY,
                events=tuple(_journal_event(event) for event in page),
                next_cursor=rows[limit].id if len(rows) > limit else None,
                sources=(
                    SourceSummary(
                        name="journal",
                        state=DataState.READY,
                        version="audit-v1",
                        observed_at=observed_at,
                        stable_key="journal:latest",
                    ),
                ),
                warnings=(),
            )

        return JournalEventListResponse(
            as_of=as_of,
            data_state=DataState.UNAVAILABLE,
            events=(),
            next_cursor=None,
            sources=(
                SourceSummary(
                    name="journal",
                    state=DataState.UNAVAILABLE,
                    version="audit-v1",
                    observed_at=as_of,
                    stable_key="journal:latest",
                ),
            ),
            warnings=(
                WarningSummary(
                    code="journal.unavailable",
                    severity="warning",
                    message="Journal events are unavailable",
                    source_keys=("journal:latest",),
                ),
            ),
        )

    def analytics(self) -> AnalyticsSummary:
        as_of = self._clock.now()
        engine = create_engine_from_url(get_settings().database_url)
        try:
            with Session(engine) as session:
                candidate_rows = list(
                    session.execute(
                        select(
                            CandidateORM.status,
                            CandidateORM.strategy_id,
                            CandidateORM.created_at,
                        )
                    )
                )
                risk_rows = list(
                    session.execute(select(RiskDecisionORM.status, RiskDecisionORM.as_of))
                )
        finally:
            engine.dispose()

        if candidate_rows or risk_rows:
            observed = [
                _db_utc(value)
                for *_unused, value in (*candidate_rows, *risk_rows)
                if value is not None
            ]
            observed_at = max(observed, default=as_of)
            return AnalyticsSummary(
                as_of=observed_at,
                data_state=DataState.READY,
                candidate_counts=dict(
                    Counter(str(status) for status, _strategy, _created in candidate_rows)
                ),
                strategy_mix=dict(
                    Counter(
                        str(strategy)
                        for _status, strategy, _created in candidate_rows
                        if strategy is not None
                    )
                ),
                block_reasons={},
                stale_counts={},
                risk_status_distribution=dict(
                    Counter(str(status) for status, _as_of in risk_rows)
                ),
                sources=(
                    SourceSummary(
                        name="analytics",
                        state=DataState.READY,
                        version="dashboard-analytics-v1",
                        observed_at=observed_at,
                        stable_key="analytics:local",
                    ),
                ),
                warnings=(),
            )

        return AnalyticsSummary(
            as_of=as_of,
            data_state=DataState.UNAVAILABLE,
            candidate_counts={},
            strategy_mix={},
            block_reasons={},
            stale_counts={},
            risk_status_distribution={},
            sources=(
                SourceSummary(
                    name="analytics",
                    state=DataState.UNAVAILABLE,
                    version="dashboard-analytics-v1",
                    observed_at=as_of,
                    stable_key="analytics:local",
                ),
            ),
            warnings=(
                WarningSummary(
                    code="analytics.unavailable",
                    severity="warning",
                    message="Dashboard analytics are unavailable",
                    source_keys=("analytics:local",),
                ),
            ),
        )

    def _market_state(self) -> MarketStateService:
        if self._market_state_service is not None:
            return self._market_state_service

        from market_trader.api.market_state import get_market_state_service

        return get_market_state_service()


def _database_data_state(database_url: str) -> DataState:
    if database_state(database_url) == "ok":
        return DataState.READY
    return DataState.UNAVAILABLE


def _candidate_list_item(candidate: CandidateORM, symbol: SymbolORM) -> CandidateListItem:
    return CandidateListItem(
        candidate_key=candidate.candidate_key or candidate.id,
        symbol=symbol.display_symbol,
        direction=candidate.direction or "unknown",
        strategy=candidate.strategy_id or "unknown",
        score=_decimal_text(candidate.score),
        qualification_state=candidate.status,
        catalyst_state="unknown",
        risk_state="unknown",
        data_state=DataState.READY,
        observed_at=_db_utc(candidate.created_at),
        reason_codes=_reason_codes(candidate.explanation_payload),
        source_keys=(candidate.candidate_key or candidate.id,),
    )


def _journal_event(event: JournalEventORM) -> JournalEventSummary:
    return JournalEventSummary(
        event_key=event.id,
        event_type=event.event_type,
        occurred_at=_db_utc(event.occurred_at),
        correlation_id=event.correlation_id,
        actor=event.actor_type,
        source_key=f"{event.subject_type}:{event.subject_id}",
        payload_summary=_payload_summary(event.payload),
    )


def _risk_check_summary(check: RiskCheckORM, decision: RiskDecisionORM) -> WarningSummary:
    return WarningSummary(
        code=check.code,
        severity=check.severity,
        message=f"{check.code}: {check.state}",
        source_keys=tuple(check.source_keys or [decision.decision_key]),
    )


def _payload_summary(payload: dict[str, Any]) -> dict[str, object]:
    return {
        key: value
        for key, value in payload.items()
        if isinstance(value, str | int | bool | float)
    }


def _reason_codes(payload: dict[str, Any]) -> tuple[str, ...]:
    value = payload.get("reason_codes")
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return ()


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return "0.000000"
    return f"{value:.6f}"


def _db_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
