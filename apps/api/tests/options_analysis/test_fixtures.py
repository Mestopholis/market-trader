import hashlib
import json
from pathlib import Path

import pytest

from market_trader.options_analysis.fixtures import OptionsFixtureDataset


def test_fixture_loader_verifies_stream_digest_and_rejects_sensitive_keys(tmp_path: Path) -> None:
    stream = tmp_path / "contracts.json"
    stream.write_text('[{"contract_id":"call-1"}]', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "options_analysis_fixture_schema_version": 1,
                "dataset_id": "unit-test",
                "as_of": "2026-08-14T14:00:00+00:00",
                "policy_version": "options-analysis-policy-v1",
                "policy_hash": "a" * 64,
                "streams": [{"filename": "contracts.json", "sha256": _digest(stream)}],
                "expected_counts": {},
                "expected_reason_summary": {},
                "expected_result_digest": "b" * 64,
            }
        ),
        encoding="utf-8",
    )

    dataset = OptionsFixtureDataset.load(tmp_path)

    assert dataset.dataset_id == "unit-test"
    assert dataset.streams == (({"contract_id": "call-1"},),)


def test_fixture_loader_rejects_sensitive_record_keys(tmp_path: Path) -> None:
    stream = tmp_path / "contracts.json"
    stream.write_text('[{"api_key":"not-allowed"}]', encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "options_analysis_fixture_schema_version": 1,
                "dataset_id": "unit-test",
                "as_of": "2026-08-14T14:00:00+00:00",
                "policy_version": "options-analysis-policy-v1",
                "policy_hash": "a" * 64,
                "streams": [{"filename": "contracts.json", "sha256": _digest(stream)}],
                "expected_counts": {},
                "expected_reason_summary": {},
                "expected_result_digest": "b" * 64,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="sensitive"):
        OptionsFixtureDataset.load(tmp_path)


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
