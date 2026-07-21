from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from market_trader.faults.models import FaultScenario
from market_trader.system_state.models import ComponentState


class FaultInjector(Protocol):
    def components(self) -> Sequence[ComponentState]: ...


class DeterministicFaultInjector:
    def __init__(self, scenarios: Sequence[FaultScenario]) -> None:
        self._scenarios = tuple(scenarios)

    def components(self) -> tuple[ComponentState, ...]:
        return tuple(scenario.component_state() for scenario in self._scenarios)
