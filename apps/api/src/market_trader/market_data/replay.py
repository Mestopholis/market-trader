from dataclasses import dataclass
from datetime import datetime

from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.models import ExchangeCalendar
from market_trader.market_data.fixtures import FixtureDataset, FixtureExpectedCounts
from market_trader.market_data.models import ProviderEvent, QualityState, RejectedObservation
from market_trader.market_data.pipeline import MarketDataPipeline
from market_trader.market_data.quality import FreshnessPolicy
from market_trader.market_data.sanitization import (
    SanitizedValue,
    canonical_digest,
    ingestion_key,
    sanitize_payload,
)
from market_trader.market_data.sinks import (
    AcceptedIngestion,
    IngestionSink,
    RejectedIngestion,
)


class VirtualReplayClock:
    def __init__(self) -> None:
        self._value: datetime | None = None
        self._visited: list[datetime] = []

    @property
    def visited(self) -> tuple[datetime, ...]:
        return tuple(self._visited)

    def now(self) -> datetime:
        if self._value is None:
            raise RuntimeError("replay clock has not started")
        return self._value

    def advance_to(self, value: datetime) -> None:
        value = ensure_utc(value)
        if self._value is not None and value < self._value:
            raise ValueError("replay clock cannot move backward")
        self._value = value
        self._visited.append(value)


@dataclass(frozen=True)
class ReplayResult:
    dataset_id: str
    configuration_version: str
    policy_versions: tuple[str, ...]
    accepted: int
    degraded: int
    stale: int
    quarantined: int
    deduplicated: int
    reasons: tuple[tuple[str, int], ...]
    result_digest: str

    @property
    def counts(self) -> FixtureExpectedCounts:
        return FixtureExpectedCounts(
            accepted=self.accepted,
            degraded=self.degraded,
            stale=self.stale,
            quarantined=self.quarantined,
            deduplicated=self.deduplicated,
        )

    def reason_count(self, reason_code: str) -> int:
        return dict(self.reasons).get(reason_code, 0)


