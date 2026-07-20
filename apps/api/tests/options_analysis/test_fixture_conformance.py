import hashlib
import json
from pathlib import Path

from market_trader.options_analysis.fixtures import OptionsFixtureDataset
from market_trader.options_analysis.replay import replay_options_analysis
from market_trader.options_analysis.serialization import stable_digest
from scripts.generate_options_analysis_fixtures import main as generate_fixtures

FIXTURE_ROOT = Path("fixtures/options_analysis")
DATASET_IDS = (
    "bull-call-qualified",
    "bear-put-qualified",
    "contract-boundaries",
    "risk-warnings",
)


def test_generated_options_analysis_fixtures_are_conformant() -> None:
    for dataset_id in DATASET_IDS:
        dataset = OptionsFixtureDataset.load(FIXTURE_ROOT / dataset_id)
        records = replay_options_analysis(dataset)
        expected_counts = dataset.manifest["expected_counts"]

        assert dataset.dataset_id == dataset_id
        assert isinstance(expected_counts, dict)
        assert expected_counts["records"] == len(records)
        assert dataset.manifest["expected_result_digest"] == stable_digest(records)
        assert not _contains_forbidden_text(FIXTURE_ROOT / dataset_id)


def test_options_analysis_fixture_generator_is_idempotent() -> None:
    before = _fixture_hashes()
    generate_fixtures()
    after = _fixture_hashes()

    assert after == before


def _fixture_hashes() -> dict[str, str]:
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(FIXTURE_ROOT.glob("*/*.json"))
    }


def _contains_forbidden_text(path: Path) -> bool:
    encoded = json.dumps(
        {
            file.name: file.read_text(encoding="utf-8")
            for file in sorted(path.glob("*.json"))
        },
        sort_keys=True,
    ).lower()
    return any(term in encoded for term in ("authorization", "api_key", "order", "approval"))
