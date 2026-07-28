from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_trader.api import broker as broker_api
from market_trader.api.auth import require_authenticated_session, require_csrf_protection
from market_trader.broker.schwab.live_data import (
    SchwabLiveMarketDataIngestionResult,
    SchwabLiveMarketDataIngestionService,
)
from market_trader.broker.schwab.market_data import SchwabMarketDataProvider
from market_trader.config import get_settings
from market_trader.db.engine import create_engine_from_url
from market_trader.db.models import (
    JournalEventORM,
    MarketDataSnapshotORM,
    SchwabMarketDataSyncORM,
    SymbolORM,
)
from market_trader.domain.time import FrozenClock
from market_trader.main import create_app
from market_trader.repositories.symbols import SymbolCreate, SymbolRepository
from market_trader.scanner.configuration import load_scanner_configuration
from market_trader.scanner.live_scan import SchwabLiveScanResult
from market_trader.security.csrf import CSRF_HEADER_NAME
from market_trader.security.session import SessionClaims
from tests.db_helpers import migrated_engine

NOW = datetime(2026, 7, 28, 15, 30, tzinfo=UTC)
CONFIGURATION_PATH = Path("config/scanner")


@pytest.fixture(autouse=True)
def clear_broker_caches() -> Iterator[None]:
    get_settings.cache_clear()
    broker_api._engine.cache_clear()
    yield
    get_settings.cache_clear()
    broker_api._engine.cache_clear()


def test_refresh_quotes_persists_schwab_snapshots_and_sync_status(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)
    try:
        with Session(engine) as session, session.begin():
            _create_symbol(session, "SPY")
            service = SchwabLiveMarketDataIngestionService(
                provider=SchwabMarketDataProvider(
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
                                        "tradeTime": int(NOW.timestamp() * 1000),
                                    },
                                }
                            }
                        }
                    ),
                    session=session,
                    clock=FrozenClock(NOW),
                ),
                clock=FrozenClock(NOW),
            )

            result = service.refresh_quotes(
                session,
                symbols=("SPY",),
                correlation_id="corr-live-quotes",
            )

        with Session(engine) as session:
            snapshots = session.scalars(select(MarketDataSnapshotORM)).all()
            sync = session.scalar(select(SchwabMarketDataSyncORM))
            event_types = session.scalars(
                select(JournalEventORM.event_type).order_by(JournalEventORM.event_type)
            ).all()

        assert result.accepted == 1
        assert result.quarantined == 0
        assert result.provider_state == "available"
        assert result.symbols == ("SPY",)
        assert len(snapshots) == 1
        assert snapshots[0].source == "schwab"
        assert snapshots[0].data_kind == "quote"
        assert snapshots[0].payload["symbol"] == "SPY"
        assert sync is not None
        assert sync.sync_key == "schwab:quote:SPY"
        assert sync.status == "completed"
        assert sync.provider_state == "available"
        assert sync.observed_at is not None
        assert sync.observed_at.replace(tzinfo=UTC) == NOW
        assert "market_data_snapshot.stored" in event_types
    finally:
        engine.dispose()


def test_broker_api_refreshes_live_schwab_quotes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("MARKET_TRADER_DATABASE_URL", database_url)
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_MARKET_DATA_ENABLED", "true")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY", "synthetic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[require_authenticated_session] = lambda: SessionClaims(
        username="operator",
        issued_at=NOW,
    )
    app.dependency_overrides[require_csrf_protection] = lambda: None
    from market_trader.api.broker import get_schwab_live_market_data_service

    fake = FakeLiveMarketDataService()
    app.dependency_overrides[get_schwab_live_market_data_service] = lambda: fake

    response = TestClient(app, base_url="https://testserver").post(
        "/api/broker/schwab/market-data/quotes/refresh",
        json={"symbols": ["spy", "AAPL"]},
        headers={CSRF_HEADER_NAME: "csrf", "X-Correlation-ID": "corr-live-api"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "accepted": 2,
        "data_kind": "quote",
        "deduplicated": 0,
        "degraded": 0,
        "provider_state": "available",
        "quarantined": 0,
        "stale": 0,
        "symbols": ["SPY", "AAPL"],
        "sync_key": "schwab:quote:AAPL,SPY",
    }
    assert fake.calls == [(("SPY", "AAPL"), "corr-live-api")]


def test_broker_api_runs_live_schwab_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'api-scan.db'}"
    monkeypatch.setenv("MARKET_TRADER_DATABASE_URL", database_url)
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_MARKET_DATA_ENABLED", "true")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY", "synthetic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[require_authenticated_session] = lambda: SessionClaims(
        username="operator",
        issued_at=NOW,
    )
    app.dependency_overrides[require_csrf_protection] = lambda: None
    from market_trader.api.broker import get_schwab_live_scanner_service

    fake = FakeLiveScannerService()
    app.dependency_overrides[get_schwab_live_scanner_service] = lambda: fake

    response = TestClient(app, base_url="https://testserver").post(
        "/api/broker/schwab/market-data/scan-live",
        json={
            "source": "schwab",
            "as_of": NOW.isoformat(),
            "observed_lookback_minutes": 15,
            "refresh_quotes": False,
        },
        headers={CSRF_HEADER_NAME: "csrf", "X-Correlation-ID": "corr-live-scan-api"},
    )

    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json() == {
        "source": "schwab",
        "run_key": "scan:live:test",
        "result_digest": "digest-live-test",
        "counts": {
            "eligible": 1,
            "ineligible": 28,
            "blocked": 1,
            "signals": 5,
            "candidates": 2,
        },
    }
    assert fake.calls == [("schwab", NOW, 15, "corr-live-scan-api")]


