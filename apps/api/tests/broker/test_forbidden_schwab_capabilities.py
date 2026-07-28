import json
import re
from pathlib import Path

from fastapi.testclient import TestClient

from market_trader.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[4]

SCHWAB_ORDER_PATTERNS = (
    re.compile(r"\bschwab\b.{0,120}\border submit\b", re.IGNORECASE),
    re.compile(r"\border submit\b.{0,120}\bschwab\b", re.IGNORECASE),
    re.compile(r"\bschwab\b.{0,120}\bsubmit\b", re.IGNORECASE),
    re.compile(r"\bsubmit\b.{0,120}\bschwab\b", re.IGNORECASE),
    re.compile(r"\bschwab\b.{0,120}\bsubmit order\b", re.IGNORECASE),
    re.compile(r"\bsubmit order\b.{0,120}\bschwab\b", re.IGNORECASE),
    re.compile(r"\bschwab\b.{0,120}\bplace\b", re.IGNORECASE),
    re.compile(r"\bplace\b.{0,120}\bschwab\b", re.IGNORECASE),
    re.compile(r"\bschwab\b.{0,120}\bcancel\b", re.IGNORECASE),
    re.compile(r"\bschwab\b.{0,120}\breplace\b", re.IGNORECASE),
    re.compile(r"\bschwab\b.{0,120}\bsaved[- ]?order\b", re.IGNORECASE),
    re.compile(r"\bschwab\b.{0,120}\blive[_ -]?mode\b", re.IGNORECASE),
)


def test_openapi_allows_read_only_schwab_but_no_schwab_order_capability() -> None:
    response = TestClient(create_app(), base_url="https://testserver").get("/api/openapi.json")

    assert response.status_code == 200
    _assert_no_schwab_order_capability(json.dumps(response.json(), indent=2))


def test_source_and_fixtures_exclude_schwab_order_capability() -> None:
    for root in (
        REPO_ROOT / "apps" / "api" / "src",
        REPO_ROOT / "apps" / "api" / "fixtures",
        REPO_ROOT / "apps" / "web" / "src",
        REPO_ROOT / "apps" / "web" / "dist",
    ):
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_dir() or path.suffix.lower() not in {
                ".css",
                ".html",
                ".js",
                ".jsx",
                ".json",
                ".py",
                ".ts",
                ".tsx",
            }:
                continue
            if ".test." in path.name or "tests" in path.parts:
                continue
            _assert_no_schwab_order_capability(
                path.read_text(encoding="utf-8"),
                source=path,
            )


def test_security_check_uses_schwab_order_specific_patterns() -> None:
    security_check = (REPO_ROOT / "scripts" / "security-check.sh").read_text(
        encoding="utf-8"
    )

    assert r"\bschwab\b.{0,120}\bsubmit\b" in security_check
    assert "Schwab read-only and validation-contract references are allowed" in security_check


def _assert_no_schwab_order_capability(
    text: str, *, source: Path | None = None
) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        if "forbidden" in line.lower() or "explicit non-capabilities" in line.lower():
            continue
        for pattern in SCHWAB_ORDER_PATTERNS:
            assert not pattern.search(line), (
                f"forbidden Schwab order capability matched {pattern.pattern!r}"
                f" in {source or 'payload'}:{line_number}"
            )
