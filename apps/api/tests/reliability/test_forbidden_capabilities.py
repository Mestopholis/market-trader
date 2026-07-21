from __future__ import annotations

import json
import os
import re
from pathlib import Path

from fastapi.testclient import TestClient

from market_trader.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[4]

FORBIDDEN_EXPOSURE_PATTERNS = (
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
)

SAFETY_ALLOWLIST = (
    re.compile(r"\bno live\b", re.IGNORECASE),
    re.compile(r"\bnot expose\b", re.IGNORECASE),
    re.compile(r"\bforbidden\b", re.IGNORECASE),
    re.compile(r"\bsimulated_broker_reference\b", re.IGNORECASE),
)


def test_openapi_contract_excludes_forbidden_live_broker_capabilities() -> None:
    response = TestClient(create_app(), base_url="https://testserver").get("/api/openapi.json")

    assert response.status_code == 200
    _assert_no_forbidden_exposure(json.dumps(response.json()))


def test_frontend_sources_and_build_artifacts_exclude_forbidden_capability_copy() -> None:
    scanned_files = _scan_text_roots(
        REPO_ROOT / "apps" / "web" / "src",
        REPO_ROOT / "apps" / "web" / "dist",
    )

    assert scanned_files, "expected frontend source or build artifact files to be scanned"


def test_security_gate_scripts_are_declared_and_wired() -> None:
    security_script = REPO_ROOT / "scripts" / "security-check.sh"

    assert security_script.exists()
    assert os.access(security_script, os.X_OK)

    script_text = security_script.read_text(encoding="utf-8")
    for required_fragment in (
        "pip check",
        "ruff check",
        "npm audit",
        "forbidden capability",
        "docker compose config",
    ):
        assert required_fragment in script_text

    ci_text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    verify_text = (REPO_ROOT / "scripts" / "verify-foundation.sh").read_text(encoding="utf-8")

    assert "scripts/security-check.sh" in ci_text
    assert "scripts/security-check.sh" in verify_text


def test_security_gate_has_project_configuration() -> None:
    assert "[tool.market_trader.security]" in (
        REPO_ROOT / "apps" / "api" / "pyproject.toml"
    ).read_text(encoding="utf-8")

    package = json.loads((REPO_ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8"))
    assert package["scripts"]["security"] == "npm audit --audit-level high --omit dev"


def _scan_text_roots(*roots: Path) -> list[Path]:
    scanned: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_dir() or path.suffix.lower() not in {
                ".css",
                ".html",
                ".js",
                ".jsx",
                ".ts",
                ".tsx",
            }:
                continue
            if ".test." in path.name:
                continue
            _assert_no_forbidden_exposure(path.read_text(encoding="utf-8"), source=path)
            scanned.append(path)
    return scanned


def _assert_no_forbidden_exposure(text: str, *, source: Path | None = None) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if any(allow.search(line) for allow in SAFETY_ALLOWLIST):
            continue
        for pattern in FORBIDDEN_EXPOSURE_PATTERNS:
            assert not pattern.search(line), (
                f"forbidden capability exposure matched {pattern.pattern!r}"
                f" in {source or 'payload'}:{line_number}"
            )
