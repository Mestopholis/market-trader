#!/usr/bin/env bash
set -euo pipefail

base_url="${MARKET_TRADER_URL:-http://127.0.0.1:8080}"
health="$(curl --fail --silent --show-error "${base_url}/api/health")"

test "$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin)["trading_mode"])')" = "paper"
curl --fail --silent --show-error "$base_url/" | grep -q '<div id="root"></div>'

printf 'Foundation verification passed at %s\n' "$base_url"
