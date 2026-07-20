from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from market_trader.dashboard.models import (
    AnalyticsSummary,
    CandidateDetail,
    CandidateListItem,
    DashboardOverview,
    DataState,
    JournalEventSummary,
    RiskSummary,
    SourceSummary,
    WarningSummary,
)

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def test_dashboard_overview_sorts_sources_and_preserves_paper_state() -> None:
    overview = DashboardOverview(
        as_of=AS_OF,
        data_state=DataState.PARTIAL,
        paper_mode=True,
        market_state="entry_open",
        entry_allowed=True,
        sources=(
            SourceSummary(
                name="risk",
                state=DataState.READY,
                version="risk-policy-v1",
                observed_at=AS_OF,
                stable_key="risk:latest",
            ),
            SourceSummary(
                name="scanner",
                state=DataState.STALE,
                version="scanner-policy-v1",
                observed_at=AS_OF,
                stable_key="scanner:latest",
            ),
        ),
        warnings=(
            WarningSummary(
                code="scanner.stale",
                severity="warning",
                message="Scanner data is stale",
                source_keys=("scanner:latest",),
            ),
        ),
    )

    assert overview.paper_mode is True
    assert [source.name for source in overview.sources] == ["risk", "scanner"]
    assert overview.sources[1].state is DataState.STALE


def test_dashboard_models_require_aware_utc_timestamps() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        SourceSummary(
            name="market_data",
            state=DataState.READY,
            version="quotes-v1",
            observed_at=datetime(2026, 7, 20, 15, 30),
            stable_key="quote:aapl",
        )

    source = SourceSummary(
        name="market_data",
        state=DataState.READY,
        version="quotes-v1",
        observed_at=AS_OF,
        stable_key="quote:aapl",
    )

    assert source.observed_at == AS_OF


def test_warning_summaries_are_bounded_and_sort_source_keys() -> None:
    warning = WarningSummary(
        code="risk.blocked",
        severity="block",
        message="x" * 240,
        source_keys=("risk:2", "risk:1"),
    )

    assert warning.message == ("x" * 200)
    assert warning.source_keys == ("risk:1", "risk:2")


def test_candidate_list_item_carries_traceability_without_action_fields() -> None:
    candidate = CandidateListItem(
        candidate_key="candidate:aapl:2026-07-20",
        symbol="aapl",
        direction="bullish",
        strategy="bullish_breakout",
        score="87.50",
        qualification_state="qualified",
        catalyst_state="confirmed",
        risk_state="warning",
        data_state=DataState.READY,
        observed_at=AS_OF,
        reason_codes=("score.momentum", "catalyst.confirmed"),
        source_keys=("scanner:run:1", "risk:decision:1"),
    )

    payload = candidate.model_dump()

    assert candidate.symbol == "AAPL"
    assert candidate.reason_codes == ("catalyst.confirmed", "score.momentum")
    assert "order_payload" not in payload
    assert "approval" not in payload


def test_candidate_detail_links_downstream_sections() -> None:
    detail = CandidateDetail(
        candidate_key="candidate:aapl:2026-07-20",
        symbol="AAPL",
        data_state=DataState.PARTIAL,
        as_of=AS_OF,
        scanner={"score": "87.50", "policy_version": "scanner-policy-v1"},
        catalysts={"decision": "confirmed", "result_digest": "cat-digest"},
        options={"state": "unavailable"},
        risk={"status": "warning", "result_digest": "risk-digest"},
        sources=(
            SourceSummary(
                name="scanner",
                state=DataState.READY,
                version="scanner-policy-v1",
                observed_at=AS_OF,
                stable_key="scanner:run:1",
            ),
        ),
        warnings=(),
    )

    assert detail.options["state"] == "unavailable"
    assert detail.risk["result_digest"] == "risk-digest"


def test_secret_like_keys_are_rejected_from_display_payloads() -> None:
    with pytest.raises(ValidationError, match="secret-like"):
        CandidateDetail(
            candidate_key="candidate:aapl:2026-07-20",
            symbol="AAPL",
            data_state=DataState.READY,
            as_of=AS_OF,
            scanner={"score": "87.50", "api_key": "not-safe"},
            catalysts={},
            options={},
            risk={},
            sources=(),
            warnings=(),
        )

    with pytest.raises(ValidationError, match="secret-like"):
        JournalEventSummary(
            event_key="journal:1",
            event_type="risk_decision.recorded",
            occurred_at=AS_OF,
            correlation_id="corr:1",
            actor="system",
            source_key="risk:decision:1",
            payload_summary={"token": "not-safe"},
        )


def test_risk_journal_and_analytics_summaries_are_bounded_view_models() -> None:
    risk = RiskSummary(
        as_of=AS_OF,
        data_state=DataState.READY,
        latest_decision_key="risk:decision:1",
        status="blocked",
        checks=(
            WarningSummary(
                code="daily_loss",
                severity="block",
                message="Daily loss lock is active",
                source_keys=("lock:1",),
            ),
        ),
        active_locks=("manual_operator_hold", "daily_loss"),
        tax_disclaimer="Informational estimate only; not tax advice.",
        sources=(),
        warnings=(),
    )
    event = JournalEventSummary(
        event_key="journal:1",
        event_type="risk_decision.recorded",
        occurred_at=AS_OF,
        correlation_id="corr:1",
        actor="system",
        source_key="risk:decision:1",
        payload_summary={"status": "blocked"},
    )
    analytics = AnalyticsSummary(
        as_of=AS_OF,
        data_state=DataState.READY,
        candidate_counts={"qualified": 3, "blocked": 2},
        strategy_mix={"bullish_breakout": 2},
        block_reasons={"daily_loss": 1},
        stale_counts={"scanner": 1},
        risk_status_distribution={"blocked": 2, "warning": 1},
        sources=(),
        warnings=(),
    )

    assert risk.active_locks == ("daily_loss", "manual_operator_hold")
    assert event.payload_summary == {"status": "blocked"}
    assert analytics.candidate_counts["qualified"] == 3
