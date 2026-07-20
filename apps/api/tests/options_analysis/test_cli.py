import hashlib
import json
from pathlib import Path

from _pytest.capture import CaptureFixture

from market_trader.options_analysis import cli


def _write_fixture(root: Path, *, records: list[dict[str, object]] | None = None) -> Path:
    root.mkdir()
    payload = records or [{"sequence": 2, "kind": "spread"}, {"sequence": 1, "kind": "contract"}]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    (root / "events.json").write_bytes(raw)
    manifest = {
        "options_analysis_fixture_schema_version": 1,
        "dataset_id": "bull-call-qualified",
        "as_of": "2026-08-14T14:30:00+00:00",
        "policy_version": "options-analysis-policy-v1",
        "policy_hash": "a" * 64,
        "streams": [{"filename": "events.json", "sha256": hashlib.sha256(raw).hexdigest()}],
        "expected_counts": {"records": len(payload)},
        "expected_reason_summary": {"pin_risk": 1},
        "expected_result_digest": "b" * 64,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return root


def _json_lines(value: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in value.splitlines() if line]


def test_validate_outputs_single_sorted_json_summary(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    dataset = _write_fixture(tmp_path / "dataset")

    assert cli.main(["validate", str(dataset)]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    lines = _json_lines(captured.out)
    assert len(lines) == 1
    assert captured.out == json.dumps(lines[0], sort_keys=True, separators=(",", ":")) + "\n"
    assert lines[0] == {
        "as_of": "2026-08-14T14:30:00+00:00",
        "command": "validate",
        "dataset_id": "bull-call-qualified",
        "expected_counts": {"records": 2},
        "expected_reason_summary": {"pin_risk": 1},
        "expected_result_digest": "b" * 64,
        "persistence": "memory",
        "policy_hash": "a" * 64,
        "policy_version": "options-analysis-policy-v1",
        "record_count": 2,
    }


def test_analyze_outputs_deterministic_record_order_without_secrets(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    dataset = _write_fixture(tmp_path / "dataset")

    assert cli.main(["analyze", str(dataset)]) == 0

    payload = _json_lines(capsys.readouterr().out)[0]
    assert payload["command"] == "analyze"
    assert payload["records"] == [
        {"kind": "contract", "sequence": 1},
        {"kind": "spread", "sequence": 2},
    ]
    encoded = json.dumps(payload, sort_keys=True)
    assert "authorization" not in encoded
    assert "order" not in encoded


def test_malformed_fixture_returns_dataset_error(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    dataset = _write_fixture(tmp_path / "dataset")
    (dataset / "events.json").write_text("[]", encoding="utf-8")

    assert cli.main(["validate", str(dataset)]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert _json_lines(captured.err) == [
        {"error": "dataset_error", "message": "options analysis fixture is invalid"}
    ]


def test_sensitive_fixture_returns_dataset_error(
    tmp_path: Path,
    capsys: CaptureFixture[str],
) -> None:
    dataset = _write_fixture(tmp_path / "dataset", records=[{"api_key": "secret"}])

    assert cli.main(["analyze", str(dataset)]) == 2

    assert _json_lines(capsys.readouterr().err) == [
        {"error": "dataset_error", "message": "options analysis fixture is invalid"}
    ]
