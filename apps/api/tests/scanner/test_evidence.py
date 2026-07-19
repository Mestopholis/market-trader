from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import MappingProxyType

import pytest

from market_trader.scanner.evidence import (
    SECTOR_ETFS,
    CatalystDirection,
    CatalystMateriality,
    EvidenceValidationError,
    MacroState,
    VolatilityDirection,
    parse_supplemental_evidence,
)
from market_trader.scanner.serialization import stable_digest

AS_OF = datetime(2026, 7, 17, 20, 0, tzinfo=UTC)


def _common(
    evidence_type: str,
    lineage_id: str,
    *,
    observed_at: datetime | None = None,
    valid_until: datetime | None = None,
) -> dict[str, object]:
    return {
        "evidence_type": evidence_type,
        "schema_version": "scanner-evidence-v1",
        "configuration_version": "market-regime-v1",
        "correlation_id": f"scan-{lineage_id}",
        "lineage_id": lineage_id,
        "source": "synthetic-fixture",
        "observed_at": (observed_at or AS_OF - timedelta(minutes=5)).isoformat(),
        "valid_until": (valid_until or AS_OF).isoformat(),
    }


def _breadth() -> dict[str, object]:
    return {
        **_common("breadth", "breadth-1"),
        "source_universe": "synthetic-us-listed",
        "session_date": "2026-07-17",
        "total_eligible_issues": 500,
        "advancing_issues": 300,
        "declining_issues": 150,
        "unchanged_issues": 50,
        "issues_above_sma_50": 275,
        "up_volume": "1250000.50",
        "down_volume": "750000.25",
    }


def _sector() -> dict[str, object]:
    observations = [
        {
            "symbol": symbol,
            "sector": sector,
            "close_relative_to_sma_50": "1.0100",
            "return_20_session": str(Decimal(index) / Decimal("100")),
        }
        for index, (symbol, sector) in enumerate(SECTOR_ETFS.items(), start=1)
    ]
    return {
        **_common("sector", "sector-1"),
        "session_date": "2026-07-17",
        "observations": observations,
    }


def _volatility() -> dict[str, object]:
    return {
        **_common("volatility", "volatility-1"),
        "measure": "synthetic-volatility-index",
        "current_value": "18.5",
        "value_five_sessions_earlier": "20.0",
        "median_20_session": "19.25",
    }


def _macro() -> dict[str, object]:
    return {
        **_common("macro", "macro-1"),
        "state": "risk_on",
        "reason_codes": ["credit_spreads_stable", "rates_stable"],
    }


def _catalyst(
    evidence_id: str = "catalyst-1",
    lineage_id: str = "catalyst-lineage-1",
    direction: str = "positive",
) -> dict[str, object]:
    return {
        **_common("catalyst", lineage_id),
        "evidence_id": evidence_id,
        "symbol": "NVDA",
        "source_reference": "https://example.test/filings/catalyst-1",
        "published_at": (AS_OF - timedelta(hours=2)).isoformat(),
        "materiality": "material",
        "direction": direction,
        "category": "earnings_guidance",
    }


def _records() -> list[dict[str, object]]:
    return [_breadth(), _sector(), _volatility(), _macro(), _catalyst()]


def test_parses_all_evidence_types_into_immutable_typed_values() -> None:
    records = _records()

    result = parse_supplemental_evidence(records, as_of=AS_OF)

    assert result.as_of == AS_OF
    assert result.breadth[0].total_eligible_issues == 500
    assert result.breadth[0].up_volume == Decimal("1250000.50")
    assert tuple(item.symbol for item in result.sector[0].observations) == tuple(SECTOR_ETFS)
    assert result.volatility[0].direction is VolatilityDirection.FALLING
    assert result.macro[0].state is MacroState.RISK_ON
    assert result.macro[0].reason_codes == ("credit_spreads_stable", "rates_stable")
    assert result.catalysts[0].materiality is CatalystMateriality.MATERIAL
    assert result.catalysts[0].direction is CatalystDirection.POSITIVE
    assert result.breadth[0].is_current(AS_OF)
    assert isinstance(result.sector_by_symbol, MappingProxyType)
    with pytest.raises(TypeError):
        result.sector_by_symbol["XLK"] = result.sector[0].observations[0]  # type: ignore[index]

    records[0]["source_universe"] = "mutated"
    assert result.breadth[0].source_universe == "synthetic-us-listed"


