# Milestone 7: Risk, Sizing, Exposure, and Tax Warnings

Status: Complete  
Scope: deterministic offline risk decisions only

## What this milestone adds

Milestone 7 adds a pure risk domain that turns a scanner/share proposal or a defined-risk debit-spread proposal into a deterministic risk decision. It does not contact a broker, preview an order, place an order, or read live account balances.

The risk path covers:

- versioned risk policy loading from `apps/api/config/risk/risk-policy-v1.json`;
- immutable proposal, context, sizing, check, and decision contracts;
- share and debit-spread integer sizing;
- settled-cash, unsettled-cash, reserved-risk, position-count, trade-count, loss, drawdown, and correlation checks;
- active risk-lock blocking and informational lock warnings;
- taxable-account wash-sale and holding-period warnings with non-advice language;
- append-only persistence for risk decisions, checks, and reservations;
- deterministic risk fixtures, replay, and CLI validation.

## Local setup

From `apps/api`:

```bash
.venv/bin/python -m pip install -e '.[dev]'
```

Validate all checked-in risk fixtures:

```bash
.venv/bin/python -m pytest tests/risk -q
```

Validate one fixture through the CLI:

```bash
.venv/bin/python -m market_trader.risk.cli validate fixtures/risk/share-sizing-boundaries/approved-share.json
```

Evaluate one fixture:

```bash
.venv/bin/python -m market_trader.risk.cli evaluate fixtures/risk/share-sizing-boundaries/approved-share.json
```

## Fixture groups

Checked-in fixtures live under `apps/api/fixtures/risk`:

- `share-sizing-boundaries`
- `spread-sizing-boundaries`
- `portfolio-limits-and-locks`
- `settlement-and-tax-warnings`

Regenerate fixtures from `apps/api`:

```bash
.venv/bin/python scripts/generate_risk_fixtures.py
```

After regeneration, run:

```bash
.venv/bin/pytest tests/risk/test_fixture_conformance.py -q
```

## Persistence notes

Risk persistence is append-only:

- `risk_decisions`
- `risk_checks`
- `risk_reservations`

SQLite migrations install no-update and no-delete triggers for these tables. Repository writes are idempotent for exact reruns and conflict if a stable key is reused with a different digest. Audit events are emitted for:

- `risk_decision.recorded`
- `risk_check.recorded`
- `risk_reservation.recorded`

## Lock meanings

Required active locks block the decision. The v1 policy requires:

- `daily_loss`
- `weekly_loss`
- `drawdown`
- `manual`

Informational locks produce warnings rather than approval-ready blocks. The v1 policy includes `catalyst_warning` as informational.

## Tax-warning disclaimer

Tax checks are educational warnings only. They are not tax advice, do not calculate a final tax liability, and do not replace review by a qualified tax professional.

## Explicit non-capabilities

Milestone 7 does not implement:

- Schwab authentication;
- broker account balance reads;
- broker buying-power reads;
- broker order previews;
- approval actions;
- paper or live order submission;
- margin calculations;
- tax advice.
