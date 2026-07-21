#!/usr/bin/env bash
set -euo pipefail

root_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
api_dir="$root_dir/apps/api"
web_dir="$root_dir/apps/web"

if [ -x "$api_dir/.venv/bin/python" ]; then
  python_bin="$api_dir/.venv/bin/python"
else
  python_bin="${PYTHON:-python3}"
fi

if [ -x "$api_dir/.venv/bin/ruff" ]; then
  ruff_bin="$api_dir/.venv/bin/ruff"
else
  ruff_bin="ruff"
fi

log() {
  printf '[security-check] %s\n' "$1"
}

log "running Python dependency audit with pip check"
(
  cd "$api_dir"
  "$python_bin" -m pip check
)

log "running static-security scan with ruff check"
(
  cd "$api_dir"
  "$ruff_bin" check src tests scripts
)

log "running Node dependency audit with npm audit"
if command -v npm >/dev/null 2>&1; then
  audit_log="$(mktemp)"
  if (
    cd "$web_dir"
    npm audit --audit-level high --omit dev
  ) >"$audit_log" 2>&1; then
    cat "$audit_log"
  else
    audit_status=$?
    cat "$audit_log"
    if grep -Eiq 'ENOTFOUND|EAI_AGAIN|ECONNRESET|ETIMEDOUT|network|registry|audit endpoint' "$audit_log" \
      && [ "${MARKET_TRADER_ALLOW_OFFLINE_AUDIT:-1}" = "1" ] \
      && [ -z "${CI:-}" ]; then
      log "npm audit could not reach the registry; continuing because offline local audits are allowed"
    else
      rm -f "$audit_log"
      exit "$audit_status"
    fi
  fi
  rm -f "$audit_log"
else
  log "npm is unavailable; skipping Node audit"
fi

log "running secret scan and forbidden capability scan"
"$python_bin" - "$root_dir" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
text_suffixes = {
    ".css",
    ".html",
    ".js",
    ".jsx",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
skipped_parts = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "node_modules"}
scan_roots = [
    root / ".github",
    root / "scripts",
    root / "apps" / "api" / "src",
    root / "apps" / "api" / "fixtures",
    root / "apps" / "web" / "src",
    root / "apps" / "web" / "dist",
]

secret_patterns = [
    re.compile(r"(?i)\b(secret|token|password|api[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
]
forbidden_patterns = [
    re.compile(r"\bschwab\b", re.IGNORECASE),
    re.compile(r"\blive[_ -]?mode\b", re.IGNORECASE),
    re.compile(r"\bbroker credential", re.IGNORECASE),
    re.compile(r"\bconnect broker\b", re.IGNORECASE),
    re.compile(r"\barm live\b", re.IGNORECASE),
    re.compile(r"\bplace live order\b", re.IGNORECASE),
    re.compile(r"\bsubmit live order\b", re.IGNORECASE),
    re.compile(r"\bexternally reachable\b", re.IGNORECASE),
    re.compile(r"\bexternal deployment\b", re.IGNORECASE),
    re.compile(r"\bapi[_-]?key\s*[:=]\s*['\"][^'\"]+['\"]", re.IGNORECASE),
]
allowlisted_lines = [
    re.compile(r"\bno live\b", re.IGNORECASE),
    re.compile(r"\bnot expose\b", re.IGNORECASE),
    re.compile(r"\bforbidden\b", re.IGNORECASE),
    re.compile(r"\bredact", re.IGNORECASE),
    re.compile(r"\bsanitiz", re.IGNORECASE),
    re.compile(r"\bsimulated_broker_reference\b", re.IGNORECASE),
]
allowlisted_path_parts = {
    "test_forbidden_capabilities.py",
    "redaction.py",
    "sanitization.py",
    "fixtures.py",
    "serialization.py",
    "models.py",
}

failures: list[str] = []
scanned = 0
for scan_root in scan_roots:
    if not scan_root.exists():
        continue
    for path in sorted(scan_root.rglob("*")):
        if path.is_dir() or path.suffix.lower() not in text_suffixes:
            continue
        if any(part in skipped_parts for part in path.parts):
            continue
        relative = path.relative_to(root)
        if ".test." in path.name or "tests" in relative.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        scanned += 1
        for line_number, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in secret_patterns):
                failures.append(f"secret-like literal in {relative}:{line_number}")
            if path.name in allowlisted_path_parts or any(pattern.search(line) for pattern in allowlisted_lines):
                continue
            for pattern in forbidden_patterns:
                if pattern.search(line):
                    failures.append(
                        f"forbidden capability exposure {pattern.pattern!r} in {relative}:{line_number}"
                    )

if scanned == 0:
    failures.append("no text files scanned")

if failures:
    for failure in failures:
        print(failure, file=sys.stderr)
    raise SystemExit(1)
PY

log "running OpenAPI forbidden capability scan"
"$python_bin" - "$root_dir" <<'PY'
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
sys.path.insert(0, str(root / "apps" / "api" / "src"))

from market_trader.main import create_app  # noqa: E402

payload = json.dumps(create_app().openapi())
for pattern in (
    re.compile(r"\bschwab\b", re.IGNORECASE),
    re.compile(r"\blive[_ -]?mode\b", re.IGNORECASE),
    re.compile(r"\bapi[_ -]?key\b", re.IGNORECASE),
    re.compile(r"\bbroker credential", re.IGNORECASE),
    re.compile(r"\bconnect broker\b", re.IGNORECASE),
    re.compile(r"\barm live\b", re.IGNORECASE),
    re.compile(r"\bplace live order\b", re.IGNORECASE),
    re.compile(r"\bsubmit live order\b", re.IGNORECASE),
    re.compile(r"\bexternally reachable\b", re.IGNORECASE),
    re.compile(r"\bexternal deployment\b", re.IGNORECASE),
):
    if pattern.search(payload):
        raise SystemExit(f"OpenAPI exposes forbidden capability pattern: {pattern.pattern}")
PY

log "running container configuration checks"
"$python_bin" - "$root_dir" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
api_dockerfile = (root / "apps" / "api" / "Dockerfile").read_text(encoding="utf-8")
web_dockerfile = (root / "apps" / "web" / "Dockerfile").read_text(encoding="utf-8")
compose = (root / "compose.yaml").read_text(encoding="utf-8")

failures: list[str] = []
if "USER appuser" not in api_dockerfile:
    failures.append("api Dockerfile must run as appuser")
if re.search(r"^FROM\s+[^\n:]+:latest\b", api_dockerfile + "\n" + web_dockerfile, re.MULTILINE):
    failures.append("Dockerfiles must not use latest tags")
if "127.0.0.1:8080:8080" not in compose:
    failures.append("web service must bind to loopback only")
if re.search(r"^\s*privileged:\s*true\b", compose, re.MULTILINE):
    failures.append("compose services must not run privileged")
if re.search(r"^\s*-\s*['\"]?8000:8000", compose, re.MULTILINE):
    failures.append("api service must not publish its internal port")

if failures:
    for failure in failures:
        print(failure, file=sys.stderr)
    raise SystemExit(1)
PY

if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  log "validating docker compose config"
  (
    cd "$root_dir"
    docker compose config >/dev/null
  )
else
  log "docker compose is unavailable; skipping docker compose config"
fi

log "security gate passed"
