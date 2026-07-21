from __future__ import annotations

from pathlib import Path

from market_trader.faults.injectors import DeterministicFaultInjector
from market_trader.faults.models import FaultScenario
from market_trader.system_state.models import ComponentState, SystemReadiness
from market_trader.system_state.service import collect_system_state
from tests.db_helpers import migrated_engine


def test_provider_loss_fault_blocks_market_data_with_safe_diagnostics(tmp_path: Path) -> None:
    state = _collect_with_fault(
        tmp_path,
        FaultScenario.provider_loss(provider_name="polygon", raw_error="token=super-secret"),
    )

    component = _component(state, "market_data_provider")
    assert state.status == "blocking"
    assert component.status == "blocking"
    assert component.blocking is True
    assert component.code == "provider_unavailable"
    assert component.summary == "Market data provider is unavailable."
    assert component.details == {"provider": "polygon", "fault": "provider_loss"}
    assert "super-secret" not in state.model_dump_json()


def test_database_contention_fault_blocks_database_without_lock_details(tmp_path: Path) -> None:
    state = _collect_with_fault(
        tmp_path,
        FaultScenario.database_contention(raw_error="database is locked by pid 4811"),
    )

    component = _component(state, "database")
    assert component.status == "blocking"
    assert component.blocking is True
    assert component.code == "database_contention"
    assert component.summary == "Database writes are temporarily blocked by contention."
    assert component.details == {"fault": "database_contention"}
    assert "4811" not in state.model_dump_json()


def test_clock_drift_fault_blocks_scheduler_with_bounded_offset(tmp_path: Path) -> None:
    state = _collect_with_fault(
        tmp_path,
        FaultScenario.clock_drift(offset_seconds=900, raw_error="ntp peer 10.0.0.4"),
    )

    component = _component(state, "clock")
    assert component.status == "blocking"
    assert component.blocking is True
    assert component.code == "clock_drift_detected"
    assert component.summary == "System clock drift exceeds the safe trading threshold."
    assert component.details == {"fault": "clock_drift", "offset_seconds": 900}
    assert "10.0.0.4" not in state.model_dump_json()


def test_disk_write_failure_fault_blocks_backups_without_paths(tmp_path: Path) -> None:
    state = _collect_with_fault(
        tmp_path,
        FaultScenario.disk_write_failure(raw_error=f"permission denied: {tmp_path / 'backup.db'}"),
    )

    component = _component(state, "disk")
    assert component.status == "blocking"
    assert component.blocking is True
    assert component.code == "disk_write_failed"
    assert component.summary == "Persistent storage cannot be written safely."
    assert component.details == {"fault": "disk_write_failure"}
    assert str(tmp_path) not in state.model_dump_json()


def test_process_restart_recovery_fault_blocks_until_reconciled(tmp_path: Path) -> None:
    state = _collect_with_fault(
        tmp_path,
        FaultScenario.process_restart_recovery(pending_events=3, raw_error="order tmp/order-1"),
    )

    component = _component(state, "restart_recovery")
    assert component.status == "blocking"
    assert component.blocking is True
    assert component.code == "restart_recovery_gap"
    assert component.summary == "Process restart recovery has pending reconciliation work."
    assert component.details == {"fault": "process_restart_recovery", "pending_events": 3}
    assert "tmp/order-1" not in state.model_dump_json()


def _collect_with_fault(tmp_path: Path, scenario: FaultScenario) -> SystemReadiness:
    engine = migrated_engine(tmp_path, filename=f"{scenario.kind}.db")
    try:
        return collect_system_state(
            str(engine.url),
            fault_injector=DeterministicFaultInjector([scenario]),
        )
    finally:
        engine.dispose()


def _component(state: SystemReadiness, name: str) -> ComponentState:
    return next(component for component in state.components if component.name == name)