def test_broker_api_refreshes_universe_quotes_before_live_schwab_scan(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = migrated_engine(tmp_path, filename="api-scan-universe.db")
    database_url = str(engine.url)
    engine.dispose()
    monkeypatch.setenv("MARKET_TRADER_DATABASE_URL", database_url)
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_MARKET_DATA_ENABLED", "true")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_CLIENT_SECRET", "synthetic-secret")
    monkeypatch.setenv("MARKET_TRADER_SCHWAB_TOKEN_ENCRYPTION_KEY", "synthetic-key")
    get_settings.cache_clear()

    app = create_app()
    app.dependency_overrides[require_authenticated_session] = lambda: SessionClaims(
        username="operator",
        issued_at=NOW,
    )
    app.dependency_overrides[require_csrf_protection] = lambda: None
    from market_trader.api.broker import (
        get_schwab_live_market_data_service,
        get_schwab_live_scanner_service,
    )

    fake_quotes = FakeLiveMarketDataService()
    fake_scan = FakeLiveScannerService()
    app.dependency_overrides[get_schwab_live_market_data_service] = lambda: fake_quotes
    app.dependency_overrides[get_schwab_live_scanner_service] = lambda: fake_scan

    response = TestClient(app, base_url="https://testserver").post(
        "/api/broker/schwab/market-data/scan-live",
        json={
            "source": "schwab",
            "as_of": NOW.isoformat(),
            "observed_lookback_minutes": 15,
            "refresh_quotes": True,
        },
        headers={CSRF_HEADER_NAME: "csrf", "X-Correlation-ID": "corr-live-universe"},
    )

    assert response.status_code == 200
    assert fake_quotes.calls == [
        (
            (
                "SPY",
                "QQQ",
                "IWM",
                "DIA",
                "XLB",
                "XLC",
                "XLE",
                "XLF",
                "XLI",
                "XLK",
                "XLP",
                "XLRE",
                "XLU",
                "XLV",
                "XLY",
                "AAPL",
                "MSFT",
                "NVDA",
                "AMZN",
                "META",
                "GOOGL",
                "TSLA",
                "AMD",
                "AVGO",
                "JPM",
                "XOM",
                "UNH",
                "LLY",
                "WMT",
                "COST",
            ),
            "corr-live-universe",
        )
    ]
    assert fake_scan.calls == [("schwab", NOW, 15, "corr-live-universe")]
    engine = create_engine_from_url(database_url)
    try:
        with Session(engine) as session:
            stored_symbols = session.scalars(select(SymbolORM.display_symbol)).all()
    finally:
        engine.dispose()
    assert set(stored_symbols) == set(fake_scan.universe_symbols)


class FakeSchwabClient:
    def __init__(self, payloads: dict[str, dict[str, Any]]) -> None:
        self.payloads = payloads

    def get_json(
        self,
        _session: Session,
        path: str,
        *,
        correlation_id: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        assert correlation_id == "schwab-quotes"
        assert params == {"symbols": "SPY"}
        return self.payloads[path]


class FakeLiveMarketDataService:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str]] = []

    def refresh_quotes(
        self,
        _session: Session,
        *,
        symbols: tuple[str, ...],
        correlation_id: str,
    ) -> SchwabLiveMarketDataIngestionResult:
        self.calls.append((symbols, correlation_id))
        return SchwabLiveMarketDataIngestionResult(
            sync_key="schwab:quote:AAPL,SPY",
            data_kind="quote",
            symbols=symbols,
            provider_state="available",
            accepted=2,
            degraded=0,
            stale=0,
            quarantined=0,
            deduplicated=0,
        )


class FakeLiveScannerService:
    def __init__(self) -> None:
        self.configuration = load_scanner_configuration(CONFIGURATION_PATH)
        self.universe_symbols = tuple(
            entry.display_symbol for entry in self.configuration.universe.entries
        )
        self.calls: list[tuple[str, datetime, int, str]] = []

    def scan(
        self,
        session: Session,
        *,
        source: str,
        as_of: datetime,
        observed_lookback_minutes: int,
        correlation_id: str,
    ) -> SchwabLiveScanResult:
        assert isinstance(session, Session)
        self.calls.append((source, as_of, observed_lookback_minutes, correlation_id))
        return SchwabLiveScanResult(
            source=source,
            run_key="scan:live:test",
            result_digest="digest-live-test",
            counts={
                "eligible": 1,
                "ineligible": 28,
                "blocked": 1,
                "signals": 5,
                "candidates": 2,
            },
        )


def _create_symbol(session: Session, display_symbol: str) -> None:
    SymbolRepository(session).create_symbol(
        SymbolCreate(
            display_symbol=display_symbol,
            instrument_type="equity",
            exchange="ARCX",
            is_active=True,
            first_observed_at=NOW,
            last_observed_at=NOW,
            metadata_payload={"schema_version": 1},
            metadata_schema_version=1,
            correlation_id="corr-symbol",
        )
    )