def test_normalizes_aware_timestamps_and_freshness_boundary_is_inclusive() -> None:
    offset = datetime.fromisoformat("2026-07-17T15:00:00-05:00")
    records = _records()
    records[0] = _breadth() | {
        "observed_at": offset.isoformat(),
        "valid_until": offset.isoformat(),
    }

    result = parse_supplemental_evidence(records, as_of=AS_OF)

    assert result.breadth[0].observed_at == AS_OF
    assert result.breadth[0].is_current(AS_OF)
    assert not result.breadth[0].is_current(AS_OF + timedelta(microseconds=1))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("observed_at", "2026-07-17T19:55:00", "timezone-aware"),
        ("valid_until", "2026-07-17T20:00:00", "timezone-aware"),
        ("observed_at", "2026-07-17T20:00:00.000001+00:00", "after as_of"),
        ("valid_until", "2026-07-17T19:54:59+00:00", "before observed_at"),
    ],
)
def test_rejects_invalid_temporal_bounds(field: str, value: str, message: str) -> None:
    record = _breadth()
    record[field] = value

    with pytest.raises(EvidenceValidationError, match=message):
        parse_supplemental_evidence([record, _sector(), _volatility(), _macro()], as_of=AS_OF)


def test_rejects_naive_as_of() -> None:
    with pytest.raises(EvidenceValidationError, match="as_of must be timezone-aware"):
        parse_supplemental_evidence(_records(), as_of=AS_OF.replace(tzinfo=None))


def test_stale_evidence_is_retained_for_later_blocking_logic() -> None:
    stale = _macro()
    stale["valid_until"] = (AS_OF - timedelta(seconds=1)).isoformat()

    result = parse_supplemental_evidence(
        [_breadth(), _sector(), _volatility(), stale], as_of=AS_OF
    )

    assert not result.macro[0].is_current(AS_OF)


def test_rejects_future_sessions_and_retains_conflicting_session_or_config_versions() -> None:
    breadth = _breadth()
    breadth["session_date"] = "2026-07-18"
    with pytest.raises(EvidenceValidationError, match="session_date is after as_of"):
        parse_supplemental_evidence(
            [breadth, _sector(), _volatility(), _macro()], as_of=AS_OF
        )

    sector = _sector()
    sector["session_date"] = "2026-07-16"
    session_conflict = parse_supplemental_evidence(
        [_breadth(), sector, _volatility(), _macro()], as_of=AS_OF
    )
    assert session_conflict.breadth[0].session_date != session_conflict.sector[0].session_date

    macro = _macro()
    macro["configuration_version"] = "macro-policy-v1"
    version_conflict = parse_supplemental_evidence(
        [_breadth(), _sector(), _volatility(), macro], as_of=AS_OF
    )
    assert version_conflict.macro[0].configuration_version == "macro-policy-v1"


def test_malformed_timestamp_has_a_stable_sanitized_error() -> None:
    breadth = _breadth()
    breadth["observed_at"] = "not-a-timestamp"

    with pytest.raises(
        EvidenceValidationError, match="breadth.observed_at must be a valid timestamp"
    ) as caught:
        parse_supplemental_evidence(
            [breadth, _sector(), _volatility(), _macro()], as_of=AS_OF
        )

    assert "not-a-timestamp" not in str(caught.value)


@pytest.mark.parametrize("state", ["risk_on", "neutral", "risk_off", "blocked"])
def test_accepts_only_approved_macro_states(state: str) -> None:
    macro = _macro()
    macro["state"] = state

    result = parse_supplemental_evidence(
        [_breadth(), _sector(), _volatility(), macro], as_of=AS_OF
    )

    assert result.macro[0].state.value == state


