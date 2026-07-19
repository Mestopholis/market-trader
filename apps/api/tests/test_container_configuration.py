from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_api_container_runs_migrations_before_startup() -> None:
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()

    assert "COPY alembic.ini ./" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert "COPY fixtures ./fixtures" in dockerfile
    assert "USER appuser" in dockerfile
    assert "alembic upgrade head && exec uvicorn" in dockerfile


def test_api_container_packages_offline_scanner_assets_as_non_root() -> None:
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()

    assert "COPY config ./config" in dockerfile
    assert "COPY fixtures ./fixtures" in dockerfile
    assert "USER appuser" in dockerfile


def test_api_container_packages_offline_catalyst_assets_as_non_root() -> None:
    dockerfile = (Path(__file__).resolve().parents[1] / "Dockerfile").read_text()

    assert "COPY config ./config" in dockerfile
    assert "COPY fixtures ./fixtures" in dockerfile
    assert "USER appuser" in dockerfile


def test_migrations_use_the_configured_database_url() -> None:
    migration_environment = (
        Path(__file__).resolve().parents[1] / "migrations" / "env.py"
    ).read_text()

    assert 'os.getenv("MARKET_TRADER_DATABASE_URL")' in migration_environment


def test_compose_passes_the_display_timezone_to_the_api() -> None:
    compose = (REPOSITORY_ROOT / "compose.yaml").read_text()

    assert "MARKET_TRADER_DISPLAY_TIMEZONE" in compose
    assert "America/Chicago" in compose


def test_smoke_verification_checks_the_market_state_contract() -> None:
    verification_script = (
        REPOSITORY_ROOT / "scripts" / "verify-foundation.sh"
    ).read_text()

    assert "/api/market-state" in verification_script
    assert '"calendar"' in verification_script
    assert '"entry_allowed"' in verification_script
    assert "isinstance" in verification_script
    assert '"policy_version"' in verification_script
    assert '"calendar_timezone"' in verification_script
    assert '"display_timezone"' in verification_script
    assert '"trading_mode"' in verification_script
    assert "market_trader.market_data.cli validate" in verification_script
    assert "/app/fixtures/market_data/regular-session" in verification_script
    assert "market_trader.scanner.cli validate" in verification_script
    assert "/app/fixtures/scanner/bullish" in verification_script
    assert "SCHWAB" not in verification_script.upper()
    assert "PROVIDER_URL" not in verification_script.upper()


def test_smoke_verification_validates_catalysts_offline_without_sensitive_inputs() -> None:
    verification_script = (
        REPOSITORY_ROOT / "scripts" / "verify-foundation.sh"
    ).read_text()

    assert "market_trader.catalysts.cli validate" in verification_script
    assert (
        "/app/fixtures/catalysts/company-and-earnings" in verification_script
    )
    for prohibited in (
        "SEC_CONTACT",
        "SCHWAB",
        "FRED",
        "BEA",
        "NEWS_API",
        "SOCIAL_TOKEN",
        "MODEL_API",
        "ACCOUNT_ID",
        "APPROVAL_ID",
        "ORDER_ID",
    ):
        assert prohibited not in verification_script.upper()
