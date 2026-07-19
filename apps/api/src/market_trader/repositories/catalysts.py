from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.catalysts.models import (
    CatalystDecision,
    CatalystObservation,
    CatalystPolicyVersions,
    CitedSummary,
    QuarantinedObservation,
    SourceRunResult,
    SummarySegment,
)
from market_trader.catalysts.serialization import canonical_record, stable_digest
from market_trader.db.models import (
    CatalystDecisionORM,
    CatalystObservationORM,
    CatalystQuarantineORM,
    CatalystSourceRunORM,
    CatalystSummaryORM,
    SymbolORM,
)
from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc, utc_now
from market_trader.repositories._mapping import stored_utc
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


class CatalystPersistenceConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class PersistedCatalystSourceRun:
    id: str
    run_key: str
    source_id: str
    result_digest: str
    correlation_id: str
    created_at: datetime


class CatalystRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._audit = AuditRepository(session)

    def create_source_run(self, result: SourceRunResult) -> PersistedCatalystSourceRun:
        existing = self._session.scalar(
            select(CatalystSourceRunORM).where(CatalystSourceRunORM.run_key == result.run_key)
        )
        if existing is not None:
            if existing.result_digest != result.result_digest:
                raise CatalystPersistenceConflict(f"source run key conflict: {result.run_key}")
            return _source_run(existing)
        versions = (
            result.decisions[0].policy_versions
            if result.decisions
            else CatalystPolicyVersions()
        )
        correlation_id = stable_digest(result.run_key)
        created_at = utc_now()
        record = CatalystSourceRunORM(
            id=new_domain_id("csr"),
            run_key=result.run_key,
            source_id=result.source_id,
            as_of=ensure_utc(result.as_of),
            state=result.state.value,
            policy_versions=_json_object(versions),
            policy_hashes={},
            result_counts={
                "observations": len(result.observations),
                "quarantined": len(result.quarantined),
                "decisions": len(result.decisions),
                "summaries": len(result.summaries),
            },
            reasons=list(result.reasons),
            result_digest=result.result_digest,
            correlation_id=correlation_id,
            created_at=created_at,
        )
        self._session.add(record)
        self._session.flush()
        self._audit_new(
            record,
            "catalyst_source_run.recorded",
            "catalyst_source_run",
            result.as_of,
            {"run_key": result.run_key, "source_id": result.source_id},
        )
        return _source_run(record)

    def get_source_run(self, run_key: str) -> PersistedCatalystSourceRun | None:
        record = self._session.scalar(
            select(CatalystSourceRunORM).where(CatalystSourceRunORM.run_key == run_key)
        )
        return None if record is None else _source_run(record)

    def record_observation(
        self, source_run_id: str, value: CatalystObservation, symbol_id: str | None
    ) -> CatalystObservation:
        existing = self._session.scalar(
            select(CatalystObservationORM).where(
                CatalystObservationORM.observation_key == value.observation_key
            )
        )
        if existing is not None:
            if existing.authoritative_digest != value.authoritative_digest:
                raise CatalystPersistenceConflict(
                    f"observation key conflict: {value.observation_key}"
                )
            return _observation(existing, self._symbol(existing.symbol_id))
        record = CatalystObservationORM(
            id=new_domain_id("cob"),
            observation_key=value.observation_key,
            source_run_id=source_run_id,
            ingestion_key=value.ingestion_key,
            authoritative_digest=value.authoritative_digest,
            external_text_digest=value.external_text_digest,
            source_id=value.source_id,
            authority_class=value.authority_class.value,
            event_family=value.event_family.value,
            event_category=value.event_category,
            provider_event_id=value.provider_event_id,
            source_reference=value.source_reference,
            symbol_id=symbol_id,
            published_at=value.published_at,
            ingested_at=value.ingested_at,
            scheduled_for=value.scheduled_for,
            valid_until=value.valid_until,
            structured_facts=_json_object(value.structured_facts),
            external_text=_json_object(value.external_text),
            source_schema_version=value.source_schema_version,
            normalization_schema_version=value.normalization_schema_version,
            configuration_version=value.configuration_version,
            correlation_id=value.correlation_id,
            created_at=utc_now(),
        )
        self._session.add(record)
        self._session.flush()
        self._audit_new(
            record,
            "catalyst_observation.recorded",
            "catalyst_observation",
            value.ingested_at,
            {"observation_key": value.observation_key, "source_id": value.source_id},
        )
        return _observation(record, value.symbol)

    def get_observation(self, observation_key: str) -> CatalystObservation | None:
        record = self._session.scalar(
            select(CatalystObservationORM).where(
                CatalystObservationORM.observation_key == observation_key
            )
        )
        return None if record is None else _observation(record, self._symbol(record.symbol_id))

    def record_quarantine(
        self, source_run_id: str, value: QuarantinedObservation
    ) -> QuarantinedObservation:
        existing = self._session.scalar(
            select(CatalystQuarantineORM).where(
                CatalystQuarantineORM.ingestion_key == value.ingestion_key
            )
        )
        if existing is not None:
            if existing.sanitized_payload_digest != value.sanitized_payload_digest:
                raise CatalystPersistenceConflict(
                    f"quarantine key conflict: {value.ingestion_key}"
                )
            return _quarantine(existing)
        record = CatalystQuarantineORM(
            id=new_domain_id("cqu"),
            source_run_id=source_run_id,
            ingestion_key=value.ingestion_key,
            sanitized_payload_digest=value.sanitized_payload_digest,
            source_id=value.source_id,
            provider_event_id=value.provider_event_id,
            published_at=value.published_at,
            ingested_at=value.ingested_at,
            reasons=list(value.reasons),
            sanitized_payload=_json_object(value.sanitized_payload),
            source_schema_version=value.source_schema_version,
            normalization_schema_version=value.normalization_schema_version,
            correlation_id=value.correlation_id,
            created_at=utc_now(),
        )
        self._session.add(record)
        self._session.flush()
        self._audit_new(
            record,
            "catalyst_quarantine.recorded",
            "catalyst_quarantine",
            value.ingested_at,
            {"ingestion_key": value.ingestion_key, "reasons": list(value.reasons)},
        )
        return _quarantine(record)

    def get_quarantine(self, ingestion_key: str) -> QuarantinedObservation | None:
        record = self._session.scalar(
            select(CatalystQuarantineORM).where(
                CatalystQuarantineORM.ingestion_key == ingestion_key
            )
        )
        return None if record is None else _quarantine(record)

    def record_decision(
        self, source_run_id: str, value: CatalystDecision, symbol_id: str | None
    ) -> CatalystDecision:
        existing = self._session.scalar(
            select(CatalystDecisionORM).where(
                CatalystDecisionORM.decision_key == value.decision_key
            )
        )
        if existing is not None:
            if existing.input_digest != value.input_digest:
                raise CatalystPersistenceConflict(f"decision key conflict: {value.decision_key}")
            return _decision(existing, self._symbol(existing.symbol_id))
        record = CatalystDecisionORM(
            id=new_domain_id("cde"),
            decision_key=value.decision_key,
            source_run_id=source_run_id,
            scope=value.scope,
            symbol_id=symbol_id,
            as_of=value.as_of,
            materiality=value.materiality.value,
            direction=value.direction.value,
            confirmation=value.confirmation.value,
            risk_state=value.risk_state.value,
            reasons=list(value.reasons),
            observation_keys=list(value.observation_keys),
            policy_versions=_json_object(value.policy_versions),
            input_digest=value.input_digest,
            explanation=_json_object(value.explanation),
            correlation_id=stable_digest(value.decision_key),
            created_at=utc_now(),
        )
        self._session.add(record)
        self._session.flush()
        self._audit_new(
            record,
            "catalyst_decision.recorded",
            "catalyst_decision",
            value.as_of,
            {"decision_key": value.decision_key, "input_digest": value.input_digest},
        )
        return _decision(record, value.symbol)

    def get_decision(self, decision_key: str) -> CatalystDecision | None:
        record = self._session.scalar(
            select(CatalystDecisionORM).where(CatalystDecisionORM.decision_key == decision_key)
        )
        return None if record is None else _decision(record, self._symbol(record.symbol_id))

    def record_summary(self, source_run_id: str, value: CitedSummary) -> CitedSummary:
        existing = self._session.scalar(
            select(CatalystSummaryORM).where(CatalystSummaryORM.summary_key == value.summary_key)
        )
        if existing is not None:
            if existing.content_digest != value.content_digest:
                raise CatalystPersistenceConflict(f"summary key conflict: {value.summary_key}")
            return _summary(existing)
        record = CatalystSummaryORM(
            id=new_domain_id("csu"),
            summary_key=value.summary_key,
            source_run_id=source_run_id,
            provider_id=value.provider_id,
            generated_at=value.generated_at,
            segments=cast(list[dict[str, Any]], canonical_record(value.segments)),
            policy_version=value.policy_version,
            content_digest=value.content_digest,
            correlation_id=stable_digest(value.summary_key),
            created_at=utc_now(),
        )
        self._session.add(record)
        self._session.flush()
        self._audit_new(
            record,
            "catalyst_summary.recorded",
            "catalyst_summary",
            value.generated_at,
            {"summary_key": value.summary_key, "content_digest": value.content_digest},
        )
        return _summary(record)

    def get_summary(self, summary_key: str) -> CitedSummary | None:
        record = self._session.scalar(
            select(CatalystSummaryORM).where(CatalystSummaryORM.summary_key == summary_key)
        )
        return None if record is None else _summary(record)

    def _audit_new(
        self,
        record: Any,
        event_type: str,
        subject_type: str,
        occurred_at: datetime,
        payload: dict[str, Any],
    ) -> None:
        self._audit.append(
            AuditEventCreate(
                correlation_id=record.correlation_id,
                event_type=event_type,
                actor_type="system",
                occurred_at=occurred_at,
                subject_type=subject_type,
                subject_id=record.id,
                payload={"schema_version": 1, **payload},
                schema_version=1,
            )
        )

    def _symbol(self, symbol_id: str | None) -> str | None:
        if symbol_id is None:
            return None
        record = self._session.get(SymbolORM, symbol_id)
        return None if record is None else record.display_symbol


