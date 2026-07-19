from dataclasses import dataclass
from datetime import datetime

from market_trader.catalysts.classification import (
    ClassifiedObservation,
    classify_observation,
)
from market_trader.catalysts.configuration import CatalystConfiguration
from market_trader.catalysts.decisions import SourceStatus, decide_catalysts
from market_trader.catalysts.fixtures import CatalystFixtureDataset, CatalystFixtureRecord
from market_trader.catalysts.models import (
    CatalystDecision,
    CatalystObservation,
    CatalystProviderEvent,
    CitedSummary,
    EventFamily,
    EventRiskWindow,
    QuarantinedObservation,
    SourceFailure,
    SourceState,
)
from market_trader.catalysts.normalizers import ObservationWatermark, normalize_event
from market_trader.catalysts.risk import EventRiskEvaluator
from market_trader.catalysts.serialization import stable_digest
from market_trader.catalysts.summaries import (
    SummaryProviderResponse,
    validate_cited_summary,
)
from market_trader.domain.time import ensure_utc
from market_trader.market_calendar.models import ExchangeCalendar
from market_trader.market_data.sanitization import ingestion_key


class CatalystReplayMismatchError(ValueError):
    pass


class VirtualCatalystClock:
    def __init__(self) -> None:
        self._value: datetime | None = None
        self._visited: list[datetime] = []

    @property
    def visited(self) -> tuple[datetime, ...]:
        return tuple(self._visited)

    def now(self) -> datetime:
        if self._value is None:
            raise RuntimeError("catalyst replay clock has not started")
        return self._value

    def advance_to(self, value: datetime) -> None:
        current = ensure_utc(value)
        if self._value is not None and current < self._value:
            raise ValueError("catalyst replay clock cannot move backward")
        self._value = current
        self._visited.append(current)


class InMemoryCatalystReplaySink:
    def __init__(self) -> None:
        self.observations: dict[str, CatalystObservation] = {}
        self.quarantined: dict[str, QuarantinedObservation] = {}
        self.summaries: dict[str, CitedSummary] = {}
        self.event_digests: dict[str, str] = {}

    def write_observation(self, observation: CatalystObservation, event_digest: str) -> None:
        self.observations[observation.ingestion_key] = observation
        self.event_digests[observation.ingestion_key] = event_digest

    def write_quarantine(self, quarantine: QuarantinedObservation) -> None:
        self.quarantined[quarantine.ingestion_key] = quarantine

    def write_summary(self, summary: CitedSummary) -> None:
        self.summaries[summary.summary_key] = summary


@dataclass(frozen=True)
class CatalystReplayResult:
    dataset_id: str
    accepted: int
    quarantined: int
    deduplicated: int
    source_failures: int
    source_recoveries: int
    classifications: tuple[ClassifiedObservation, ...]
    risk_windows: tuple[EventRiskWindow, ...]
    decisions: tuple[CatalystDecision, ...]
    summaries: tuple[CitedSummary, ...]
    reasons: tuple[tuple[str, int], ...]
    result_digest: str
    reason_digest: str

    def reason_count(self, reason: str) -> int:
        return dict(self.reasons).get(reason, 0)


