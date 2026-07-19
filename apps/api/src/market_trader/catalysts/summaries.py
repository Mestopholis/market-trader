from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from market_trader.catalysts.configuration import SummaryPolicy
from market_trader.catalysts.models import (
    CatalystObservation,
    CitedSummary,
    SummarySegment,
)
from market_trader.catalysts.sanitization import sanitize_provider_payload
from market_trader.catalysts.serialization import stable_digest
from market_trader.domain.time import ensure_utc

SUMMARY_PROVIDER_ID = "recorded-summary-v1"


@dataclass(frozen=True)
class SummarySegmentInput:
    text: str
    observation_keys: tuple[str, ...]
    source_references: tuple[str, ...]


@dataclass(frozen=True)
class SummaryProviderResponse:
    provider_id: str
    generated_at: datetime
    segments: tuple[SummarySegmentInput, ...]


@dataclass(frozen=True)
class SummaryValidationResult:
    summary: CitedSummary | None
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "reasons", tuple(sorted(set(self.reasons))))
        if (self.summary is None) == (not self.reasons):
            raise ValueError("summary validation result requires exactly one outcome")


def validate_cited_summary(
    response: SummaryProviderResponse,
    accepted_observations: Mapping[str, CatalystObservation],
    policy: SummaryPolicy,
    *,
    quarantined_observation_keys: tuple[str, ...] = (),
) -> SummaryValidationResult:
    generated_at = ensure_utc(response.generated_at)
    if response.provider_id != SUMMARY_PROVIDER_ID:
        return _rejected("summary_source_unknown")
    if not response.segments:
        return _rejected("summary_citation_missing")
    quarantined = set(quarantined_observation_keys)
    segments: list[SummarySegment] = []
    total_characters = 0
    for raw_segment in response.segments:
        keys = tuple(sorted(set(raw_segment.observation_keys)))
        references = tuple(sorted(set(raw_segment.source_references)))
        if not keys or not references or any(key in quarantined for key in keys):
            return _rejected("summary_citation_missing")
        observations = tuple(accepted_observations.get(key) for key in keys)
        if any(observation is None for observation in observations):
            return _rejected("summary_citation_missing")
        expected_references = {
            observation.source_reference
            for observation in observations
            if observation is not None
        }
        if set(references) != expected_references:
            return _rejected("summary_citation_missing")
        sanitized = sanitize_provider_payload(raw_segment.text)
        if not isinstance(sanitized, str) or not sanitized:
            return _rejected("summary_citation_missing")
        total_characters += len(sanitized)
        if total_characters > policy.max_text_characters:
            return _rejected("summary_text_too_large")
        segments.append(
            SummarySegment(
                text=sanitized,
                observation_keys=keys,
                source_references=references,
            )
        )
    content_record = {
        "provider_id": response.provider_id,
        "generated_at": generated_at,
        "segments": tuple(segments),
        "policy_version": policy.version,
    }
    content_digest = stable_digest(content_record)
    summary_identity = (
        response.provider_id,
        generated_at,
        tuple(segments),
        policy.version,
    )
    summary_key = f"summary_{stable_digest(summary_identity)}"
    return SummaryValidationResult(
        summary=CitedSummary(
            summary_key=summary_key,
            provider_id=response.provider_id,
            generated_at=generated_at,
            segments=tuple(segments),
            policy_version=policy.version,
            content_digest=content_digest,
        ),
        reasons=(),
    )


def _rejected(reason: str) -> SummaryValidationResult:
    return SummaryValidationResult(summary=None, reasons=(reason,))