@pytest.mark.parametrize("direction", ["positive", "negative", "unclear"])
@pytest.mark.parametrize("materiality", ["material", "non_material"])
def test_accepts_only_approved_catalyst_states(direction: str, materiality: str) -> None:
    catalyst = _catalyst(direction=direction)
    catalyst["materiality"] = materiality

    result = parse_supplemental_evidence(
        [_breadth(), _sector(), _volatility(), _macro(), catalyst], as_of=AS_OF
    )

    assert result.catalysts[0].direction.value == direction
    assert result.catalysts[0].materiality.value == materiality


@pytest.mark.parametrize(
    ("record", "message"),
    [
        (_macro() | {"state": "optimistic"}, "invalid macro.state"),
        (_catalyst(direction="bullish"), "invalid catalyst.direction"),
        (_catalyst() | {"materiality": "high"}, "invalid catalyst.materiality"),
    ],
)
def test_rejects_unknown_evidence_states(record: dict[str, object], message: str) -> None:
    records = [_breadth(), _sector(), _volatility(), _macro(), _catalyst()]
    records = [
        item for item in records if item["evidence_type"] != record["evidence_type"]
    ]
    with pytest.raises(EvidenceValidationError, match=message):
        parse_supplemental_evidence([*records, record], as_of=AS_OF)


def test_retains_missing_and_conflicting_regime_evidence_for_fail_closed_classification() -> None:
    missing = parse_supplemental_evidence(
        [_breadth(), _volatility(), _macro()], as_of=AS_OF
    )
    assert missing.sector == ()

    second_breadth = _breadth()
    second_breadth["lineage_id"] = "breadth-2"
    second_breadth["advancing_issues"] = 150
    second_breadth["declining_issues"] = 300
    conflicting = parse_supplemental_evidence(
        [_breadth(), second_breadth, _sector(), _volatility(), _macro()],
        as_of=AS_OF,
    )
    assert len(conflicting.breadth) == 2
    assert {item.lineage_id for item in conflicting.breadth} == {
        "breadth-1",
        "breadth-2",
    }


def test_requires_exact_sector_symbols_and_identities() -> None:
    missing = _sector()
    missing["observations"] = missing["observations"][:-1]  # type: ignore[index]
    with pytest.raises(EvidenceValidationError, match="exactly 11 sector observations"):
        parse_supplemental_evidence(
            [_breadth(), missing, _volatility(), _macro()], as_of=AS_OF
        )

    duplicate = _sector()
    observations = deepcopy(duplicate["observations"])
    assert isinstance(observations, list)
    observations[-1]["symbol"] = observations[0]["symbol"]
    duplicate["observations"] = observations
    with pytest.raises(EvidenceValidationError, match="duplicate sector symbol"):
        parse_supplemental_evidence(
            [_breadth(), duplicate, _volatility(), _macro()], as_of=AS_OF
        )

    mismatched = _sector()
    observations = deepcopy(mismatched["observations"])
    assert isinstance(observations, list)
    observations[0]["sector"] = "technology"
    mismatched["observations"] = observations
    with pytest.raises(EvidenceValidationError, match="invalid sector identity"):
        parse_supplemental_evidence(
            [_breadth(), mismatched, _volatility(), _macro()], as_of=AS_OF
        )


def test_validates_breadth_internal_consistency_and_nonnegative_values() -> None:
    inconsistent = _breadth()
    inconsistent["advancing_issues"] = 301
    with pytest.raises(EvidenceValidationError, match="breadth issue counts are inconsistent"):
        parse_supplemental_evidence(
            [inconsistent, _sector(), _volatility(), _macro()], as_of=AS_OF
        )

    negative = _breadth()
    negative["down_volume"] = "-0.01"
    with pytest.raises(EvidenceValidationError, match="invalid breadth.down_volume"):
        parse_supplemental_evidence(
            [negative, _sector(), _volatility(), _macro()], as_of=AS_OF
        )


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", 1.5, True])
def test_rejects_nonfinite_or_non_string_decimal_values(value: object) -> None:
    volatility = _volatility()
    volatility["current_value"] = value

    with pytest.raises(EvidenceValidationError, match="invalid volatility.current_value"):
        parse_supplemental_evidence(
            [_breadth(), _sector(), volatility, _macro()], as_of=AS_OF
        )


