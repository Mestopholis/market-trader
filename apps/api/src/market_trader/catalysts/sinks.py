from sqlalchemy.orm import Session

from market_trader.catalysts.models import SourceRunResult
from market_trader.repositories.catalysts import (
    CatalystRepository,
    PersistedCatalystSourceRun,
)
from market_trader.repositories.symbols import SymbolRepository


class CatalystPersistenceError(RuntimeError):
    pass


class RepositoryCatalystSink:
    def __init__(self, session: Session) -> None:
        self._repository = CatalystRepository(session)
        self._symbols = SymbolRepository(session)

    def persist(self, result: SourceRunResult) -> PersistedCatalystSourceRun:
        existing = self._repository.get_source_run(result.run_key)
        if existing is not None:
            if existing.result_digest != result.result_digest:
                from market_trader.repositories.catalysts import CatalystPersistenceConflict

                raise CatalystPersistenceConflict(f"source run key conflict: {result.run_key}")
            return existing
        symbol_ids = self._resolve_symbols(result)
        accepted_keys = {item.observation_key for item in result.observations}
        for summary in result.summaries:
            cited = {key for segment in summary.segments for key in segment.observation_keys}
            if not cited.issubset(accepted_keys):
                raise CatalystPersistenceError("missing observation citation")
        run = self._repository.create_source_run(result)
        for observation in result.observations:
            self._repository.record_observation(
                run.id,
                observation,
                None if observation.symbol is None else symbol_ids[observation.symbol],
            )
        for quarantine in result.quarantined:
            self._repository.record_quarantine(run.id, quarantine)
        for decision in result.decisions:
            self._repository.record_decision(
                run.id,
                decision,
                None if decision.symbol is None else symbol_ids[decision.symbol],
            )
        for summary in result.summaries:
            self._repository.record_summary(run.id, summary)
        return run

    def _resolve_symbols(self, result: SourceRunResult) -> dict[str, str]:
        names = {
            *(item.symbol for item in result.observations if item.symbol is not None),
            *(item.symbol for item in result.decisions if item.symbol is not None),
        }
        resolved: dict[str, str] = {}
        for name in sorted(names):
            symbol = self._symbols.get_symbol_by_display_symbol(name)
            if symbol is None:
                raise CatalystPersistenceError(f"missing symbol: {name}")
            resolved[name] = symbol.id
        return resolved
