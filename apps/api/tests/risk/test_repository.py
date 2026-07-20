from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from market_trader.db.base import Base
from market_trader.db.models import (
    JournalEventORM,
    RiskCheckORM,
    RiskDecisionORM,
    RiskReservationORM,
)
from market_trader.repositories.risk_decisions import (
    RiskDecisionPersistenceConflict,
    RiskDecisionPersistenceError,
    RiskDecisionRepository,
)
from market_trader.risk.models import (
    ProposalKind,
    RiskCheck,
    RiskCheckSeverity,
    RiskCheckState,
    RiskDecision,
    RiskDecisionStatus,
    SizingResult,
)

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


@pytest.fixture
def session() -> Generator[Session]:
    sqlite_engine = create_engine("sqlite://")
    Base.metadata.create_all(sqlite_engine)
    try:
        with Session(sqlite_engine) as value:
            yield value
    finally:
        sqlite_engine.dispose()


def test_persist_records_decision_children_reservation_and_audit_without_committing(
    session: Session,
) -> None:
    persisted = RiskDecisionRepository(session).persist(_decision())

    assert persisted.decision_key == "risk:decision:1"
    assert persisted.correlation_id
    assert _count(session, RiskDecisionORM) == 1
    assert _count(session, RiskCheckORM) == 1
    assert _count(session, RiskReservationORM) == 1
    event_types = session.scalars(
        select(JournalEventORM.event_type).order_by(JournalEventORM.event_type)
    ).all()
    assert event_types == [
        "risk_check.recorded",
        "risk_decision.recorded",
        "risk_reservation.recorded",
    ]
    session.rollback()
    assert _count(session, RiskDecisionORM) == 0


def test_exact_rerun_is_idempotent_without_duplicate_children_or_audit(
    session: Session,
) -> None:
    repository = RiskDecisionRepository(session)
    first = repository.persist(_decision())
    second = repository.persist(_decision())

    assert first.id == second.id
    assert _count(session, RiskDecisionORM) == 1
    assert _count(session, RiskCheckORM) == 1
    assert _count(session, RiskReservationORM) == 1
    assert _count(session, JournalEventORM) == 3


def test_changed_digest_for_existing_decision_key_is_a_conflict(session: Session) -> None:
    repository = RiskDecisionRepository(session)
    repository.persist(_decision())

    with pytest.raises(RiskDecisionPersistenceConflict):
        repository.persist(_decision(result_digest="d" * 64))


def test_child_failure_rolls_back_entire_persist_attempt(session: Session) -> None:
    duplicate_checks = (
        _check("buying_power.settled_cash"),
        _check("buying_power.settled_cash"),
    )

    with pytest.raises(RiskDecisionPersistenceError, match="duplicate check"):
        RiskDecisionRepository(session).persist(_decision(checks=duplicate_checks))

    assert _count(session, RiskDecisionORM) == 0
    assert _count(session, RiskCheckORM) == 0
    assert _count(session, RiskReservationORM) == 0
    assert _count(session, JournalEventORM) == 0


def _decision(
    *,
    result_digest: str = "b" * 64,
    checks: tuple[RiskCheck, ...] | None = None,
) -> RiskDecision:
    return RiskDecision(
        decision_key="risk:decision:1",
        status=RiskDecisionStatus.APPROVED,
        proposal_kind=ProposalKind.SHARES,
        sizing=SizingResult(
            quantity=5,
            notional=Decimal("500.00"),
            maximum_loss=Decimal("25.00"),
            reserved_risk=Decimal("25.00"),
            assignment_stress=Decimal("0.00"),
            reasons=("test",),
        ),
        checks=checks if checks is not None else (_check("buying_power.settled_cash"),),
        policy_version="risk-policy-v1",
        policy_hash="a" * 64,
        input_digest="c" * 64,
        result_digest=result_digest,
        as_of=AS_OF,
        reason_summary=("approved",),
    )


def _check(code: str) -> RiskCheck:
    return RiskCheck(
        code=code,
        severity=RiskCheckSeverity.INFO,
        state=RiskCheckState.PASSED,
        message="passed",
        facts={"available": Decimal("1000.00")},
        source_keys=("bp-digest",),
    )


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0
