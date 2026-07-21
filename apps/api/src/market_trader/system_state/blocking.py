from collections.abc import Callable

from market_trader.system_state.models import SystemReadiness


class SystemBlockedError(ValueError):
    def __init__(self, code: str, *, component: str) -> None:
        super().__init__(code)
        self.code = code
        self.component = component


class BlockingStatePolicy:
    def __init__(self, readiness_provider: Callable[[], SystemReadiness]) -> None:
        self._readiness_provider = readiness_provider

    def ensure_paper_mutation_allowed(self) -> None:
        readiness = self._readiness_provider()
        for component in readiness.components:
            if component.blocking:
                raise SystemBlockedError(component.code, component=component.name)


def allow_all_policy() -> BlockingStatePolicy:
    return BlockingStatePolicy(
        lambda: SystemReadiness(status="ok", blocking=False, components=[])
    )