def test_rejects_wrong_schema_strict_keys_and_missing_attribution() -> None:
    wrong_version = _breadth()
    wrong_version["schema_version"] = "scanner-evidence-v2"
    with pytest.raises(EvidenceValidationError, match="unsupported evidence schema"):
        parse_supplemental_evidence(
            [wrong_version, _sector(), _volatility(), _macro()], as_of=AS_OF
        )

    unknown = _breadth()
    unknown["extra"] = "not-declared"
    with pytest.raises(EvidenceValidationError, match="unexpected breadth field"):
        parse_supplemental_evidence(
            [unknown, _sector(), _volatility(), _macro()], as_of=AS_OF
        )

    missing_source = _macro()
    del missing_source["source"]
    with pytest.raises(EvidenceValidationError, match="invalid macro.source"):
        parse_supplemental_evidence(
            [_breadth(), _sector(), _volatility(), missing_source], as_of=AS_OF
        )


@pytest.mark.parametrize(
    "forbidden",
    [
        {"api_key": "never-log-this"},
        {"nested": {"authorization": "Bearer never-log-this"}},
        {"article_body": "full article text"},
        {"instruction_text": "run this command"},
        {"executable_content": "print('unsafe')"},
    ],
)
def test_rejects_sensitive_or_executable_content_without_echoing_it(
    forbidden: dict[str, object],
) -> None:
    catalyst = _catalyst()
    catalyst.update(forbidden)

    with pytest.raises(EvidenceValidationError) as caught:
        parse_supplemental_evidence(
            [_breadth(), _sector(), _volatility(), _macro(), catalyst], as_of=AS_OF
        )

    assert "never-log-this" not in str(caught.value)
    assert "full article text" not in str(caught.value)
    assert "run this command" not in str(caught.value)
    assert "print('unsafe')" not in str(caught.value)


def test_rejects_unbounded_strings_collections_and_record_counts() -> None:
    catalyst = _catalyst()
    catalyst["source_reference"] = "x" * 2049
    with pytest.raises(EvidenceValidationError, match="invalid catalyst.source_reference"):
        parse_supplemental_evidence(
            [_breadth(), _sector(), _volatility(), _macro(), catalyst], as_of=AS_OF
        )

    macro = _macro()
    macro["reason_codes"] = [f"reason-{index}" for index in range(33)]
    with pytest.raises(EvidenceValidationError, match="invalid macro.reason_codes"):
        parse_supplemental_evidence(
            [_breadth(), _sector(), _volatility(), macro], as_of=AS_OF
        )

    catalysts = [_catalyst(f"evidence-{index}", f"lineage-{index}") for index in range(997)]
    with pytest.raises(EvidenceValidationError, match="too many evidence records"):
        parse_supplemental_evidence(
            [_breadth(), _sector(), _volatility(), _macro(), *catalysts], as_of=AS_OF
        )


def test_rejects_duplicate_evidence_ids_but_preserves_lineage_conflicts() -> None:
    duplicate = _catalyst()
    with pytest.raises(EvidenceValidationError, match="duplicate catalyst evidence_id"):
        parse_supplemental_evidence(
            [_breadth(), _sector(), _volatility(), _macro(), duplicate, duplicate], as_of=AS_OF
        )

    positive = _catalyst("positive-1", "shared-lineage", "positive")
    negative = _catalyst("negative-1", "independent-lineage", "negative")
    result = parse_supplemental_evidence(
        [_breadth(), _sector(), _volatility(), _macro(), negative, positive], as_of=AS_OF
    )

    assert [item.direction for item in result.catalysts] == [
        CatalystDirection.NEGATIVE,
        CatalystDirection.POSITIVE,
    ]


def test_input_order_does_not_change_output_or_digest() -> None:
    first = _records() + [_catalyst("catalyst-2", "lineage-2", "negative")]
    second = list(reversed(deepcopy(first)))

    left = parse_supplemental_evidence(first, as_of=AS_OF)
    right = parse_supplemental_evidence(second, as_of=AS_OF)

    assert left == right
    assert stable_digest(left) == stable_digest(right)
