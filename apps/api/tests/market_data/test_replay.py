from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from market_trader.market_calendar.adapter import XNYSCalendarAdapter
from market_trader.market_data.fixtures import (
    FixtureDataset,
    FixtureExpectedCounts,
    FixtureManifest,
    FixtureStream,
)
from market_trader.market_data.models import DataKind, ProviderEvent
from market_trader.market_data.replay import ReplayEngine, VirtualReplayClock
from market_trader.market_data.sinks import InMemoryIngestionSink

BASE_TIME = datetime(2026, 7, 17, 14, 30, tzinfo=UTC)


def test_replay_advances_clock_in_arrival_order() -> None:
    events = (
        quote_event("quote-1", observed_at=BASE_TIME, ingested_at=BASE_TIME),
        quote_event(
            "quote-2",
            observed_at=BASE_TIME + timedelta(seconds=1),
            ingested_at=BASE_TIME + timedelta(seconds=2),
        ),
    )
    clock = VirtualReplayClock()

    result = engine(clock=clock).replay(dataset(events))

    assert clock.visited == tuple(event.ingested_at for event in events)
    assert result.accepted == 2
    assert result.degraded == 0
    assert result.quarantined == 0


def test_older_observation_is_quarantined_without_sorting() -> None:
    events = (
        quote_event("quote-new", observed_at=BASE_TIME + timedelta(seconds=2)),
        quote_event(
            "quote-old",
            observed_at=BASE_TIME + timedelta(seconds=1),
            ingested_at=BASE_TIME + timedelta(seconds=3),
        ),
    )

    result = engine().replay(dataset(events))

    assert result.accepted == 1
    assert result.quarantined == 1
    assert result.reason_count("out_of_order") == 1


def test_equal_observation_timestamps_with_distinct_ids_are_accepted() -> None:
    events = (
        quote_event("quote-1", observed_at=BASE_TIME),
        quote_event("quote-2", observed_at=BASE_TIME, ingested_at=BASE_TIME + timedelta(seconds=1)),
    )

    result = engine().replay(dataset(events))

    assert result.accepted == 2
    assert result.quarantined == 0


def test_exact_duplicate_is_deduplicated() -> None:
    event = quote_event("quote-1", observed_at=BASE_TIME)

    result = engine().replay(dataset((event, event)))

    assert result.accepted == 1
    assert result.deduplicated == 1


def test_same_event_identity_with_different_payload_is_quarantined() -> None:
    first = quote_event("quote-1", observed_at=BASE_TIME)
    conflicting_payload = dict(first.payload)
    conflicting_payload["bid"] = "624.00"
    conflicting = replace(first, payload=conflicting_payload)

    result = engine().replay(dataset((first, conflicting)))

    assert result.accepted == 1
    assert result.quarantined == 1
    assert result.reason_count("event_identity_conflict") == 1


def test_stale_observation_is_blocking_and_uses_rejection_sink() -> None:
    stale = quote_event(
        "quote-stale",
        observed_at=BASE_TIME,
        ingested_at=BASE_TIME + timedelta(seconds=16),
    )
    sink = InMemoryIngestionSink()

    result = engine(sink=sink).replay(dataset((stale,)))

    assert result.stale == 1
    assert result.reason_count("stale") == 1
    assert len(sink.rejected) == 1
    assert len(sink.accepted) == 0


def test_replay_is_idempotent_against_existing_sink() -> None:
    sink = InMemoryIngestionSink()
    replay_engine = engine(sink=sink)
    fixture = dataset((quote_event("quote-1", observed_at=BASE_TIME),))

    first = replay_engine.replay(fixture)
    second = replay_engine.replay(fixture)

    assert first.accepted == 1
    assert second.deduplicated == 1
    assert len(sink.accepted) == 1


def test_fresh_runs_have_identical_result_digest() -> None:
    fixture = dataset((quote_event("quote-1", observed_at=BASE_TIME),))

    first = engine().replay(fixture)
    second = engine().replay(fixture)

    assert first == second
    assert len(first.result_digest) == 64


def engine(
    *,
    clock: VirtualReplayClock | None = None,
    sink: InMemoryIngestionSink | None = None,
) -> ReplayEngine:
    calendar = XNYSCalendarAdapter(start=date(2026, 1, 1), end=date(2027, 12, 31))
    return ReplayEngine(
        clock=clock or VirtualReplayClock(),
        calendar=calendar,
        sink=sink or InMemoryIngestionSink(),
    )


def dataset(events: tuple[ProviderEvent, ...]) -> FixtureDataset:
    manifest = FixtureManifest(
        dataset_id="replay-test",
        description="Replay behavior test.",
        fixture_schema_version=1,
        source="fixture",
        configuration_version="fixture-v1",
        streams=(FixtureStream("quotes.ndjson", DataKind.QUOTE, "0" * 64, len(events)),),
        expected_counts=FixtureExpectedCounts(0, 0, 0, 0, 0),
        expected_result_digest=None,
    )
    return FixtureDataset(path=Path("replay-test"), manifest=manifest, events=events)


def quote_event(
    event_id: str,
    *,
    observed_at: datetime,
    ingested_at: datetime | None = None,
) -> ProviderEvent:
    return ProviderEvent(
        source="fixture",
        event_id=event_id,
        data_kind=DataKind.QUOTE,
        observed_at=observed_at,
        ingested_at=ingested_at or observed_at,
        payload={
            "symbol": "SPY",
            "bid": "625.10",
            "ask": "625.20",
            "bid_size": 100,
            "ask_size": 200,
        },
        fixture_schema_version=1,
        configuration_version="fixture-v1",
        correlation_id=f"corr-{event_id}",
    )
