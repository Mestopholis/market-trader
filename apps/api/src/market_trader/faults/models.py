from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from market_trader.system_state.models import ComponentState

type FaultKind = Literal[
    "provider_loss",
    "database_contention",
    "clock_drift",
    "disk_write_failure",
    "process_restart_recovery",
]


@dataclass(frozen=True, slots=True)
class FaultScenario:
    kind: FaultKind
    raw_error: str | None = None
    provider_name: str | None = None
    offset_seconds: int | None = None
    pending_events: int | None = None

    @classmethod
    def provider_loss(cls, *, provider_name: str, raw_error: str | None = None) -> FaultScenario:
        return cls(kind="provider_loss", provider_name=provider_name, raw_error=raw_error)

    @classmethod
    def database_contention(cls, *, raw_error: str | None = None) -> FaultScenario:
        return cls(kind="database_contention", raw_error=raw_error)

    @classmethod
    def clock_drift(cls, *, offset_seconds: int, raw_error: str | None = None) -> FaultScenario:
        return cls(kind="clock_drift", offset_seconds=offset_seconds, raw_error=raw_error)

    @classmethod
    def disk_write_failure(cls, *, raw_error: str | None = None) -> FaultScenario:
        return cls(kind="disk_write_failure", raw_error=raw_error)

    @classmethod
    def process_restart_recovery(
        cls,
        *,
        pending_events: int,
        raw_error: str | None = None,
    ) -> FaultScenario:
        return cls(
            kind="process_restart_recovery",
            pending_events=pending_events,
            raw_error=raw_error,
        )

    def component_state(self) -> ComponentState:
        if self.kind == "provider_loss":
            return ComponentState(
                name="market_data_provider",
                status="blocking",
                code="provider_unavailable",
                summary="Market data provider is unavailable.",
                blocking=True,
                details={
                    "provider": self.provider_name or "unknown",
                    "fault": self.kind,
                },
            )
        if self.kind == "database_contention":
            return ComponentState(
                name="database",
                status="blocking",
                code="database_contention",
                summary="Database writes are temporarily blocked by contention.",
                blocking=True,
                details={"fault": self.kind},
            )
        if self.kind == "clock_drift":
            return ComponentState(
                name="clock",
                status="blocking",
                code="clock_drift_detected",
                summary="System clock drift exceeds the safe trading threshold.",
                blocking=True,
                details={
                    "fault": self.kind,
                    "offset_seconds": _bounded_non_negative(self.offset_seconds, maximum=86_400),
                },
            )
        if self.kind == "disk_write_failure":
            return ComponentState(
                name="disk",
                status="blocking",
                code="disk_write_failed",
                summary="Persistent storage cannot be written safely.",
                blocking=True,
                details={"fault": self.kind},
            )
        return ComponentState(
            name="restart_recovery",
            status="blocking",
            code="restart_recovery_gap",
            summary="Process restart recovery has pending reconciliation work.",
            blocking=True,
            details={
                "fault": self.kind,
                "pending_events": _bounded_non_negative(self.pending_events, maximum=10_000),
            },
        )


def _bounded_non_negative(value: int | None, *, maximum: int) -> int:
    if value is None or value < 0:
        return 0
    return min(value, maximum)
