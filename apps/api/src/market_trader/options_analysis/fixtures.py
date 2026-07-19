import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

_REQUIRED_MANIFEST_KEYS = frozenset(
    {
        "options_analysis_fixture_schema_version",
        "dataset_id",
        "as_of",
        "policy_version",
        "policy_hash",
        "streams",
        "expected_counts",
        "expected_reason_summary",
        "expected_result_digest",
    }
)
_SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "cookie",
        "token",
        "secret",
        "password",
        "api_key",
        "account",
        "approval",
        "order",
    }
)


@dataclass(frozen=True)
class OptionsFixtureDataset:
    dataset_id: str
    streams: tuple[tuple[dict[str, object], ...], ...]
    manifest: dict[str, object]

    @classmethod
    def load(cls, path: Path | str) -> "OptionsFixtureDataset":
        root = Path(path)
        try:
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("options fixture manifest is malformed") from error
        if not isinstance(manifest, dict) or set(manifest) != _REQUIRED_MANIFEST_KEYS:
            raise ValueError("options fixture manifest has invalid keys")
        if manifest["options_analysis_fixture_schema_version"] != 1:
            raise ValueError("unsupported options fixture schema")
        if not isinstance(manifest["dataset_id"], str) or not manifest["dataset_id"]:
            raise ValueError("options fixture dataset id is invalid")
        streams_value = manifest["streams"]
        if not isinstance(streams_value, list):
            raise ValueError("options fixture streams are invalid")
        streams: list[tuple[dict[str, object], ...]] = []
        for stream in streams_value:
            if not isinstance(stream, dict) or set(stream) != {"filename", "sha256"}:
                raise ValueError("options fixture stream is invalid")
            filename, expected_hash = stream["filename"], stream["sha256"]
            if not isinstance(filename, str) or Path(filename).name != filename:
                raise ValueError("options fixture stream filename is invalid")
            if not isinstance(expected_hash, str):
                raise ValueError("options fixture stream digest is invalid")
            try:
                raw = (root / filename).read_bytes()
                records = json.loads(raw)
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise ValueError("options fixture stream is malformed") from error
            if hashlib.sha256(raw).hexdigest() != expected_hash:
                raise ValueError("options fixture stream digest mismatch")
            if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
                raise ValueError("options fixture stream records are invalid")
            if any(_contains_sensitive_key(item) for item in records):
                raise ValueError("options fixture contains sensitive key")
            streams.append(tuple(records))
        return cls(dataset_id=manifest["dataset_id"], streams=tuple(streams), manifest=manifest)


def _contains_sensitive_key(value: object) -> bool:
    if isinstance(value, dict):
        return any(
            key.lower() in _SENSITIVE_KEYS or _contains_sensitive_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_sensitive_key(item) for item in value)
    return False