class ReplayEngine:
    def __init__(
        self,
        *,
        clock: VirtualReplayClock,
        calendar: ExchangeCalendar,
        sink: IngestionSink,
    ) -> None:
        self._clock = clock
        self._sink = sink
        freshness_policy = FreshnessPolicy.v1(calendar=calendar, clock=clock)
        self._policy_versions = (freshness_policy.version,)
        self._pipeline = MarketDataPipeline(freshness_policy=freshness_policy)

    def replay(self, dataset: FixtureDataset) -> ReplayResult:
        counts = _MutableCounts()
        reason_counts: dict[str, int] = {}
        outcome_records: list[SanitizedValue] = []
        watermarks: dict[tuple[str, str, str], datetime] = {}

        for event in dataset.events:
            self._clock.advance_to(event.ingested_at)
            sanitized_payload = sanitize_payload(event.payload)
            payload_digest = canonical_digest(sanitized_payload)
            event_key = ingestion_key(
                event.source,
                event.event_id,
                event.fixture_schema_version,
            )
            existing_digest = self._sink.payload_digest_for(event_key)
            if existing_digest is not None:
                if existing_digest == payload_digest:
                    counts.deduplicated += 1
                    self._record(
                        outcome_records,
                        event_key,
                        payload_digest,
                        "deduplicated",
                        (),
                    )
                    continue
                conflict_key = self._conflict_key(event_key, payload_digest)
                if self._sink.payload_digest_for(conflict_key) == payload_digest:
                    counts.deduplicated += 1
                    self._record(
                        outcome_records,
                        conflict_key,
                        payload_digest,
                        "deduplicated",
                        (),
                    )
                    continue
                rejection = self._pipeline.reject(event, "event_identity_conflict")
                self._write_rejection(
                    conflict_key,
                    payload_digest,
                    sanitized_payload,
                    event,
                    rejection,
                )
                counts.quarantined += 1
                self._add_reasons(reason_counts, rejection.reason_codes)
                self._record_rejection(outcome_records, conflict_key, payload_digest, rejection)
                continue

            result = self._pipeline.normalize(event)
            if result.rejection is not None:
                rejection = result.rejection
                self._write_rejection(
                    event_key,
                    payload_digest,
                    sanitized_payload,
                    event,
                    rejection,
                )
                if rejection.quality_state is QualityState.STALE:
                    counts.stale += 1
                else:
                    counts.quarantined += 1
                self._add_reasons(reason_counts, rejection.reason_codes)
                self._record_rejection(outcome_records, event_key, payload_digest, rejection)
                continue

            value = result.accepted
            assert value is not None
            identity = self._pipeline.identity(value)
            watermark_key = (event.source, event.data_kind.value, identity)
            watermark = watermarks.get(watermark_key)
            if watermark is not None and event.observed_at < watermark:
                rejection = self._pipeline.reject(
                    event,
                    "out_of_order",
                    symbol_identity=identity,
                )
                self._write_rejection(
                    event_key,
                    payload_digest,
                    sanitized_payload,
                    event,
                    rejection,
                )
                counts.quarantined += 1
                self._add_reasons(reason_counts, rejection.reason_codes)
                self._record_rejection(outcome_records, event_key, payload_digest, rejection)
                continue

            watermarks[watermark_key] = event.observed_at
            state = value.metadata.quality_state
            reasons = value.metadata.quality_reasons
            self._sink.write_accepted(
                AcceptedIngestion(
                    ingestion_key=event_key,
                    payload_digest=payload_digest,
                    sanitized_payload=sanitized_payload,
                    event=event,
                    value=value,
                    quality_state=state,
                    reason_codes=reasons,
                )
            )
            if state is QualityState.DEGRADED:
                counts.degraded += 1
            else:
                counts.accepted += 1
            self._add_reasons(reason_counts, reasons)
            self._record(outcome_records, event_key, payload_digest, state.value, reasons)

        return ReplayResult(
            dataset_id=dataset.manifest.dataset_id,
            configuration_version=dataset.manifest.configuration_version,
            policy_versions=self._policy_versions,
            accepted=counts.accepted,
            degraded=counts.degraded,
            stale=counts.stale,
            quarantined=counts.quarantined,
            deduplicated=counts.deduplicated,
            reasons=tuple(sorted(reason_counts.items())),
            result_digest=canonical_digest(outcome_records),
        )

    def _write_rejection(
        self,
        key: str,
        payload_digest: str,
        sanitized_payload: SanitizedValue,
        event: ProviderEvent,
        rejection: RejectedObservation,
    ) -> None:
        self._sink.write_rejected(
            RejectedIngestion(
                ingestion_key=key,
                payload_digest=payload_digest,
                sanitized_payload=sanitized_payload,
                event=event,
                rejection=rejection,
            )
        )

    @staticmethod
    def _conflict_key(event_key: str, payload_digest: str) -> str:
        return f"conflict_{canonical_digest([event_key, payload_digest])}"

    @staticmethod
    def _add_reasons(counts: dict[str, int], reasons: tuple[str, ...]) -> None:
        for reason in reasons:
            counts[reason] = counts.get(reason, 0) + 1

    @staticmethod
    def _record(
        records: list[SanitizedValue],
        key: str,
        payload_digest: str,
        state: str,
        reasons: tuple[str, ...],
    ) -> None:
        records.append(
            {
                "ingestion_key": key,
                "payload_digest": payload_digest,
                "state": state,
                "reason_codes": list(reasons),
            }
        )

    @classmethod
    def _record_rejection(
        cls,
        records: list[SanitizedValue],
        key: str,
        payload_digest: str,
        rejection: RejectedObservation,
    ) -> None:
        cls._record(
            records,
            key,
            payload_digest,
            rejection.quality_state.value,
            rejection.reason_codes,
        )


@dataclass
class _MutableCounts:
    accepted: int = 0
    degraded: int = 0
    stale: int = 0
    quarantined: int = 0
    deduplicated: int = 0
