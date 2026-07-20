import hashlib
import json
from collections.abc import MutableMapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from market_trader.risk.fixtures import RiskFixtureError, load_risk_fixture
from market_trader.risk.models import (
    BuyingPowerSnapshot,
    RiskDecisionStatus,
    RiskInput,
    ShareProposal,
)
from market_trader.risk.serialization import canonical_record

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)


def test_loads_strict_fixture_with_expected_status(tmp_path: Path) -> None:
    path = _write_fixture(tmp_path, _risk_input(), expected_status="approved")

    fixture = load_risk_fixture(path)

    assert fixture.fixture_key == "fixture:test"
    assert fixture.expected_status is RiskDecisionStatus.APPROVED
    assert fixture.risk_input.decision_key == "risk:fixture"


def test_fixture_rejects_unknown_keys_bad_hash_and_sensitive_keys(tmp_path: Path) -> None:
    raw = _fixture_payload(_risk_input(), expected_status="approved")
    raw["unknown"] = True
    path = _write_raw(tmp_path, raw)
    with pytest.raises(RiskFixtureError, match="unknown fixture keys"):
        load_risk_fixture(path)

    raw = _fixture_payload(_risk_input(), expected_status="approved")
    raw["content_hash"] = "bad"
    path = tmp_path / "bad-hash.json"
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    with pytest.raises(RiskFixtureError, match="content hash"):
        load_risk_fixture(path)

    raw = _fixture_payload(_risk_input(), expected_status="approved")
    raw["input"]["broker_token"] = "secret"  # type: ignore[index]
    path = _write_raw(tmp_path, raw)
    with pytest.raises(RiskFixtureError, match="sensitive"):
        load_risk_fixture(path)


def _risk_input() -> RiskInput:
    return RiskInput(
        decision_key="risk:fixture",
        proposal=ShareProposal(
            proposal_key="proposal:fixture",
            symbol="AAPL",
            entry_price=Decimal("100.00"),
            stop_price=Decimal("95.00"),
            direction="long",
        ),
        buying_power=BuyingPowerSnapshot(
            settled_cash=Decimal("10000.00"),
            unsettled_cash=Decimal("0.00"),
            reserved_cash=Decimal("0.00"),
            observed_at=AS_OF,
            snapshot_digest="bp-digest",
        ),
        positions=(),
        working_orders=(),
        locks=(),
        open_tax_lots=(),
        closed_trade_lots=(),
        policy_version="risk-policy-v1",
        policy_hash="policy-hash",
        as_of=AS_OF,
        account_equity=Decimal("10000.00"),
    )


def _write_fixture(tmp_path: Path, risk_input: RiskInput, *, expected_status: str) -> Path:
    return _write_raw(tmp_path, _fixture_payload(risk_input, expected_status=expected_status))


def _fixture_payload(risk_input: RiskInput, *, expected_status: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "fixture_key": "fixture:test",
        "group": "share-sizing-boundaries",
        "case_name": "test fixture",
        "content_hash": "",
        "policy_path": "config/risk/risk-policy-v1.json",
        "input": canonical_record(risk_input),
        "expected_status": expected_status,
    }


def _write_raw(tmp_path: Path, raw: MutableMapping[str, object]) -> Path:
    raw["content_hash"] = _content_hash(raw)
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(raw, sort_keys=True), encoding="utf-8")
    return path


def _content_hash(raw: MutableMapping[str, object]) -> str:
    payload = dict(raw)
    payload.pop("content_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
