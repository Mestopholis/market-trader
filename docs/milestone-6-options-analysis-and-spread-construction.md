# Milestone 6 Options Analysis And Spread Construction

Milestone 6 adds deterministic standard-contract validation, defined-risk bull
call and bear put debit-spread construction, warning evaluation, offline
fixtures, replay, CLI validation, and append-only persistence.

The application remains paper-only. This milestone contains no Schwab client,
broker preview, sizing, approval action, order intent, order submission, naked
options, credit spreads, or 0DTE behavior.

## Backend Setup

Python 3.12 or 3.13 is supported on macOS and Linux. From the repository root:

```bash
cd apps/api
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

All persisted timestamps are aware UTC. Market-time rules use XNYS sessions.
Display examples may use `America/Chicago`, but rule evaluation must not use
fixed UTC offsets as a substitute for named timezones.

## Offline Validation And Analysis

Validate a production fixture and its stream hashes, record counts, policy hash,
reason summary, and frozen result digest:

```bash
cd apps/api
./.venv/bin/python -m market_trader.options_analysis.cli validate \
  fixtures/options_analysis/bull-call-qualified
```

Analyze the same fixture in memory:

```bash
./.venv/bin/python -m market_trader.options_analysis.cli analyze \
  fixtures/options_analysis/bull-call-qualified
```

The four production groups are `bull-call-qualified`, `bear-put-qualified`,
`contract-boundaries`, and `risk-warnings`. Commands print one compact, sorted
JSON object. Exit `2` means fixture validation failed, and exit `3` means an
infrastructure failure. Offline validation and analysis do not use credentials,
network access, account data, approvals, or orders.

## Persistence Behavior

Options-analysis persistence is append-only and idempotent. The repository
resolves the scanner run, qualified candidate, and symbol lineage before writing.
It records the run, contract evaluations, spread candidates, spread warnings, and
audit events in one transaction scope without committing on behalf of the caller.

An exact rerun returns the existing run without duplicate children or audit
events. A changed digest for the same run key raises a conflict. Missing lineage,
nonqualified candidates, candidate/symbol mismatch, or child-record failure rolls
back the complete persist attempt.

The schema tables are:

- `options_analysis_runs`
- `option_contract_evaluations`
- `option_spread_candidates`
- `option_spread_warnings`

Representative read-only inspection queries:

```bash
sqlite3 data/milestone6.db \
  'SELECT run_key, input_digest, result_digest, policy_version, as_of FROM options_analysis_runs;'

sqlite3 data/milestone6.db \
  'SELECT contract_id, state, reasons FROM option_contract_evaluations ORDER BY contract_id;'

sqlite3 data/milestone6.db \
  'SELECT strategy, long_contract_id, short_contract_id, blocked FROM option_spread_candidates;'

sqlite3 data/milestone6.db \
  "SELECT event_type, COUNT(*) FROM journal_events WHERE event_type LIKE 'option_%' OR event_type = 'options_analysis_run.recorded' GROUP BY event_type;"
```

## Policy And Fixture Changes

The options-analysis policy lives in
`apps/api/config/options_analysis/options-analysis-policy-v1.json`. Its content
hash is part of fixture validation and run identity. To change a rule:

1. Change only the reviewed rule and assign its reviewed version.
2. Recalculate the canonical content hash in the policy file.
3. Regenerate fixtures with:

   ```bash
   cd apps/api
   ./.venv/bin/python scripts/generate_options_analysis_fixtures.py
   ```

4. Review the fixture manifests, stream hashes, counts, reason summaries, and
   result digests.
5. Run `./.venv/bin/pytest tests/options_analysis -q` before committing.

Fixtures must stay synthetic and bounded by their explicit `as_of`. Never include
authorization headers, cookies, secrets, tokens, account data, real customer
data, approval data, or order data.

## Container Verification

From the repository root:

```bash
cp .env.example .env
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose down
```

The API image packages `/app/config/options_analysis` and
`/app/fixtures/options_analysis`. The smoke script validates the
`bull-call-qualified` fixture offline. It does not require Schwab, provider,
account, approval, or order credentials.
