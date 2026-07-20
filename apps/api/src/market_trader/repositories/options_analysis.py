from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.db.models import (
    CandidateORM,
    OptionContractEvaluationORM,
    OptionsAnalysisRunORM,
    OptionSpreadCandidateORM,
    OptionSpreadWarningORM,
    ScannerRunORM,
    SymbolORM,
)
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc, utc_now
from market_trader.options_analysis.engine import OptionsAnalysisResult, RankedSpread
from market_trader.options_analysis.models import ContractEvaluation, SpreadCandidate
from market_trader.options_analysis.serialization import canonical_record, stable_digest
from market_trader.options_analysis.warnings import SpreadWarning
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


class OptionsAnalysisPersistenceError(RuntimeError):
    pass


class OptionsAnalysisPersistenceConflict(OptionsAnalysisPersistenceError):
    pass


@dataclass(frozen=True)
class OptionsAnalysisRunCreate:
    run_key: str
    scanner_run_id: str
    candidate_id: str
    symbol_id: str
    input_digest: str
    result_digest: str
    policy_version: str
    policy_hash: str
    as_of: datetime
    result_counts: dict[str, object]
    reason_summary: dict[str, object]


@dataclass(frozen=True)
class PersistedOptionsAnalysisRun:
    id: str
    run_key: str
    input_digest: str
    result_digest: str
    correlation_id: str
    created_at: datetime


class OptionsAnalysisRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def persist(self, result: OptionsAnalysisResult) -> PersistedOptionsAnalysisRun:
        self._validate_result_identity(result)
        existing = self._session.scalar(
            select(OptionsAnalysisRunORM).where(OptionsAnalysisRunORM.run_key == result.run_key)
        )
        if existing is not None:
            if (
                existing.input_digest != result.input_digest
                or existing.result_digest != result.result_digest
            ):
                raise OptionsAnalysisPersistenceConflict(
                    f"options analysis run key conflict: {result.run_key}"
                )
            return _to_persisted(existing)

        scanner_run = self._resolve_scanner_run(result.scanner_run_key)
        symbol = self._resolve_symbol(result.symbol)
        candidate = self._resolve_candidate(result.candidate_key, scanner_run.id, symbol.id)

        try:
            with self._session.begin_nested():
                return self._persist_new_result(result, scanner_run, candidate, symbol)
        except OptionsAnalysisPersistenceError:
            raise
        except Exception as exc:  # pragma: no cover - preserves atomicity for DB errors.
            raise OptionsAnalysisPersistenceError("options analysis persistence failed") from exc

    def record_run(self, value: OptionsAnalysisRunCreate) -> OptionsAnalysisRunORM:
        existing = self._session.scalar(
            select(OptionsAnalysisRunORM).where(OptionsAnalysisRunORM.run_key == value.run_key)
        )
        if existing is not None:
            is_conflict = (
                existing.input_digest != value.input_digest
                or existing.result_digest != value.result_digest
            )
            if is_conflict:
                raise OptionsAnalysisPersistenceConflict(
                    f"options analysis run key conflict: {value.run_key}"
                )
            return existing
        record = OptionsAnalysisRunORM(
            id=new_domain_id("oar"),
            run_key=value.run_key,
            scanner_run_id=value.scanner_run_id,
            candidate_id=value.candidate_id,
            symbol_id=value.symbol_id,
            input_digest=value.input_digest,
            result_digest=value.result_digest,
            policy_version=value.policy_version,
            policy_hash=value.policy_hash,
            as_of=ensure_utc(value.as_of),
            result_counts=value.result_counts,
            reason_summary=value.reason_summary,
            created_at=utc_now(),
        )
        self._session.add(record)
        self._session.flush()
        return record

    def _persist_new_result(
        self,
        result: OptionsAnalysisResult,
        scanner_run: ScannerRunORM,
        candidate: CandidateORM,
        symbol: SymbolORM,
    ) -> PersistedOptionsAnalysisRun:
        if result.as_of is None:
            raise OptionsAnalysisPersistenceError("options analysis result missing as_of")
        created_at = utc_now()
        correlation_id = stable_digest(result.run_key)
        run = OptionsAnalysisRunORM(
            id=new_domain_id("oar"),
            run_key=result.run_key,
            scanner_run_id=scanner_run.id,
            candidate_id=candidate.id,
            symbol_id=symbol.id,
            input_digest=result.input_digest,
            result_digest=result.result_digest,
            policy_version=result.policy_version,
            policy_hash=result.policy_hash,
            as_of=ensure_utc(result.as_of),
            result_counts=_result_counts(result),
            reason_summary=_reason_summary(result),
            created_at=created_at,
        )
        self._session.add(run)
        self._session.flush()
        self._append_audit(
            correlation_id=correlation_id,
            event_type="options_analysis_run.recorded",
            occurred_at=result.as_of,
            subject_type="options_analysis_run",
            subject_id=run.id,
            payload={
                "schema_version": 1,
                "run_key": result.run_key,
                "scanner_run_key": result.scanner_run_key,
                "candidate_key": result.candidate_key,
                "symbol": result.symbol,
                "input_digest": result.input_digest,
                "result_digest": result.result_digest,
                "policy_version": result.policy_version,
                "policy_hash": result.policy_hash,
            },
        )

        for evaluation in result.evaluations:
            self._record_evaluation(result, run, evaluation, correlation_id)

        for ranked in (*result.selectable, *result.blocked):
            self._record_spread(result, run, ranked, correlation_id)

        return _to_persisted(run, correlation_id=correlation_id)

    def _record_evaluation(
        self,
        result: OptionsAnalysisResult,
        run: OptionsAnalysisRunORM,
        evaluation: ContractEvaluation,
        correlation_id: str,
    ) -> None:
        if result.as_of is None:
            raise OptionsAnalysisPersistenceError("options analysis result missing as_of")
        record = OptionContractEvaluationORM(
            id=new_domain_id("oce"),
            evaluation_key=f"{result.run_key}:evaluation:{evaluation.contract_id}",
            run_id=run.id,
            contract_id=evaluation.contract_id,
            state=str(evaluation.state.value),
            reasons=list(evaluation.reasons),
            created_at=run.created_at,
        )
        self._session.add(record)
        self._session.flush()
        self._append_audit(
            correlation_id=correlation_id,
            event_type="option_contract_evaluation.recorded",
            occurred_at=result.as_of,
            subject_type="option_contract_evaluation",
            subject_id=record.id,
            payload={
                "schema_version": 1,
                "run_key": result.run_key,
                "evaluation_key": record.evaluation_key,
                "contract_id": evaluation.contract_id,
                "state": evaluation.state.value,
                "reasons": list(evaluation.reasons),
            },
        )

    def _record_spread(
        self,
        result: OptionsAnalysisResult,
        run: OptionsAnalysisRunORM,
        ranked: RankedSpread,
        correlation_id: str,
    ) -> None:
        if result.as_of is None:
            raise OptionsAnalysisPersistenceError("options analysis result missing as_of")
        spread = ranked.candidate
        spread_key = _spread_key(result.run_key, spread)
        warning_keys = _warning_keys(spread_key, ranked.warnings)
        record = OptionSpreadCandidateORM(
            id=new_domain_id("osc"),
            spread_key=spread_key,
            run_id=run.id,
            strategy=spread.strategy.value,
            long_contract_id=spread.long_contract_id,
            short_contract_id=spread.short_contract_id,
            expiration=spread.expiration,
            blocked=ranked.blocked,
            calculations=_spread_calculations(spread),
            warning_keys=warning_keys,
            created_at=run.created_at,
        )
        self._session.add(record)
        self._session.flush()
        self._append_audit(
            correlation_id=correlation_id,
            event_type="option_spread_candidate.recorded",
            occurred_at=result.as_of,
            subject_type="option_spread_candidate",
            subject_id=record.id,
            payload={
                "schema_version": 1,
                "run_key": result.run_key,
                "spread_key": spread_key,
                "strategy": spread.strategy.value,
                "blocked": ranked.blocked,
                "warning_keys": warning_keys,
            },
        )
        for warning, warning_key in zip(ranked.warnings, warning_keys, strict=True):
            self._record_warning(result, record, warning, warning_key, correlation_id)

    def _record_warning(
        self,
        result: OptionsAnalysisResult,
        spread_record: OptionSpreadCandidateORM,
        warning: SpreadWarning,
        warning_key: str,
        correlation_id: str,
    ) -> None:
        if result.as_of is None:
            raise OptionsAnalysisPersistenceError("options analysis result missing as_of")
        record = OptionSpreadWarningORM(
            id=new_domain_id("osw"),
            warning_key=warning_key,
            spread_id=spread_record.id,
            code=warning.code,
            severity=warning.severity,
            facts={},
            source_keys=[],
            created_at=spread_record.created_at,
        )
        self._session.add(record)
        self._session.flush()
        self._append_audit(
            correlation_id=correlation_id,
            event_type="option_spread_warning.recorded",
            occurred_at=result.as_of,
            subject_type="option_spread_warning",
            subject_id=record.id,
            payload={
                "schema_version": 1,
                "run_key": result.run_key,
                "spread_key": spread_record.spread_key,
                "warning_key": warning_key,
                "code": warning.code,
                "severity": warning.severity,
            },
        )

    def _append_audit(
        self,
        *,
        correlation_id: str,
        event_type: str,
        occurred_at: datetime,
        subject_type: str,
        subject_id: str,
        payload: dict[str, Any],
    ) -> None:
        self._audit.append(
            AuditEventCreate(
                correlation_id=correlation_id,
                event_type=event_type,
                actor_type="system",
                occurred_at=occurred_at,
                subject_type=subject_type,
                subject_id=subject_id,
                payload=payload,
                schema_version=1,
            )
        )

    def _resolve_scanner_run(self, scanner_run_key: str) -> ScannerRunORM:
        record = self._session.scalar(
            select(ScannerRunORM).where(ScannerRunORM.run_key == scanner_run_key)
        )
        if record is None:
            raise OptionsAnalysisPersistenceError(f"missing scanner run: {scanner_run_key}")
        return record

    def _resolve_symbol(self, display_symbol: str) -> SymbolORM:
        record = self._session.scalar(
            select(SymbolORM).where(SymbolORM.display_symbol == display_symbol)
        )
        if record is None:
            raise OptionsAnalysisPersistenceError(f"missing symbol: {display_symbol}")
        return record

    def _resolve_candidate(
        self,
        candidate_key: str,
        scanner_run_id: str,
        symbol_id: str,
    ) -> CandidateORM:
        record = self._session.scalar(
            select(CandidateORM).where(CandidateORM.candidate_key == candidate_key)
        )
        if record is None:
            raise OptionsAnalysisPersistenceError(f"missing candidate: {candidate_key}")
        if record.scanner_run_id != scanner_run_id:
            raise OptionsAnalysisPersistenceError(f"candidate scanner mismatch: {candidate_key}")
        if record.symbol_id != symbol_id:
            raise OptionsAnalysisPersistenceError(f"candidate symbol mismatch: {candidate_key}")
        if record.status != "qualified":
            raise OptionsAnalysisPersistenceError(f"candidate is not qualified: {candidate_key}")
        return record

    def _validate_result_identity(self, result: OptionsAnalysisResult) -> None:
        required = {
            "run_key": result.run_key,
            "scanner_run_key": result.scanner_run_key,
            "candidate_key": result.candidate_key,
            "symbol": result.symbol,
            "input_digest": result.input_digest,
            "result_digest": result.result_digest,
            "policy_version": result.policy_version,
            "policy_hash": result.policy_hash,
        }
        missing = sorted(key for key, value in required.items() if not value)
        if missing:
            raise OptionsAnalysisPersistenceError(
                f"options analysis result missing identity fields: {', '.join(missing)}"
            )


