#!/usr/bin/env bash
set -euo pipefail

base_url="${MARKET_TRADER_URL:-http://127.0.0.1:8080}"
health="$(curl --fail --silent --show-error "${base_url}/api/health")"

test "$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["trading_mode"])')" = "paper"
database="$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("database", ""))')"
test -z "$database" || test "$database" = "ok"

market_state="$(curl --fail --silent --show-error "${base_url}/api/market-state")"
printf '%s' "$market_state" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["calendar"] == "XNYS"
assert isinstance(payload["entry_allowed"], bool)
assert payload["policy_version"]
assert payload["calendar_timezone"] == "America/New_York"
assert payload["display_timezone"] == "America/Chicago"
'

curl --fail --silent --show-error "$base_url/" | grep -q '<div id="root"></div>'

docker compose exec -T api \
  python -m market_trader.market_data.cli validate \
  /app/fixtures/market_data/regular-session >/dev/null

docker compose exec -T api \
  python -m market_trader.scanner.cli validate \
  /app/fixtures/scanner/bullish >/dev/null

docker compose exec -T api \
  python -m market_trader.catalysts.cli validate \
  /app/fixtures/catalysts/company-and-earnings >/dev/null

docker compose exec -T api \
  python -m market_trader.options_analysis.cli validate \
  /app/fixtures/options_analysis/bull-call-qualified >/dev/null

docker compose exec -T api \
  python -m market_trader.risk.cli validate \
  /app/fixtures/risk/share-sizing-boundaries/approved-share.json >/dev/null

printf 'Foundation verification passed at %s\n' "$base_url"