class CatalystReplayEngine:
    def __init__(
        self,
        *,
        clock: VirtualCatalystClock,
        calendar: ExchangeCalendar,
        configuration: CatalystConfiguration,
        sink: InMemoryCatalystReplaySink,
    ) -> None:
        self._clock = clock
        self._configuration = configuration
        self._sink = sink
        self._risk = EventRiskEvaluator(calendar=calendar, policy=configuration.risk)

    def replay(self, dataset: CatalystFixtureDataset) -> CatalystReplayResult:
        if dict(dataset.manifest.policy_hashes) != dict(self._configuration.content_hashes):
            raise CatalystReplayMismatchError("fixture policy hashes do not match configuration")
        counts = _ReplayCounts()
        reasons: dict[str, int] = {}
        source_states: dict[str, SourceState] = {}
        source_reasons: dict[str, tuple[str, ...]] = {}
        summaries: list[CitedSummary] = []

        for record in dataset.records:
            timestamp = _record_time(record)
            self._clock.advance_to(timestamp)
            if isinstance(record, SourceFailure):
                counts.source_failures += 1
                source_states[record.source_id] = _source_state(record)
                source_reasons[record.source_id] = record.reasons
                _add_reasons(reasons, record.reasons)
                continue
            if isinstance(record, SummaryProviderResponse):
                result = validate_cited_summary(
                    record,
                    {
                        observation.observation_key: observation
                        for observation in self._sink.observations.values()
                    },
                    self._configuration.summary,
                    quarantined_observation_keys=tuple(self._sink.quarantined),
                )
                if result.summary is None:
                    _add_reasons(reasons, result.reasons)
                else:
                    self._sink.write_summary(result.summary)
                    summaries.append(result.summary)
                continue

            prior_state = source_states.get(record.source_id)
            if prior_state is not None and prior_state is not SourceState.AVAILABLE:
                counts.source_recoveries += 1
                _add_reasons(reasons, ("source_recovered",))
            source_states[record.source_id] = SourceState.AVAILABLE
            source_reasons[record.source_id] = ()
            event_key = _event_key(record)
            event_digest = stable_digest(record)
            existing_digest = self._sink.event_digests.get(event_key)
            if existing_digest == event_digest:
                counts.deduplicated += 1
                continue
            watermark = self._watermark(record)
            normalized = normalize_event(
                record,
                as_of=self._clock.now(),
                configuration=self._configuration,
                watermark=watermark,
            )
            if normalized.quarantine is not None:
                self._sink.write_quarantine(normalized.quarantine)
                counts.quarantined += 1
                _add_reasons(reasons, normalized.quarantine.reasons)
                continue
            observation = normalized.observation
            assert observation is not None
            if observation.ingestion_key in self._sink.observations:
                counts.deduplicated += 1
                continue
            self._sink.write_observation(observation, event_digest)
            counts.accepted += 1

        observations = tuple(
            sorted(self._sink.observations.values(), key=lambda item: item.observation_key)
        )
        classifications = tuple(
            ClassifiedObservation(
                observation=observation,
                classification=classify_observation(
                    observation,
                    self._configuration.classification,
                ),
            )
            for observation in observations
        )
        windows = self._risk_windows(observations, dataset.manifest.as_of)
        statuses = _source_statuses(
            observations,
            source_states,
            source_reasons,
            dataset.manifest.as_of,
        )
        decisions = decide_catalysts(
            classifications,
            windows,
            statuses,
            as_of=dataset.manifest.as_of,
            policy_versions=dataset.manifest.policy_versions,
        )
        reason_items = tuple(sorted(reasons.items()))
        reason_digest = stable_digest(reason_items)
        result_record = {
            "dataset_id": dataset.manifest.dataset_id,
            "accepted": counts.accepted,
            "quarantined": counts.quarantined,
            "deduplicated": counts.deduplicated,
            "source_failures": counts.source_failures,
            "source_recoveries": counts.source_recoveries,
            "observations": observations,
            "quarantines": tuple(
                sorted(self._sink.quarantined.values(), key=lambda item: item.ingestion_key)
            ),
            "classifications": classifications,
            "risk_windows": windows,
            "decisions": decisions,
            "summaries": tuple(sorted(summaries, key=lambda item: item.summary_key)),
            "reason_digest": reason_digest,
            "policy_versions": dataset.manifest.policy_versions,
            "policy_hashes": dataset.manifest.policy_hashes,
        }
        result_digest = stable_digest(result_record)
        _validate_expected_digest(
            "reason digest",
            dataset.manifest.expected_reason_digest,
            reason_digest,
        )
        _validate_expected_digest(
            "result digest",
            dataset.manifest.expected_result_digest,
            result_digest,
        )
        return CatalystReplayResult(
            dataset_id=dataset.manifest.dataset_id,
            accepted=counts.accepted,
            quarantined=counts.quarantined,
            deduplicated=counts.deduplicated,
            source_failures=counts.source_failures,
            source_recoveries=counts.source_recoveries,
            classifications=classifications,
            risk_windows=windows,
            decisions=decisions,
            summaries=tuple(sorted(summaries, key=lambda item: item.summary_key)),
            reasons=reason_items,
            result_digest=result_digest,
            reason_digest=reason_digest,
        )

    def _watermark(self, event: CatalystProviderEvent) -> ObservationWatermark:
        matching = tuple(
            observation
            for observation in self._sink.observations.values()
            if observation.source_id == event.source_id
            and observation.symbol == event.symbol_identity
            and observation.event_family is event.event_family
        )
        latest = max((item.published_at for item in matching), default=None)
        return ObservationWatermark(
            latest_published_at=latest,
            observations_by_ingestion_key=self._sink.observations,
        )

    def _risk_windows(
        self,
        observations: tuple[CatalystObservation, ...],
        as_of: datetime,
    ) -> tuple[EventRiskWindow, ...]:
        earnings_symbols = sorted(
            {
                item.symbol
                for item in observations
                if item.event_family is EventFamily.EARNINGS and item.symbol is not None
            }
        )
        macro_categories = sorted(
            {
                item.event_category
                for item in observations
                if item.event_family is EventFamily.ECONOMIC_RELEASE
                and item.event_category in self._configuration.risk.high_impact_macro
            }
        )
        return (
            *(
                self._risk.evaluate_earnings(symbol, observations, as_of=as_of)
                for symbol in earnings_symbols
            ),
            *(
                self._risk.evaluate_macro(category, observations, as_of=as_of)
                for category in macro_categories
            ),
        )


