from __future__ import annotations

import hashlib
import json
from pathlib import Path

FIXTURE_ROOT = Path("fixtures/paper_lifecycle")

SCENARIOS: dict[str, dict[str, object]] = {
    "success": {
        "case_name": "paper approval preview submit full fill",
        "scenario": "full_fill",
        "expected_order_status": "filled",
        "expected_position_status": "open",
        "expected_recovery_counts": {
            "open_approvals": 0,
            "working_orders": 0,
            "timed_out_orders": 0,
            "open_orders": 0,
            "open_positions": 1,
        },
    },
    "partial-fill": {
        "case_name": "paper partial fill leaves working remainder",
        "scenario": "partial_fill",
        "expected_order_status": "partially_filled",
        "expected_position_status": None,
        "expected_recovery_counts": {
            "open_approvals": 0,
            "working_orders": 1,
            "timed_out_orders": 0,
            "open_orders": 1,
            "open_positions": 0,
        },
    },
    "reject": {
        "case_name": "paper reject terminal order",
        "scenario": "reject",
        "expected_order_status": "rejected",
        "expected_position_status": None,
        "expected_recovery_counts": {
            "open_approvals": 0,
            "working_orders": 0,
            "timed_out_orders": 0,
            "open_orders": 0,
            "open_positions": 0,
        },
    },
    "stale-quote": {
        "case_name": "paper stale quote rejection path",
        "scenario": "timeout",
        "expected_order_status": "timed_out",
        "expected_position_status": None,
        "expected_recovery_counts": {
            "open_approvals": 1,
            "working_orders": 0,
            "timed_out_orders": 1,
            "open_orders": 1,
            "open_positions": 0,
        },
    },
    "expired-approval": {
        "case_name": "paper expired approval rejection path",
        "scenario": "timeout",
        "expected_order_status": "timed_out",
        "expected_position_status": None,
        "expected_recovery_counts": {
            "open_approvals": 0,
            "working_orders": 0,
            "timed_out_orders": 1,
            "open_orders": 1,
            "open_positions": 0,
        },
    },
    "cancel-race": {
        "case_name": "paper cancel replace race terminal state",
        "scenario": "cancel_replace",
        "expected_order_status": "replaced",
        "expected_position_status": None,
        "expected_recovery_counts": {
            "open_approvals": 0,
            "working_orders": 0,
            "timed_out_orders": 0,
            "open_orders": 0,
            "open_positions": 0,
        },
    },
    "restart-recovery": {
        "case_name": "paper restart recovery finds working order",
        "scenario": "accepted_unfilled",
        "expected_order_status": "working",
        "expected_position_status": None,
        "expected_recovery_counts": {
            "open_approvals": 1,
            "working_orders": 1,
            "timed_out_orders": 0,
            "open_orders": 1,
            "open_positions": 0,
        },
    },
    "simulated-assignment": {
        "case_name": "paper simulated assignment position",
        "scenario": "assignment",
        "expected_order_status": "filled",
        "expected_position_status": "assigned",
        "expected_recovery_counts": {
            "open_approvals": 0,
            "working_orders": 0,
            "timed_out_orders": 0,
            "open_orders": 0,
            "open_positions": 1,
        },
    },
}


def main() -> int:
    for fixture_id, scenario in SCENARIOS.items():
        payload = _manifest(fixture_id, scenario)
        target = FIXTURE_ROOT / fixture_id / "manifest.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return 0


def _manifest(fixture_id: str, scenario: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {
        "paper_lifecycle_fixture_schema_version": 1,
        "fixture_id": fixture_id,
        "paper_mode": True,
        "approval_state": "approved",
        "paper_reference_prefix": "sim-paper",
        "expected_no_external_reference": True,
        **scenario,
    }
    payload["fixture_hash"] = _content_hash(payload)
    return payload


def _content_hash(raw: dict[str, object]) -> str:
    payload = dict(raw)
    payload.pop("fixture_hash", None)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
