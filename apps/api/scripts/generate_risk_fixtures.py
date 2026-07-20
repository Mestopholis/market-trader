from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from market_trader.risk.configuration import load_risk_policy
from market_trader.risk.engine import RiskEngine
from market_trader.risk.models import (
    BuyingPowerSnapshot,
    ClosedTradeLot,
    DebitSpreadProposal,
    PortfolioPosition,
    RiskInput,
    RiskLockSnapshot,
    ShareProposal,
)
from market_trader.risk.serialization import canonical_record

AS_OF = datetime(2026, 7, 20, 15, 30, tzinfo=UTC)
POLICY_PATH = Path("config/risk/risk-policy-v1.json")


def main() -> int:
    policy = load_risk_policy(POLICY_PATH)
    fixtures = {
        "share-sizing-boundaries/approved-share.json": _fixture(
            "fixture:risk:approved-share",
            "share-sizing-boundaries",
            "approved share boundary",
            _base_input(policy.content_hash),
            policy,
        ),
        "spread-sizing-boundaries/approved-spread.json": _fixture(
            "fixture:risk:approved-spread",
            "spread-sizing-boundaries",
            "approved one-contract spread",
            _base_input(
                policy.content_hash,
                proposal=DebitSpreadProposal(
                    proposal_key="proposal:spread:spy",
                    symbol="SPY",
                    long_contract_id="SPY260918C00490000",
                    short_contract_id="SPY260918C00500000",
                    expiration=AS_OF,
                    debit=Decimal("2.50"),
                    maximum_loss=Decimal("0.50"),
                    short_strike=Decimal("500.00"),
                ),
                settled_cash=Decimal("5000.00"),
                account_equity=Decimal("5000.00"),
            ),
            policy,
        ),
        "portfolio-limits-and-locks/blocked-lock.json": _fixture(
            "fixture:risk:blocked-lock",
            "portfolio-limits-and-locks",
            "blocked by daily loss lock",
            _base_input(
                policy.content_hash,
                locks=(
                    RiskLockSnapshot(
                        lock_id="lock:daily-loss",
                        lock_type="daily_loss",
                        status="active",
                        reason="daily loss limit hit",
                        activated_at=AS_OF,
                        source_event_id="event:daily-loss",
                    ),
                ),
            ),
            policy,
        ),
        "settlement-and-tax-warnings/wash-sale-warning.json": _fixture(
            "fixture:risk:wash-sale-warning",
            "settlement-and-tax-warnings",
            "wash-sale warning",
            _base_input(
                policy.content_hash,
                closed_trade_lots=(
                    ClosedTradeLot(
                        lot_key="closed:aapl-loss",
                        symbol="AAPL",
                        closed_at=AS_OF - timedelta(days=5),
                        quantity=1,
                        realized_pl=Decimal("-10.00"),
                        loss_amount=Decimal("10.00"),
                        account_taxable=True,
                    ),
                ),
            ),
            policy,
        ),
    }
    root = Path("fixtures/risk")
    for relative, payload in fixtures.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


def _fixture(
    fixture_key: str,
    group: str,
    case_name: str,
    risk_input: RiskInput,
    policy: object,
) -> dict[str, object]:
    decision = RiskEngine().evaluate(risk_input, policy)  # type: ignore[arg-type]
    payload = {
        "schema_version": 1,
        "fixture_key": fixture_key,
        "group": group,
        "case_name": case_name,
        "content_hash": "",
        "policy_path": str(POLICY_PATH),
        "input": canonical_record(risk_input),
        "expected_status": decision.status.value,
    }
    payload["content_hash"] = _content_hash(payload)
    return payload


def _base_input(
    policy_hash: str,
    *,
    proposal: ShareProposal | DebitSpreadProposal | None = None,
    settled_cash: Decimal = Decimal("10000.00"),
    account_equity: Decimal = Decimal("10000.00"),
    locks: tuple[RiskLockSnapshot, ...] = (),
    closed_trade_lots: tuple[ClosedTradeLot, ...] = (),
) -> RiskInput:
    return RiskInput(
        decision_key="risk:fixture:" + (proposal.proposal_key if proposal else "approved-share"),
        proposal=proposal
        if proposal is not None
        else ShareProposal(
            proposal_key="proposal:shares:aapl",
            symbol="AAPL",
            entry_price=Decimal("100.00"),
            stop_price=Decimal("95.00"),
            direction="long",
        ),
        buying_power=BuyingPowerSnapshot(
            settled_cash=settled_cash,
            unsettled_cash=Decimal("0.00"),
            reserved_cash=Decimal("0.00"),
            observed_at=AS_OF,
            snapshot_digest="bp-digest",
        ),
        positions=(
            PortfolioPosition(
                position_key="position:seed",
                symbol="MSFT",
                quantity=1,
                market_value=Decimal("100.00"),
                maximum_loss=Decimal("5.00"),
                correlation_group="other",
            ),
        ),
        working_orders=(),
        locks=locks,
        open_tax_lots=(),
        closed_trade_lots=closed_trade_lots,
        policy_version="risk-policy-v1",
        policy_hash=policy_hash,
        as_of=AS_OF,
        account_equity=account_equity,
    )


def _content_hash(raw: dict[str, object]) -> str:
    payload = dict(raw)
    payload.pop("content_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