def _to_persisted(
    record: OptionsAnalysisRunORM,
    *,
    correlation_id: str | None = None,
) -> PersistedOptionsAnalysisRun:
    return PersistedOptionsAnalysisRun(
        id=record.id,
        run_key=record.run_key,
        input_digest=record.input_digest,
        result_digest=record.result_digest,
        correlation_id=correlation_id or stable_digest(record.run_key),
        created_at=stored_utc(record.created_at),
    )


def _result_counts(result: OptionsAnalysisResult) -> dict[str, int]:
    return {
        "evaluations": len(result.evaluations),
        "selectable_spreads": len(result.selectable),
        "blocked_spreads": len(result.blocked),
        "warnings": sum(len(item.warnings) for item in (*result.selectable, *result.blocked)),
    }


def _reason_summary(result: OptionsAnalysisResult) -> dict[str, Any]:
    reason_counts: Counter[str] = Counter()
    warning_counts: Counter[str] = Counter()
    for evaluation in result.evaluations:
        reason_counts.update(evaluation.reasons)
    for ranked in (*result.selectable, *result.blocked):
        warning_counts.update(warning.code for warning in ranked.warnings)
    return {
        "evaluation_reasons": dict(sorted(reason_counts.items())),
        "warning_codes": dict(sorted(warning_counts.items())),
    }


def _spread_key(run_key: str, spread: SpreadCandidate) -> str:
    return (
        f"{run_key}:spread:{spread.strategy.value}:"
        f"{spread.long_contract_id}:{spread.short_contract_id}:{spread.expiration.isoformat()}"
    )


def _warning_keys(spread_key: str, warnings: tuple[SpreadWarning, ...]) -> list[str]:
    keys = [f"{spread_key}:warning:{warning.code}:{warning.severity}" for warning in warnings]
    duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
    if duplicates:
        raise OptionsAnalysisPersistenceError(
            f"duplicate warning keys for spread: {', '.join(duplicates)}"
        )
    return keys


def _spread_calculations(spread: SpreadCandidate) -> dict[str, Any]:
    payload = canonical_record(
        {
            "debit": spread.debit,
            "maximum_loss": spread.maximum_loss,
            "maximum_gain": spread.maximum_gain,
            "break_even": spread.break_even,
            "net_delta": spread.net_delta,
            "net_gamma": spread.net_gamma,
            "net_theta": spread.net_theta,
            "net_vega": spread.net_vega,
            "liquidity_open_interest": spread.liquidity_open_interest,
            "liquidity_volume": spread.liquidity_volume,
        }
    )
    if not isinstance(payload, dict):
        raise OptionsAnalysisPersistenceError("spread calculations must be an object")
    return payload
