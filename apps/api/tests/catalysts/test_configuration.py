import json
from decimal import Decimal
from pathlib import Path
from shutil import copytree

import pytest

from market_trader.catalysts.configuration import load_catalyst_configuration
from market_trader.catalysts.models import CatalystDirection, Materiality

API_ROOT = Path(__file__).parents[2]
CONFIGURATION = API_ROOT / "config" / "catalysts"

COMPANY_CIKS = {
    "AAPL": "0000320193",
    "AMD": "0000002488",
    "AMZN": "0001018724",
    "AVGO": "0001730168",
    "COST": "0000909832",
    "GOOGL": "0001652044",
    "JPM": "0000019617",
    "LLY": "0000059478",
    "META": "0001326801",
    "MSFT": "0000789019",
    "NVDA": "0001045810",
    "TSLA": "0001318605",
    "UNH": "0000731766",
    "WMT": "0000104169",
    "XOM": "0000034088",
}
FUND_SYMBOLS = (
    "DIA",
    "IWM",
    "QQQ",
    "SPY",
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
)


def test_loads_exact_versioned_source_policy() -> None:
    configuration = load_catalyst_configuration(CONFIGURATION)

    assert configuration.sources.version == "catalyst-source-policy-v1"
    assert tuple(configuration.sources.by_id) == (
        "bls-public-v1",
        "recorded-company-news-v1",
        "recorded-earnings-v1",
        "recorded-macro-v1",
        "recorded-social-v1",
        "recorded-summary-v1",
        "sec-edgar-public-v1",
    )
    sec = configuration.sources.by_id["sec-edgar-public-v1"]
    assert sec.origins == ("https://data.sec.gov",)
    assert sec.max_requests == 5
    assert sec.rate_period_seconds == 1
    assert sec.max_response_bytes == 10 * 1024 * 1024
    assert sec.allow_redirects is False
    bls = configuration.sources.by_id["bls-public-v1"]
    assert bls.origins == ("https://api.bls.gov", "https://www.bls.gov")
    assert bls.max_requests == 5
    assert bls.rate_period_seconds == 60
    assert bls.daily_request_limit == 20
    assert bls.max_response_bytes == 2 * 1024 * 1024
    assert bls.allow_redirects is False


def test_configures_exact_company_and_macro_identity() -> None:
    sources = load_catalyst_configuration(CONFIGURATION).sources

    assert dict(sources.company_ciks) == COMPANY_CIKS
    assert sources.unsupported_fund_symbols == FUND_SYMBOLS
    assert dict(sources.bls_series) == {
        "consumer_price_index": "CUSR0000SA0",
        "total_nonfarm_payrolls": "CES0000000001",
        "unemployment_rate": "LNS14000000",
    }


def test_loads_exact_classification_risk_and_summary_policy() -> None:
    configuration = load_catalyst_configuration(CONFIGURATION)

    assert configuration.classification.version == "catalyst-classification-policy-v1"
    assert configuration.classification.earnings_surprise_threshold == Decimal("2.000000")
    assert configuration.classification.social_freshness_minutes == 30
    assert configuration.classification.categories["regulatory_approval"] == (
        Materiality.MATERIAL,
        CatalystDirection.POSITIVE,
    )
    assert configuration.classification.categories["cyber_incident"] == (
        Materiality.MATERIAL,
        CatalystDirection.UNCLEAR,
    )
    assert configuration.risk.version == "event-risk-policy-v1"
    assert configuration.risk.earnings_sessions_before == 2
    assert configuration.risk.require_full_session_after is True
    assert configuration.risk.macro_minutes_before == 60
    assert configuration.risk.macro_minutes_after == 30
    assert configuration.risk.high_impact_macro == (
        "consumer_price_index",
        "employment_situation",
        "fomc_rate_decision",
    )
    assert configuration.summary.version == "catalyst-summary-policy-v1"
    assert configuration.summary.max_text_characters == 2_048
    assert configuration.summary.require_segment_citations is True
    assert set(configuration.content_hashes) == {
        "classification",
        "risk",
        "sources",
        "summary",
    }


def _copied_configuration(tmp_path: Path) -> Path:
    target = tmp_path / "catalysts"
    copytree(CONFIGURATION, target)
    return target


def _rewrite(path: Path, update: object) -> None:
    payload = json.loads(path.read_text())
    assert isinstance(payload, dict)
    if callable(update):
        update(payload)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")


def test_rejects_unknown_keys_before_hash_validation(tmp_path: Path) -> None:
    target = _copied_configuration(tmp_path)
    path = target / "event-risk-policy-v1.json"
    _rewrite(path, lambda payload: payload.update({"unknown": True}))

    with pytest.raises(ValueError, match="unknown keys"):
        load_catalyst_configuration(target)


def test_rejects_json_numeric_decimal_values(tmp_path: Path) -> None:
    target = _copied_configuration(tmp_path)
    path = target / "catalyst-classification-policy-v1.json"
    _rewrite(path, lambda payload: payload.update({"earnings_surprise_threshold": 2.0}))

    with pytest.raises(ValueError, match="decimal.*string"):
        load_catalyst_configuration(target)


def test_rejects_content_hash_drift(tmp_path: Path) -> None:
    target = _copied_configuration(tmp_path)
    path = target / "event-risk-policy-v1.json"
    _rewrite(path, lambda payload: payload.update({"macro_minutes_before": 59}))

    with pytest.raises(ValueError, match="content hash"):
        load_catalyst_configuration(target)


@pytest.mark.parametrize(
    ("filename", "field", "value", "message"),
    [
        ("catalyst-source-policy-v1.json", "version", "v2", "version"),
        ("event-risk-policy-v1.json", "earnings_sessions_before", 1, "content hash"),
        ("catalyst-summary-policy-v1.json", "max_text_characters", 4096, "content hash"),
    ],
)
def test_rejects_unapproved_policy_changes(
    tmp_path: Path,
    filename: str,
    field: str,
    value: object,
    message: str,
) -> None:
    target = _copied_configuration(tmp_path)
    path = target / filename
    _rewrite(path, lambda payload: payload.update({field: value}))

    with pytest.raises(ValueError, match=message):
        load_catalyst_configuration(target)
