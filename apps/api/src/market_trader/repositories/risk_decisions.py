from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import RiskCheckORM, RiskDecisionORM, RiskReservationORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditEventCreate, AuditRepository
from market_trader.risk.models import RiskCheck, RiskDecision
from market_trader.risk.serialization import canonical_record, stable_digest


class RiskDecisionPersistenceConflict(RuntimeError):
    pass


class RiskDecisionPersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class PersistedRiskDecision:
    id: str
    decision_key: str
    status: str
    result_digest: str
    correlation_id: str
    created_at: datetime


class RiskDecisionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def persist(self, decision: RiskDecision) -> PersistedRiskDecision:
        existing = self._session.scalar(
            select(RiskDecisionORM).where(
                RiskDecisionORM.decision_key == decision.decision_key
            )
        )
        if existing is not None:
            if (
                existing.input_digest != decision.input_digest
                or existing.result_digest != decision.result_digest
                or existing.policy_hash != decision.policy_hash
                or existing.status != decision.status.value
            ):
                raise RiskDecisionPersistenceConflict(
                    f"risk decision key conflict: {decision.decision_key}"
                )
            return _persisted(existing)

        try:
            self._validate_children(decision)
            created_at = utc_now()
            correlation_id = stable_digest(decision.decision_key)
            record = RiskDecisionORM(
                id=new_domain_id("rde"),
                decision_key=decision.decision_key,
                status=decision.status.value,
                proposal_kind=decision.proposal_kind.value,
                policy_version=decision.policy_version,
                policy_hash=decision.policy_hash,
                input_digest=decision.input_digest,
                result_digest=decision.result_digest,
                as_of=decision.as_of,
                reason_summary=list(decision.reason_summary),
                sizing_payload=_json_object(decision.sizing),
                decision_payload=_json_object(decision),
                correlation_id=correlation_id,
                created_at=created_at,
            )
            self._session.add(record)
            self._session.flush()
            self._audit_new(
                record,
                "risk_decision.recorded",
                "risk_decision",
                decision.as_of,
                {
                    "decision_key": decision.decision_key,
                    "result_digest": decision.result_digest,
                    "status": decision.status.value,
                },
            )
            for check in decision.checks:
                self._record_check(record, check, created_at)
            if decision.sizing.reserved_risk > 0:
                self._record_reservation(record, decision, created_at)
        except Exception as error:
            self._session.rollback()
            if isinstance(error, RiskDecisionPersistenceError):
                raise
            raise
        return _persisted(record)

    def _validate_children(self, decision: RiskDecision) -> None:
        check_codes = [check.code for check in decision.checks]
        if len(set(check_codes)) != len(check_codes):
            raise RiskDecisionPersistenceError("duplicate check codes are not appendable")

    def _record_check(
        self,
        decision_record: RiskDecisionORM,
        check: RiskCheck,
        created_at: datetime,
    ) -> None:
        check_key = f"{decision_record.decision_key}:{check.code}"
        record = RiskCheckORM(
            id=new_domain_id("rch"),
            check_key=check_key,
            decision_id=decision_record.id,
            code=check.code,
            severity=check.severity.value,
            state=check.state.value,
            facts=_json_object(check.facts),
            source_keys=list(check.source_keys),
            created_at=created_at,
        )
        self._session.add(record)
        self._session.flush()
        self._audit_new(
            record,
            "risk_check.recorded",
            "risk_check",
            decision_record.as_of,
            {"check_key": check_key, "code": check.code, "state": check.state.value},
        )

    def _record_reservation(
        self,
        decision_record: RiskDecisionORM,
        decision: RiskDecision,
        created_at: datetime,
    ) -> None:
        reservation_key = f"{decision.decision_key}:reserved_risk"
        record = RiskReservationORM(
            id=new_domain_id("rrs"),
            reservation_key=reservation_key,
            decision_id=decision_record.id,
            amount=decision.sizing.reserved_risk,
            reservation_payload={
                "decision_key": decision.decision_key,
                "proposal_kind": decision.proposal_kind.value,
                "quantity": decision.sizing.quantity,
                "reserved_risk": str(decision.sizing.reserved_risk),
            },
            created_at=created_at,
        )
        self._session.add(record)
        self._session.flush()
        self._audit_new(
            record,
            "risk_reservation.recorded",
            "risk_reservation",
            decision.as_of,
            {"reservation_key": reservation_key, "amount": str(decision.sizing.reserved_risk)},
        )

    def _audit_new(
        self,
        record: RiskDecisionORM | RiskCheckORM | RiskReservationORM,
        event_type: str,
        subject_type: str,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> None:
        self._audit.append(
            AuditEventCreate(
                correlation_id=record.id,
                event_type=event_type,
                actor_type="system",
                occurred_at=occurred_at,
                subject_type=subject_type,
                subject_id=record.id,
                payload=payload,
                schema_version=1,
            )
        )


def _json_object(value: object) -> dict[str, Any]:
    record = canonical_record(value)
    if not isinstance(record, dict):
        raise TypeError("canonical value must be an object")
    return cast(dict[str, Any], record)


def _persisted(record: RiskDecisionORM) -> PersistedRiskDecision:
    return PersistedRiskDecision(
        id=record.id,
        decision_key=record.decision_key,
        status=record.status,
        result_digest=record.result_digest,
        correlation_id=record.correlation_id,
        created_at=record.created_at,
    )
