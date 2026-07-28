from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy.orm import Session

from market_trader.broker.schwab.client import SchwabClientError, SchwabClientState
from market_trader.broker.schwab.market_data import SchwabMarketDataProvider
from market_trader.domain.time import FrozenClock
from market_trader.market_data.models import CandleInterval, DataKind
from market_trader.market_data.normalizers import (
    normalize_candle,
    normalize_option_chain,
    normalize_quote,
)
from market_trader.market_data.providers import (
    CandleRequest,
    CorporateActionRequest,
    OptionChainRequest,
    ProviderHealthState,
    QuoteRequest,
    UnsupportedCapability,
)

NOW = datetime(2026, 7, 27, 16, 30, tzinfo=UTC)


def test_schwab_provider_returns_normalized_quote_events() -> None:
    provider = SchwabMarketDataProvider(
        client=FakeSchwabClient(
            {
                "/marketdata/v1/quotes": {
                    "SPY": {
                        "symbol": "SPY",
                        "quote": {
                            "bidPrice": 625.1,
                            "askPrice": 625.2,
                            "bidSize": 100,
                            "askSize": 200,
                            "lastPrice": 625.15,
                            "lastSize": 25,
                            "tradeTime": 1785171600000,
                        },
                    }
                }
            }
        ),
        session=FakeSession(),
        clock=FrozenClock(NOW),
    )

    events = provider.quotes(QuoteRequest(("SPY",)))

    assert isinstance(events, tuple)
    assert events[0].data_kind is DataKind.QUOTE
    quote = normalize_quote(events[0]).accepted
    assert quote is not None
    assert quote.symbol == "SPY"
    assert quote.bid == Decimal("625.1")


def test_schwab_provider_returns_candle_events() -> None:
    provider = SchwabMarketDataProvider(
        client=FakeSchwabClient(
            {
                "/marketdata/v1/pricehistory": {
                    "symbol": "SPY",
                    "candles": [
                        {
                            "datetime": int((NOW - timedelta(minutes=1)).timestamp() * 1000),
                            "open": 625.0,
                            "high": 625.5,
                            "low": 624.8,
                            "close": 625.2,
                            "volume": 1000,
                        }
                    ],
                }
            }
        ),
        session=FakeSession(),
        clock=FrozenClock(NOW),
    )

    events = provider.candles(
        CandleRequest(
            ("SPY",),
            CandleInterval.ONE_MINUTE.value,
            NOW - timedelta(minutes=1),
            NOW,
        )
    )

    assert isinstance(events, tuple)
    candle = normalize_candle(events[0]).accepted
    assert candle is not None
    assert candle.symbol == "SPY"
    assert candle.close == Decimal("625.2")


def test_schwab_provider_returns_option_chain_events() -> None:
    provider = SchwabMarketDataProvider(
        client=FakeSchwabClient(
            {
                "/marketdata/v1/chains": {
                    "symbol": "SPY",
                    "status": "SUCCESS",
                    "callExpDateMap": {
                        "2026-08-21:25": {
                            "630.0": [
                                {
                                    "symbol": "SPY_082126C00630000",
                                    "putCall": "CALL",
                                    "expirationDate": "2026-08-21T20:00:00+0000",
                                    "strikePrice": 630.0,
                                    "bid": 4.1,
                                    "ask": 4.2,
                                    "bidSize": 10,
                                    "askSize": 12,
                                    "nonStandard": False,
                                }
                            ]
                        }
                    },
                    "putExpDateMap": {},
                }
            }
        ),
        session=FakeSession(),
        clock=FrozenClock(NOW),
    )

    events = provider.option_chains(OptionChainRequest("SPY", date(2026, 8, 1), date(2026, 8, 31)))

    assert isinstance(events, tuple)
    chain = normalize_option_chain(events[0]).accepted
    assert chain is not None
    assert chain.contracts[0].contract_id == "SPY_082126C00630000"


def test_schwab_provider_marks_corporate_actions_unsupported() -> None:
    provider = SchwabMarketDataProvider(
        client=FakeSchwabClient({}),
        session=FakeSession(),
        clock=FrozenClock(NOW),
    )

    result = provider.corporate_actions(
        CorporateActionRequest("SPY", date(2026, 1, 1), date(2026, 12, 31))
    )

    assert isinstance(result, UnsupportedCapability)
    assert result.data_kind is DataKind.CORPORATE_ACTION


@pytest.mark.parametrize(
    ("state", "expected_health", "reason"),
    [
        (SchwabClientState.RATE_LIMITED, ProviderHealthState.DEGRADED, "schwab_rate_limited"),
        (SchwabClientState.UNAVAILABLE, ProviderHealthState.UNAVAILABLE, "schwab_unavailable"),
        (SchwabClientState.QUARANTINED, ProviderHealthState.DEGRADED, "schwab_quarantined"),
    ],
)
def test_schwab_provider_health_reflects_client_failures(
    state: SchwabClientState,
    expected_health: ProviderHealthState,
    reason: str,
) -> None:
    provider = SchwabMarketDataProvider(
        client=FakeSchwabClient({}, error_state=state),
        session=FakeSession(),
        clock=FrozenClock(NOW),
    )

    with pytest.raises(SchwabClientError):
        provider.quotes(QuoteRequest(("SPY",)))

    health = provider.health()
    assert health.state is expected_health
    assert health.reason_codes == (reason,)


def test_schwab_provider_reports_stale_event_health() -> None:
    provider = SchwabMarketDataProvider(
        client=FakeSchwabClient({}),
        session=FakeSession(),
        clock=FrozenClock(NOW),
        stale_after=timedelta(minutes=5),
    )
    provider.record_observation(NOW - timedelta(minutes=6))

    health = provider.health()

    assert health.state is ProviderHealthState.DEGRADED
    assert health.reason_codes == ("schwab_stale",)


class FakeSession(Session):
    pass


class FakeSchwabClient:
    def __init__(
        self,
        payloads: dict[str, dict[str, Any]],
        *,
        error_state: SchwabClientState | None = None,
    ) -> None:
        self.payloads = payloads
        self.error_state = error_state
        self.calls: list[tuple[str, dict[str, object] | None]] = []

    def get_json(
        self,
        _session: Session,
        path: str,
        *,
        correlation_id: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((path, params))
        if self.error_state is not None:
            raise SchwabClientError(
                code=f"schwab_{self.error_state.value}",
                state=self.error_state,
                diagnostics={"path": path},
            )
        return self.payloads[path]
