from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import (
    CandidateORM,
    OptionsAnalysisRunORM,
    RiskDecisionORM,
    RiskLockORM,
    SignalORM,
    SymbolORM,
)
from market_trader.domain.time import ensure_utc
from market_trader.paper.models import ApprovalCard, ApprovalCardState, PaperAction

ELIGIBLE_RISK_STATUSES = frozenset({"approved", "warning"})
APPROVAL_CARD_TTL = timedelta(minutes=5)
REQUIRED_CLEAR_LOCK_TYPES = frozenset(
    {
        "account_mismatch",
        "authentication",
        "daily_loss",
        "drawdown",
        "manual_operator_hold",
        "stale_data",
        "strategy_review",
        "weekly_loss",
    }
)
SPREAD_PROPOSAL_KINDS = frozenset({"debit_spread", "credit_spread", "vertical_spread"})


def assemble_approval_cards(session: Session, *, as_of: datetime) -> tuple[ApprovalCard, ...]:
    """Build paper approval cards from persisted, risk-approved candidate lineage."""

    normalized_as_of = ensure_utc(as_of)
    if _has_active_required_lock(session):
        return ()

    decisions = session.scalars(
        select(RiskDecisionORM)
        .where(RiskDecisionORM.status.in_(ELIGIBLE_RISK_STATUSES))
        .order_by(RiskDecisionORM.decision_key)
    ).all()

    cards: list[ApprovalCard] = []
    for decision in decisions:
        card = _card_for_decision(session, decision, as_of=normalized_as_of)
        if card is not None:
            cards.append(card)
    return tuple(cards)


def _has_active_required_lock(session: Session) -> bool:
    lock_id = session.scalar(
        select(RiskLockORM.id)
        .where(RiskLockORM.status == "active")
        .where(RiskLockORM.lock_type.in_(REQUIRED_CLEAR_LOCK_TYPES))
        .limit(1)
    )
    return lock_id is not None


def _card_for_decision(
    session: Session, decision: RiskDecisionORM, *, as_of: datetime
) -> ApprovalCard | None:
    payload = _mapping(decision.decision_payload)
    sizing = _mapping(decision.sizing_payload)
    candidate_key = _text(payload.get("candidate_key"))
    if candidate_key is None:
        return None

    candidate = session.scalar(
        select(CandidateORM).where(CandidateORM.candidate_key == candidate_key).limit(1)
    )
    if candidate is None or candidate.candidate_key is None:
        return None
    if not _candidate_digest_matches(candidate, payload):
        return None

    quantity = _positive_int(sizing.get("quantity"))
    limit_price = _positive_decimal(payload.get("limit_price") or sizing.get("limit_price"))
    maximum_loss = _non_negative_decimal(
        sizing.get("maximum_loss") or sizing.get("max_loss") or payload.get("maximum_loss")
    )
    if quantity is None or limit_price is None or maximum_loss is None:
        return None

    symbol = session.scalar(select(SymbolORM).where(SymbolORM.id == candidate.symbol_id).limit(1))
    signal = session.scalar(select(SignalORM).where(SignalORM.id == candidate.signal_id).limit(1))
    if symbol is None or signal is None:
        return None

    source_keys = [
        f"candidate:{candidate.candidate_key}",
        f"risk_decision:{decision.decision_key}",
        f"signal:{signal.signal_key or signal.id}",
    ]
    if decision.proposal_kind in SPREAD_PROPOSAL_KINDS:
        options_run = _latest_options_run(session, candidate)
        if options_run is None:
            return None
        source_keys.append(f"options_analysis:{options_run.run_key}")

    return ApprovalCard(
        card_key=f"approval-card:{candidate.candidate_key}:{decision.decision_key}",
        state=ApprovalCardState.READY,
        candidate_key=candidate.candidate_key,
        symbol=symbol.display_symbol,
        direction=candidate.direction or signal.direction or "unknown",
        proposal_kind=decision.proposal_kind,
        quantity=quantity,
        limit_price=limit_price,
        maximum_loss=maximum_loss,
        risk_decision_key=decision.decision_key,
        risk_status=decision.status,
        risk_input_digest=decision.input_digest,
        risk_result_digest=decision.result_digest,
        source_keys=tuple(source_keys),
        allowed_actions=(PaperAction.APPROVE, PaperAction.MODIFY, PaperAction.REJECT),
        expires_at=as_of + APPROVAL_CARD_TTL,
        as_of=as_of,
        warnings=tuple(decision.reason_summary),
    )


def _latest_options_run(session: Session, candidate: CandidateORM) -> OptionsAnalysisRunORM | None:
    return session.scalar(
        select(OptionsAnalysisRunORM)
        .where(OptionsAnalysisRunORM.candidate_id == candidate.id)
        .order_by(OptionsAnalysisRunORM.as_of.desc())
        .limit(1)
    )


def _candidate_digest_matches(candidate: CandidateORM, payload: dict[str, Any]) -> bool:
    expected = _text(payload.get("candidate_input_digest"))
    if expected is None:
        return False
    return candidate.input_digest == expected


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _positive_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str | Decimal):
        try:
            parsed = int(value)
        except (InvalidOperation, ValueError):
            return None
    else:
        return None
    if parsed <= 0:
        return None
    return parsed


def _positive_decimal(value: object) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is None or parsed <= 0:
        return None
    return parsed


def _non_negative_decimal(value: object) -> Decimal | None:
    parsed = _decimal(value)
    if parsed is None or parsed < 0:
        return None
    return parsed


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
