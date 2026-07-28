from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from market_trader.broker.schwab.normalizers import (
    normalize_schwab_option_chain,
    normalize_schwab_quotes,
)
from market_trader.market_data.models import DataKind, QualityState
from market_trader.market_data.normalizers import normalize_option_chain, normalize_quote

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "fixtures" / "schwab_read_only"
OBSERVED = datetime(2026, 7, 27, 16, 0, tzinfo=UTC)


def test_normalizes_schwab_quotes_fixture_to_project_quote_events() -> None:
    events = normalize_schwab_quotes(
        _fixture("quotes.json"),
        observed_at=OBSERVED,
        ingested_at=OBSERVED,
        correlation_id="corr-quotes",
    )

    assert len(events) == 2
    assert events[0].source == "schwab"
    assert events[0].data_kind is DataKind.QUOTE
    assert "account" not in repr(events[0].payload).lower()

    quote = normalize_quote(events[0]).accepted
    assert quote is not None
    assert quote.symbol == "SPY"
    assert quote.bid == Decimal("625.10")
    assert quote.ask == Decimal("625.20")
    assert quote.metadata.quality_state is QualityState.VALID


def test_normalizes_schwab_option_chain_fixture_to_project_chain_event() -> None:
    event = normalize_schwab_option_chain(
        _fixture("option-chain.json"),
        observed_at=OBSERVED,
        ingested_at=OBSERVED,
        correlation_id="corr-chain",
    )

    assert event.source == "schwab"
    assert event.data_kind is DataKind.OPTION_CHAIN
    chain = normalize_option_chain(event).accepted
    assert chain is not None
    assert chain.underlying == "SPY"
    assert chain.contracts[0].contract_id == "SPY_082126C00630000"
    assert chain.contracts[0].strike == Decimal("630.0")
    assert chain.metadata.quality_state is QualityState.VALID


def test_normalizers_reject_non_mapping_payloads() -> None:
    quote_events = normalize_schwab_quotes([], observed_at=OBSERVED, ingested_at=OBSERVED)
    chain_event = normalize_schwab_option_chain([], observed_at=OBSERVED, ingested_at=OBSERVED)

    assert quote_events == ()
    assert chain_event.payload["contracts"] == []


def _fixture(name: str) -> object:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))