@dataclass
class _ReplayCounts:
    accepted: int = 0
    quarantined: int = 0
    deduplicated: int = 0
    source_failures: int = 0
    source_recoveries: int = 0


def _record_time(record: CatalystFixtureRecord) -> datetime:
    if isinstance(record, SourceFailure):
        return record.occurred_at
    if isinstance(record, SummaryProviderResponse):
        return record.generated_at
    return ensure_utc(record.ingested_at)


def _event_key(event: CatalystProviderEvent) -> str:
    return ingestion_key(
        event.source_id,
        event.provider_event_id,
        event.provider_schema_version,
    )


def _source_state(failure: SourceFailure) -> SourceState:
    if failure.kind.value == "partial":
        return SourceState.DEGRADED
    if failure.kind.value == "malformed":
        return SourceState.MALFORMED
    return SourceState.UNAVAILABLE


def _source_statuses(
    observations: tuple[CatalystObservation, ...],
    states: dict[str, SourceState],
    reasons: dict[str, tuple[str, ...]],
    as_of: datetime,
) -> tuple[SourceStatus, ...]:
    identities = {
        (
            item.source_id,
            "market" if item.symbol is None else "symbol",
            item.symbol,
        )
        for item in observations
    }
    return tuple(
        SourceStatus(
            source_id=source_id,
            state=states.get(source_id, SourceState.AVAILABLE),
            observed_at=as_of,
            required=False,
            scope=scope,
            symbol=symbol,
            reasons=reasons.get(source_id, ()),
        )
        for source_id, scope, symbol in sorted(
            identities,
            key=lambda item: (item[0], item[1], item[2] or ""),
        )
    )


def _add_reasons(counts: dict[str, int], reasons: tuple[str, ...]) -> None:
    for reason in reasons:
        counts[reason] = counts.get(reason, 0) + 1


def _validate_expected_digest(label: str, expected: str | None, actual: str) -> None:
    if expected is not None and expected != actual:
        raise CatalystReplayMismatchError(f"fixture {label} mismatch")
