#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
base_url="${MARKET_TRADER_URL:-http://127.0.0.1:8080}"

"$root_dir/scripts/security-check.sh"

health="$(curl --fail --silent --show-error "${base_url}/api/health")"

test "$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["trading_mode"])')" = "paper"
database="$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("database", ""))')"
test -z "$database" || test "$database" = "ok"

auth_username="${MARKET_TRADER_AUTH_USERNAME:-${MARKET_TRADER_USERNAME:-}}"
auth_password="${MARKET_TRADER_AUTH_PASSWORD:-${MARKET_TRADER_PASSWORD:-}}"
if [ -z "$auth_username" ] || [ -z "$auth_password" ]; then
  printf 'MARKET_TRADER_AUTH_USERNAME and MARKET_TRADER_AUTH_PASSWORD are required for protected endpoint verification.\n' >&2
  exit 1
fi

login_headers="$(mktemp)"
trap 'rm -f "$login_headers"' EXIT
login_payload="$(MARKET_TRADER_LOGIN_USERNAME="$auth_username" MARKET_TRADER_LOGIN_PASSWORD="$auth_password" python3 - <<'PY'
import json
import os

print(json.dumps({
    "username": os.environ["MARKET_TRADER_LOGIN_USERNAME"],
    "password": os.environ["MARKET_TRADER_LOGIN_PASSWORD"],
}))
PY
)"

curl --fail --silent --show-error \
  -D "$login_headers" \
  -o /dev/null \
  -H 'Content-Type: application/json' \
  --data "$login_payload" \
  "${base_url}/api/auth/login"

session_cookie="$(python3 - "$login_headers" <<'PY'
from pathlib import Path
import sys

for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not line.lower().startswith("set-cookie:"):
        continue
    cookie = line.split(":", 1)[1].strip().split(";", 1)[0]
    if cookie.startswith("market_trader_session="):
        print(cookie)
        raise SystemExit(0)
raise SystemExit("login did not set market_trader_session")
PY
)"

auth_curl() {
  curl --fail --silent --show-error -H "Cookie: $session_cookie" "$1"
}

market_state="$(auth_curl "${base_url}/api/market-state")"
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

dashboard_overview="$(auth_curl "${base_url}/api/dashboard/overview")"
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
