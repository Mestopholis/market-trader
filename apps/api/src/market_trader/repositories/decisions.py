from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy.orm import Session

from market_trader.db.models import CandidateORM, SignalORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository
from market_trader.scanner.models import CandidateResult, StrategyResult
from market_trader.scanner.serialization import canonical_record


@dataclass(frozen=True)
class SignalCreate:
    strategy_version: str
    symbol_id: str
    instrument_id: str | None
    direction: str | None
    score: Decimal | None
    status: str | None
    input_snapshot_id: str
    explanation_payload: dict[str, Any]
    explanation_schema_version: int
    correlation_id: str
    created_at: datetime


@dataclass(frozen=True)
class Signal:
    id: str
    strategy_version: str
    symbol_id: str
    instrument_id: str | None
    direction: str | None
    score: Decimal | None
    status: str | None
    input_snapshot_id: str
    explanation_payload: dict[str, Any]
    explanation_schema_version: int
    correlation_id: str
    created_at: datetime


@dataclass(frozen=True)
class CandidateCreate:
    signal_id: str
    symbol_id: str
    instrument_id: str | None
    status: str
    score: Decimal | None
    explanation_payload: dict[str, Any]
    explanation_schema_version: int
    correlation_id: str
    created_at: datetime


@dataclass(frozen=True)
class Candidate:
    id: str
    signal_id: str
    symbol_id: str
    instrument_id: str | None
    status: str
    score: Decimal | None
    explanation_payload: dict[str, Any]
    explanation_schema_version: int
    correlation_id: str
    created_at: datetime


@dataclass(frozen=True)
class ScannerSignalCreate:
    scanner_run_id: str
    symbol_id: str
    input_snapshot_id: str
    result: StrategyResult
    scoring_policy_version: str
    correlation_id: str
    created_at: datetime


@dataclass(frozen=True)
class ScannerCandidateCreate:
    scanner_run_id: str
    signal_id: str
    symbol_id: str
    result: CandidateResult
    scoring_policy_version: str
    correlation_id: str
    created_at: datetime


class DecisionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def create_signal(self, command: SignalCreate) -> Signal:
        record = SignalORM(
            id=new_domain_id("sig"),
            strategy_version=command.strategy_version,
            symbol_id=command.symbol_id,
            instrument_id=command.instrument_id,
            direction=command.direction,
            score=command.score,
            status=command.status,
            input_snapshot_id=command.input_snapshot_id,
            explanation_payload=dict(command.explanation_payload),
            explanation_schema_version=command.explanation_schema_version,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.created_at),
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="signal.created",
                actor_type="system",
                occurred_at=command.created_at,
                subject_type="signal",
                subject_id=record.id,
                payload={
                    "schema_version": 1,
                    "strategy_version": command.strategy_version,
                    "input_snapshot_id": command.input_snapshot_id,
                },
                schema_version=1,
            )
        )
        return _signal_to_domain(record)

    def create_candidate(self, command: CandidateCreate) -> Candidate:
        record = CandidateORM(
            id=new_domain_id("can"),
            signal_id=command.signal_id,
            symbol_id=command.symbol_id,
            instrument_id=command.instrument_id,
            status=command.status,
            score=command.score,
            explanation_payload=dict(command.explanation_payload),
            explanation_schema_version=command.explanation_schema_version,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.created_at),
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="candidate.created",
                actor_type="system",
                occurred_at=command.created_at,
                subject_type="candidate",
                subject_id=record.id,
                payload={"schema_version": 1, "signal_id": command.signal_id},
                schema_version=1,
            )
        )
        return _candidate_to_domain(record)

    def record_scanner_signal(self, command: ScannerSignalCreate) -> Signal:
        result = command.result
        record = SignalORM(
            id=new_domain_id("sig"),
            signal_key=result.signal_key,
            scanner_run_id=command.scanner_run_id,
            strategy_id=result.strategy_id,
            strategy_version=result.policy_version,
            symbol_id=command.symbol_id,
            instrument_id=None,
            direction=result.direction.value,
            score=result.score,
            status=result.status.value,
            input_snapshot_id=command.input_snapshot_id,
            input_digest=result.input_digest,
            reason_codes=list(result.reasons),
            gate_payload=_scanner_list(result.gates),
            component_score_payload=_scanner_list(result.components),
            scoring_policy_version=command.scoring_policy_version,
            explanation_payload=_scanner_dict(
                {
                    "schema_version": 1,
                    "lineage": result.lineage,
                    "input_references": result.input_references,
                    "primary_ingestion_key": result.primary_ingestion_key,
                }
            ),
            explanation_schema_version=1,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.created_at),
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="scanner_signal.recorded",
                actor_type="system",
                occurred_at=command.created_at,
                subject_type="signal",
                subject_id=record.id,
                payload={
                    "schema_version": 1,
                    "signal_key": result.signal_key,
                    "strategy_id": result.strategy_id,
                    "strategy_version": result.policy_version,
                    "status": result.status.value,
                    "score": str(result.score) if result.score is not None else None,
                    "reason_codes": list(result.reasons),
                    "input_digest": result.input_digest,
                },
                schema_version=1,
            )
        )
        return _signal_to_domain(record)

    def qualify_scanner_candidate(self, command: ScannerCandidateCreate) -> Candidate:
        result = command.result
        record = CandidateORM(
            id=new_domain_id("can"),
            candidate_key=result.candidate_key,
            scanner_run_id=command.scanner_run_id,
            strategy_id=result.strategy_id,
            signal_id=command.signal_id,
            symbol_id=command.symbol_id,
            instrument_id=None,
            direction=result.direction.value,
            status=result.status,
            score=result.score,
            input_digest=result.input_digest,
            scoring_policy_version=command.scoring_policy_version,
            explanation_payload={
                "schema_version": 1,
                "reason_codes": list(result.reasons),
                "signal_key": result.signal_key,
            },
            explanation_schema_version=1,
            correlation_id=command.correlation_id,
            created_at=ensure_utc(command.created_at),
        )
        self._session.add(record)
        self._session.flush()
        self._audit.append(
            AuditEventCreate(
                correlation_id=command.correlation_id,
                event_type="scanner_candidate.qualified",
                actor_type="system",
                occurred_at=command.created_at,
                subject_type="candidate",
                subject_id=record.id,
                payload={
                    "schema_version": 1,
                    "candidate_key": result.candidate_key,
                    "signal_key": result.signal_key,
                    "strategy_id": result.strategy_id,
                    "scoring_policy_version": command.scoring_policy_version,
                    "status": result.status,
                    "score": str(result.score),
                    "reason_codes": list(result.reasons),
                    "input_digest": result.input_digest,
                },
                schema_version=1,
            )
        )
        return _candidate_to_domain(record)

    def get_candidate(self, candidate_id: str) -> Candidate | None:
        record = self._session.get(CandidateORM, candidate_id)
        return _candidate_to_domain(record) if record is not None else None


def _signal_to_domain(record: SignalORM) -> Signal:
    return Signal(
        id=record.id,
        strategy_version=record.strategy_version,
        symbol_id=record.symbol_id,
        instrument_id=record.instrument_id,
        direction=record.direction,
        score=record.score,
        status=record.status,
        input_snapshot_id=record.input_snapshot_id,
        explanation_payload=dict(record.explanation_payload),
        explanation_schema_version=record.explanation_schema_version,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
    )


def _candidate_to_domain(record: CandidateORM) -> Candidate:
    return Candidate(
        id=record.id,
        signal_id=record.signal_id,
        symbol_id=record.symbol_id,
        instrument_id=record.instrument_id,
        status=record.status,
        score=record.score,
        explanation_payload=dict(record.explanation_payload),
        explanation_schema_version=record.explanation_schema_version,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
    )


def _scanner_dict(value: object) -> dict[str, Any]:
    payload = canonical_record(value)
    if not isinstance(payload, dict):
        raise TypeError("scanner payload must be an object")
    return payload


def _scanner_list(value: object) -> list[dict[str, Any]]:
    payload = canonical_record(value)
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise TypeError("scanner payload must be a list of objects")
    return cast(list[dict[str, Any]], payload)
