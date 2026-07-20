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

dashboard_overview="$(curl --fail --silent --show-error "${base_url}/api/dashboard/overview")"
printf '%s' "$dashboard_overview" | python3 -c '
import json
import sys

payload = json.load(sys.stdin)
assert payload["paper_mode"] is True
assert payload["data_state"] in {"ready", "stale", "partial", "unavailable"}
assert isinstance(payload["sources"], list)
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

docker compose exec -T api \
  python - <<'PY'
import json
from pathlib import Path

root = Path("/app/fixtures/paper_lifecycle")
required = {
    "success",
    "partial-fill",
    "reject",
    "stale-quote",
    "expired-approval",
    "cancel-race",
    "restart-recovery",
    "simulated-assignment",
}
found = {path.parent.name for path in root.glob("*/manifest.json")}
assert required <= found
for path in root.glob("*/manifest.json"):
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["paper_mode"] is True
    assert payload["expected_no_external_reference"] is True
    assert payload["paper_reference_prefix"] == "sim-paper"
PY

printf 'Foundation verification passed at %s\n' "$base_url"