def _source_run(record: CatalystSourceRunORM) -> PersistedCatalystSourceRun:
    return PersistedCatalystSourceRun(
        record.id,
        record.run_key,
        record.source_id,
        record.result_digest,
        record.correlation_id,
        stored_utc(record.created_at),
    )


def _observation(record: CatalystObservationORM, symbol: str | None) -> CatalystObservation:
    from market_trader.catalysts.models import AuthorityClass, EventFamily

    return CatalystObservation(
        observation_key=record.observation_key,
        ingestion_key=record.ingestion_key,
        authoritative_digest=record.authoritative_digest,
        external_text_digest=record.external_text_digest,
        source_id=record.source_id,
        authority_class=AuthorityClass(record.authority_class),
        event_family=EventFamily(record.event_family),
        event_category=record.event_category,
        provider_event_id=record.provider_event_id,
        source_reference=record.source_reference,
        symbol=symbol,
        published_at=stored_utc(record.published_at),
        ingested_at=stored_utc(record.ingested_at),
        scheduled_for=None if record.scheduled_for is None else stored_utc(record.scheduled_for),
        valid_until=stored_utc(record.valid_until),
        structured_facts=dict(record.structured_facts),
        external_text=dict(record.external_text),
        source_schema_version=record.source_schema_version,
        normalization_schema_version=record.normalization_schema_version,
        configuration_version=record.configuration_version,
        correlation_id=record.correlation_id,
    )


