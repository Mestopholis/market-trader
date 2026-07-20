import hashlib
import json
from pathlib import Path

from market_trader.paper.models import PaperBrokerScenario, PaperOrderStatus, PaperPositionStatus
from scripts.generate_paper_lifecycle_fixtures import main as generate_fixtures

FIXTURE_ROOT = Path("fixtures/paper_lifecycle")
SCENARIOS = {
    "success": ("full_fill", "filled", "open"),
    "partial-fill": ("partial_fill", "partially_filled", None),
    "reject": ("reject", "rejected", None),
    "stale-quote": ("timeout", "timed_out", None),
    "expired-approval": ("timeout", "timed_out", None),
    "cancel-race": ("cancel_replace", "replaced", None),
    "restart-recovery": ("accepted_unfilled", "working", None),
    "simulated-assignment": ("assignment", "filled", "assigned"),
}


def test_checked_in_paper_lifecycle_fixtures_cover_required_scenarios() -> None:
    manifest_paths = sorted(FIXTURE_ROOT.glob("*/manifest.json"))
    fixture_ids = {path.parent.name for path in manifest_paths}

    assert set(SCENARIOS) <= fixture_ids

    for path in manifest_paths:
        payload = json.loads(path.read_text(encoding="utf-8"))
        scenario, status, position_status = SCENARIOS[path.parent.name]
        assert payload["paper_lifecycle_fixture_schema_version"] == 1
        assert PaperBrokerScenario(payload["scenario"]) == PaperBrokerScenario(scenario)
        assert PaperOrderStatus(payload["expected_order_status"]) == PaperOrderStatus(status)
        assert payload["expected_position_status"] == position_status
        if position_status is not None:
            assert PaperPositionStatus(payload["expected_position_status"]) == PaperPositionStatus(
                position_status
            )
        assert payload["paper_mode"] is True
        assert payload["expected_no_external_reference"] is True
        assert payload["expected_recovery_counts"]
        assert not _contains_forbidden_live_text(path.parent)


def test_paper_lifecycle_fixture_generator_is_idempotent() -> None:
    before = _fixture_hashes()
    generate_fixtures()
    after = _fixture_hashes()

    assert after == before


def _fixture_hashes() -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(FIXTURE_ROOT.glob("*/manifest.json"))
    }


def _contains_forbidden_live_text(path: Path) -> bool:
    encoded = json.dumps(
        {
            file.name: file.read_text(encoding="utf-8")
            for file in sorted(path.glob("*.json"))
        },
        sort_keys=True,
    ).lower()
    forbidden = (
        "schwab",
        "oauth",
        "api_key",
        "secret",
        "password",
        "account",
        "live_mode",
        "external_broker_reference",
    )
    return any(term in encoded for term in forbidden)
