from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import EligibilityDecisionORM, ScannerRunORM
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc, utc_now
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository
from market_trader.repositories.decisions import (
    DecisionRepository,
    ScannerCandidateCreate,
    ScannerSignalCreate,
)
from market_trader.repositories.market_data import MarketDataRepository
from market_trader.repositories.symbols import SymbolRepository
from market_trader.scanner.models import ScanResult
from market_trader.scanner.serialization import canonical_record, stable_digest


class ScannerPersistenceError(RuntimeError):
    pass


class ScannerPersistenceConflict(ScannerPersistenceError):
    pass


@dataclass(frozen=True)
class PersistedScanRun:
    id: str
    run_key: str
    input_digest: str
    result_digest: str
    correlation_id: str
    created_at: datetime


class ScannerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._symbols = SymbolRepository(session)
        self._market_data = MarketDataRepository(session)
        self._decisions = DecisionRepository(session)
        self._audit = AuditRepository(session)

    def persist(self, result: ScanResult) -> PersistedScanRun:
        existing = self._session.scalar(
            select(ScannerRunORM).where(ScannerRunORM.run_key == result.run_key)
        )
        if existing is not None:
            if (
                existing.input_digest != result.input_digest
                or existing.result_digest != result.result_digest
            ):
                raise ScannerPersistenceConflict(f"scanner run key conflict: {result.run_key}")
            return _to_persisted(existing)

        universe_hash = result.configuration_hashes.get("universe")
        if not universe_hash:
            raise ScannerPersistenceError("missing universe configuration hash")

        symbol_ids = self._resolve_symbol_ids(result)
        snapshot_ids = self._resolve_snapshot_ids(result, symbol_ids)
        correlation_id = stable_digest(result.run_key)
        created_at = utc_now()
        run = ScannerRunORM(
            id=new_domain_id("scn"),
            run_key=result.run_key,
            as_of=ensure_utc(result.as_of),
            session_date=result.session_date,
            input_digest=result.input_digest,
            universe_version=result.versions.universe,
            universe_content_hash=universe_hash,
            policy_versions=_scanner_dict(result.versions),
            regime_state=result.regime.state.value,
            regime_score=result.regime.signed_score,
            regime_explanation=_scanner_dict(result.regime),
            result_counts=_scanner_dict(result.counts),
            result_digest=result.result_digest,
            status="completed",
            correlation_id=correlation_id,
            created_at=created_at,
        )
        self._session.add(run)
        self._session.flush()

        for decision in result.eligibility:
            record = EligibilityDecisionORM(
                id=new_domain_id("eld"),
                decision_key=f"{result.run_key}:{decision.symbol}",
                scanner_run_id=run.id,
                symbol_id=symbol_ids[decision.symbol],
                status=decision.status.value,
                reason_codes=list(decision.reasons),
                observed_payload=_scanner_dict(decision.observed),
                input_digest=result.input_digest,
                policy_version=decision.policy_version,
                correlation_id=correlation_id,
                created_at=created_at,
            )
            self._session.add(record)
            self._session.flush()
            self._audit.append(
                AuditEventCreate(
                    correlation_id=correlation_id,
                    event_type="eligibility_decision.recorded",
                    actor_type="system",
                    occurred_at=result.as_of,
                    subject_type="eligibility_decision",
                    subject_id=record.id,
                    payload={
                        "schema_version": 1,
                        "decision_key": record.decision_key,
                        "run_key": result.run_key,
                        "symbol": decision.symbol,
                        "policy_version": decision.policy_version,
                        "status": decision.status.value,
                        "reason_codes": list(decision.reasons),
                        "input_digest": result.input_digest,
                    },
                    schema_version=1,
                )
            )

        signal_ids: dict[str, str] = {}
        for strategy in result.strategies:
            stored = self._decisions.record_scanner_signal(
                ScannerSignalCreate(
                    scanner_run_id=run.id,
                    symbol_id=symbol_ids[strategy.symbol],
                    input_snapshot_id=snapshot_ids[strategy.signal_key],
                    result=strategy,
                    scoring_policy_version=result.versions.scoring,
                    correlation_id=correlation_id,
                    created_at=created_at,
                )
            )
            signal_ids[strategy.signal_key] = stored.id

        for candidate in result.candidates:
            signal_id = signal_ids.get(candidate.signal_key)
            if signal_id is None:
                raise ScannerPersistenceError(
                    f"missing signal for candidate: {candidate.signal_key}"
                )
            self._decisions.qualify_scanner_candidate(
                ScannerCandidateCreate(
                    scanner_run_id=run.id,
                    signal_id=signal_id,
                    symbol_id=symbol_ids[candidate.symbol],
                    result=candidate,
                    scoring_policy_version=result.versions.scoring,
                    correlation_id=correlation_id,
                    created_at=created_at,
                )
            )

        self._audit.append(
            AuditEventCreate(
                correlation_id=correlation_id,
                event_type="scanner_run.completed",
                actor_type="system",
                occurred_at=result.as_of,
                subject_type="scanner_run",
                subject_id=run.id,
                payload={
                    "schema_version": 1,
                    "run_key": result.run_key,
                    "versions": _scanner_dict(result.versions),
                    "status": "completed",
                    "input_digest": result.input_digest,
                    "result_digest": result.result_digest,
                },
                schema_version=1,
            )
        )
        return _to_persisted(run)

    def _resolve_symbol_ids(self, result: ScanResult) -> dict[str, str]:
        symbol_ids: dict[str, str] = {}
        for decision in result.eligibility:
            symbol = self._symbols.get_symbol_by_display_symbol(decision.symbol)
            if symbol is None:
                raise ScannerPersistenceError(f"missing symbol: {decision.symbol}")
            symbol_ids[decision.symbol] = symbol.id
        return symbol_ids

    def _resolve_snapshot_ids(
        self, result: ScanResult, symbol_ids: dict[str, str]
    ) -> dict[str, str]:
        snapshot_ids: dict[str, str] = {}
        for strategy in result.strategies:
            ingestion_key = strategy.primary_ingestion_key
            if not ingestion_key:
                raise ScannerPersistenceError(
                    f"missing snapshot reference for signal: {strategy.signal_key}"
                )
            snapshot = self._market_data.get_snapshot_by_ingestion_key(ingestion_key)
            if snapshot is None:
                raise ScannerPersistenceError(f"missing snapshot: {ingestion_key}")
            if snapshot.symbol_id != symbol_ids[strategy.symbol]:
                raise ScannerPersistenceError(f"snapshot symbol mismatch: {ingestion_key}")
            snapshot_ids[strategy.signal_key] = snapshot.id
        return snapshot_ids


def _to_persisted(record: ScannerRunORM) -> PersistedScanRun:
    return PersistedScanRun(
        id=record.id,
        run_key=record.run_key,
        input_digest=record.input_digest,
        result_digest=record.result_digest,
        correlation_id=record.correlation_id,
        created_at=stored_utc(record.created_at),
    )


def _scanner_dict(value: object) -> dict[str, Any]:
    payload = canonical_record(value)
    if not isinstance(payload, dict):
        raise ScannerPersistenceError("scanner payload must be an object")
    return payload