def _quarantine(record: CatalystQuarantineORM) -> QuarantinedObservation:
    return QuarantinedObservation(
        ingestion_key=record.ingestion_key,
        sanitized_payload_digest=record.sanitized_payload_digest,
        source_id=record.source_id,
        provider_event_id=record.provider_event_id,
        published_at=None if record.published_at is None else stored_utc(record.published_at),
        ingested_at=stored_utc(record.ingested_at),
        reasons=tuple(record.reasons),
        sanitized_payload=dict(record.sanitized_payload),
        source_schema_version=record.source_schema_version,
        normalization_schema_version=record.normalization_schema_version,
        correlation_id=record.correlation_id,
    )


def _decision(record: CatalystDecisionORM, symbol: str | None) -> CatalystDecision:
    from market_trader.catalysts.models import (
        CatalystDirection,
        ConfirmationState,
        Materiality,
        RiskState,
    )

    versions = record.policy_versions
    return CatalystDecision(
        decision_key=record.decision_key,
        scope=record.scope,
        symbol=symbol,
        as_of=stored_utc(record.as_of),
        materiality=Materiality(record.materiality),
        direction=CatalystDirection(record.direction),
        confirmation=ConfirmationState(record.confirmation),
        risk_state=RiskState(record.risk_state),
        reasons=tuple(record.reasons),
        observation_keys=tuple(record.observation_keys),
        policy_versions=CatalystPolicyVersions(**versions),
        input_digest=record.input_digest,
        explanation=dict(record.explanation),
    )


def _summary(record: CatalystSummaryORM) -> CitedSummary:
    return CitedSummary(
        summary_key=record.summary_key,
        provider_id=record.provider_id,
        generated_at=stored_utc(record.generated_at),
        segments=tuple(
            SummarySegment(
                text=item["text"],
                observation_keys=tuple(item["observation_keys"]),
                source_references=tuple(item["source_references"]),
            )
            for item in record.segments
        ),
        policy_version=record.policy_version,
        content_digest=record.content_digest,
    )


def _json_object(value: object) -> dict[str, Any]:
    record = canonical_record(value)
    if not isinstance(record, dict):
        raise TypeError("catalyst persistence payload must be an object")
    return record
