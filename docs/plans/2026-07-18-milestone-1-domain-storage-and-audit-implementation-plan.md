# Milestone 1 Domain Storage and Audit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the Milestone 1 persistence foundation: SQLite/PostgreSQL-compatible storage, migrations, repositories, UTC domain records, append-only audit events, and backup/restore verification while preserving paper-only behavior.

**Architecture:** The FastAPI backend owns database configuration, SQLAlchemy engine/session setup, Alembic migrations, ORM mappings, and repository classes. Future domain services consume repositories and domain DTOs; they do not import ORM models directly. SQLite remains the local default, with schema choices kept compatible with future PostgreSQL deployment.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy 2.x, Alembic, SQLite, pytest, Ruff, mypy, Docker Compose.

## Source Documents

- Approved spec: `docs/plans/2026-07-18-milestone-1-domain-storage-and-audit-spec.md`
- Roadmap: `docs/development-roadmap.md`
- Existing backend package: `apps/api/src/market_trader/`
- Existing backend tests: `apps/api/tests/`

## Safety Constraints

- Keep `MARKET_TRADER_TRADING_MODE=live` rejected.
- Do not add Schwab credentials, Schwab API setup, broker account access, provider API keys, scanner execution, approval buttons, order submission, or live-mode arming.
- Keep new tests deterministic and network-free.
- Store timestamps in UTC.
- Do not expose raw database URLs through frontend/API responses.
- Use macOS/Linux-compatible shell commands.

---

### Task 1: Add Persistence Dependencies

**Files:**

- Modify: `apps/api/pyproject.toml`

**Step 1: Add SQLAlchemy and Alembic dependencies**

Modify `[project].dependencies`:

```toml
dependencies = [
  "alembic>=1.16,<2",
  "fastapi>=0.116,<1",
  "pydantic-settings>=2.10,<3",
  "sqlalchemy>=2.0,<3",
  "uvicorn[standard]>=0.35,<1",
]
```

**Step 2: Install backend dev dependencies**

Run:

```bash
cd apps/api
python -m pip install -e '.[dev]'
```

Expected: installation exits 0.

**Step 3: Verify existing tests still pass**

Run:

```bash
cd apps/api
pytest tests/test_config.py tests/test_health.py -q
```

Expected: existing tests pass.

**Step 4: Commit**

```bash
git add apps/api/pyproject.toml
git commit -m "chore: add persistence dependencies"
```

---

### Task 2: Add UTC Time and Identifier Helpers

**Files:**

- Create: `apps/api/src/market_trader/domain/__init__.py`
- Create: `apps/api/src/market_trader/domain/time.py`
- Create: `apps/api/src/market_trader/domain/ids.py`
- Create: `apps/api/tests/test_domain_primitives.py`

**Step 1: Write failing tests**

Create `apps/api/tests/test_domain_primitives.py`:

```python
from datetime import UTC, datetime

from market_trader.domain.ids import new_domain_id
from market_trader.domain.time import ensure_utc, utc_now


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    observed = utc_now()

    assert observed.tzinfo is UTC


def test_ensure_utc_rejects_naive_datetime() -> None:
    try:
        ensure_utc(datetime(2026, 7, 18, 12, 0, 0))
    except ValueError as error:
        assert "timezone-aware" in str(error)
    else:
        raise AssertionError("naive datetime was accepted")


def test_new_domain_id_uses_prefixed_uuid_shape() -> None:
    identifier = new_domain_id("evt")

    assert identifier.startswith("evt_")
    assert len(identifier) > len("evt_")
```

**Step 2: Run the failing test**

Run:

```bash
cd apps/api
pytest tests/test_domain_primitives.py -q
```

Expected: fails because `market_trader.domain` does not exist.

**Step 3: Implement helpers**

Create `apps/api/src/market_trader/domain/__init__.py`:

```python
"""Domain primitives for Market Trader."""
```

Create `apps/api/src/market_trader/domain/time.py`:

```python
from datetime import UTC, datetime


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)
```

Create `apps/api/src/market_trader/domain/ids.py`:

```python
from uuid import uuid4


def new_domain_id(prefix: str) -> str:
    if not prefix or "_" in prefix:
        raise ValueError("prefix must be non-empty and must not contain underscores")
    return f"{prefix}_{uuid4().hex}"
```

**Step 4: Verify**

Run:

```bash
cd apps/api
pytest tests/test_domain_primitives.py -q
ruff check src tests
mypy src
```

Expected: tests, Ruff, and mypy pass.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/domain apps/api/tests/test_domain_primitives.py
git commit -m "feat: add domain primitives"
```

---

### Task 3: Add Database Engine and Session Boundary

**Files:**

- Create: `apps/api/src/market_trader/db/__init__.py`
- Create: `apps/api/src/market_trader/db/base.py`
- Create: `apps/api/src/market_trader/db/engine.py`
- Create: `apps/api/src/market_trader/db/session.py`
- Create: `apps/api/tests/test_db_engine.py`

**Step 1: Write failing database tests**

Create `apps/api/tests/test_db_engine.py`:

```python
from pathlib import Path

from sqlalchemy import text

from market_trader.db.engine import create_engine_from_url
from market_trader.db.session import session_scope


def test_sqlite_engine_enables_foreign_keys(tmp_path: Path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'test.db'}")

    with engine.connect() as connection:
        enabled = connection.execute(text("PRAGMA foreign_keys")).scalar_one()

    assert enabled == 1


def test_session_scope_commits_successful_transaction(tmp_path: Path) -> None:
    engine = create_engine_from_url(f"sqlite:///{tmp_path / 'test.db'}")

    with session_scope(engine) as session:
        session.execute(text("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)"))
        session.execute(text("INSERT INTO sample (value) VALUES ('ok')"))

    with engine.connect() as connection:
        value = connection.execute(text("SELECT value FROM sample")).scalar_one()

    assert value == "ok"
```

**Step 2: Run failing tests**

Run:

```bash
cd apps/api
pytest tests/test_db_engine.py -q
```

Expected: fails because `market_trader.db` does not exist.

**Step 3: Implement database helpers**

Create `apps/api/src/market_trader/db/__init__.py`:

```python
"""Database infrastructure."""
```

Create `apps/api/src/market_trader/db/base.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

Create `apps/api/src/market_trader/db/engine.py`:

```python
from sqlalchemy import Engine, create_engine, event


def create_engine_from_url(database_url: str) -> Engine:
    engine = create_engine(database_url, future=True)
    if database_url.startswith("sqlite"):
        _enable_sqlite_foreign_keys(engine)
    return engine


def _enable_sqlite_foreign_keys(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _connection_record) -> None:  # type: ignore[no-untyped-def]
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
```

Create `apps/api/src/market_trader/db/session.py`:

```python
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine
from sqlalchemy.orm import Session


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

**Step 4: Verify**

Run:

```bash
cd apps/api
pytest tests/test_db_engine.py -q
ruff check src tests
mypy src
```

Expected: tests, Ruff, and mypy pass.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/db apps/api/tests/test_db_engine.py
git commit -m "feat: add database session boundary"
```

---

### Task 4: Add ORM Models and Initial Migration

**Files:**

- Create: `apps/api/alembic.ini`
- Create: `apps/api/migrations/env.py`
- Create: `apps/api/migrations/script.py.mako`
- Create: `apps/api/migrations/versions/20260718_0001_domain_storage.py`
- Create: `apps/api/src/market_trader/db/models.py`
- Create: `apps/api/tests/test_migrations.py`

**Step 1: Write migration tests**

Create `apps/api/tests/test_migrations.py`:

```python
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def test_initial_migration_creates_domain_tables(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'migration.db'}"

    command.upgrade(alembic_config(database_url), "head")

    inspector = inspect(create_engine(database_url))
    assert {
        "symbols",
        "instruments",
        "market_data_snapshots",
        "signals",
        "candidates",
        "proposed_trades",
        "approvals",
        "orders",
        "fills",
        "positions",
        "risk_locks",
        "journal_events",
        "configuration_versions",
    }.issubset(set(inspector.get_table_names()))
```

**Step 2: Run failing migration test**

Run:

```bash
cd apps/api
pytest tests/test_migrations.py -q
```

Expected: fails because Alembic configuration and migrations do not exist.

**Step 3: Add Alembic configuration**

Create `apps/api/alembic.ini` with local defaults:

```ini
[alembic]
script_location = migrations
prepend_sys_path = src
sqlalchemy.url = sqlite:///./data/market_trader.db

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Create `apps/api/migrations/env.py`:

```python
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from market_trader.db.base import Base
from market_trader.db import models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Create `apps/api/migrations/script.py.mako` using Alembic's standard template.

**Step 4: Add ORM model definitions**

Create `apps/api/src/market_trader/db/models.py`. Use SQLAlchemy 2.0 mapped
classes with string IDs, UTC datetime columns, JSON payload columns, and foreign
keys. Include all tables named in the migration test. Keep enum values as strings
for portability.

Minimum model pattern:

```python
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from market_trader.db.base import Base


class JournalEventORM(Base):
    __tablename__ = "journal_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    actor_type: Mapped[str] = mapped_column(String(40))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    subject_type: Mapped[str] = mapped_column(String(80), index=True)
    subject_id: Mapped[str] = mapped_column(String(64), index=True)
    causation_event_id: Mapped[str | None] = mapped_column(
        ForeignKey("journal_events.id"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    schema_version: Mapped[int]
```

Follow the same style for:

- `SymbolORM`
- `InstrumentORM`
- `MarketDataSnapshotORM`
- `SignalORM`
- `CandidateORM`
- `ProposedTradeORM`
- `ApprovalORM`
- `OrderORM`
- `FillORM`
- `PositionORM`
- `RiskLockORM`
- `ConfigurationVersionORM`

**Step 5: Add initial migration**

Create `apps/api/migrations/versions/20260718_0001_domain_storage.py`. The
migration must create the same tables and indexes as the ORM models. Add SQLite
triggers on `journal_events` to abort direct updates and deletes:

```sql
CREATE TRIGGER journal_events_no_update
BEFORE UPDATE ON journal_events
BEGIN
  SELECT RAISE(ABORT, 'journal_events are append-only');
END;
```

```sql
CREATE TRIGGER journal_events_no_delete
BEFORE DELETE ON journal_events
BEGIN
  SELECT RAISE(ABORT, 'journal_events are append-only');
END;
```

Use conditional dialect checks if PostgreSQL-specific trigger syntax is added
later. For Milestone 1, SQLite trigger coverage is required.

**Step 6: Verify**

Run:

```bash
cd apps/api
pytest tests/test_migrations.py -q
alembic upgrade head
ruff check src tests
mypy src
```

Expected: migration test passes, local migration reaches head, Ruff and mypy pass.

**Step 7: Commit**

```bash
git add apps/api/alembic.ini apps/api/migrations apps/api/src/market_trader/db/models.py apps/api/tests/test_migrations.py
git commit -m "feat: add domain storage migration"
```

---

### Task 5: Add Audit Repository

**Files:**

- Create: `apps/api/src/market_trader/repositories/__init__.py`
- Create: `apps/api/src/market_trader/repositories/audit.py`
- Create: `apps/api/tests/test_audit_repository.py`

**Step 1: Write failing tests**

Create `apps/api/tests/test_audit_repository.py`:

```python
from pathlib import Path

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from tests.test_migrations import alembic_config
from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


def migrated_engine(tmp_path: Path):
    database_url = f"sqlite:///{tmp_path / 'audit.db'}"
    command.upgrade(alembic_config(database_url), "head")
    return create_engine(database_url)


def test_appends_and_fetches_journal_event_by_correlation_id(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)

    with Session(engine) as session:
        repo = AuditRepository(session)
        event = repo.append(
            AuditEventCreate(
                correlation_id="corr_1",
                event_type="symbol.created",
                actor_type="system",
                occurred_at=utc_now(),
                subject_type="symbol",
                subject_id="sym_1",
                payload={"schema_version": 1, "symbol": "SPY"},
                schema_version=1,
            )
        )
        session.commit()

    with Session(engine) as session:
        events = AuditRepository(session).list_by_correlation_id("corr_1")

    assert [stored.id for stored in events] == [event.id]


def test_journal_events_reject_direct_update_and_delete(tmp_path: Path) -> None:
    engine = migrated_engine(tmp_path)

    with Session(engine) as session:
        event = AuditRepository(session).append(
            AuditEventCreate(
                correlation_id="corr_2",
                event_type="symbol.created",
                actor_type="system",
                occurred_at=utc_now(),
                subject_type="symbol",
                subject_id="sym_2",
                payload={"schema_version": 1},
                schema_version=1,
            )
        )
        session.commit()

    with engine.begin() as connection:
        with pytest.raises(IntegrityError):
            connection.execute(
                text("UPDATE journal_events SET event_type = 'changed' WHERE id = :id"),
                {"id": event.id},
            )

        with pytest.raises(IntegrityError):
            connection.execute(
                text("DELETE FROM journal_events WHERE id = :id"),
                {"id": event.id},
            )
```

**Step 2: Run failing tests**

Run:

```bash
cd apps/api
pytest tests/test_audit_repository.py -q
```

Expected: fails because audit repository does not exist.

**Step 3: Implement audit repository**

Create `apps/api/src/market_trader/repositories/__init__.py`:

```python
"""Repository boundaries for persisted domain records."""
```

Create `apps/api/src/market_trader/repositories/audit.py` with:

- `AuditEventCreate` dataclass.
- `AuditEvent` frozen dataclass.
- `AuditRepository.append`.
- `AuditRepository.get`.
- `AuditRepository.list_by_correlation_id`.
- `AuditRepository.list_by_subject`.

Use `new_domain_id("evt")` for event IDs and `ensure_utc` for timestamps.

**Step 4: Verify**

Run:

```bash
cd apps/api
pytest tests/test_audit_repository.py -q
ruff check src tests
mypy src
```

Expected: tests, Ruff, and mypy pass.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/repositories apps/api/tests/test_audit_repository.py
git commit -m "feat: add append-only audit repository"
```

---

### Task 6: Add Symbol, Instrument, and Configuration Repositories

**Files:**

- Create: `apps/api/src/market_trader/repositories/symbols.py`
- Create: `apps/api/src/market_trader/repositories/config_versions.py`
- Create: `apps/api/tests/test_symbol_repository.py`
- Create: `apps/api/tests/test_config_version_repository.py`

**Step 1: Write failing repository tests**

Test behavior:

- Create a symbol with metadata payload and audit correlation ID.
- Fetch symbol by display symbol.
- Create an instrument linked to the symbol.
- Create a configuration version with content hash and immutable payload.
- Fetch active configuration version by key.

**Step 2: Run failing tests**

Run:

```bash
cd apps/api
pytest tests/test_symbol_repository.py tests/test_config_version_repository.py -q
```

Expected: fails because repositories do not exist.

**Step 3: Implement repositories**

Implement explicit dataclasses and repository methods. Required methods:

- `SymbolRepository.create_symbol`
- `SymbolRepository.get_symbol_by_display_symbol`
- `SymbolRepository.create_instrument`
- `SymbolRepository.get_instruments_for_symbol`
- `ConfigurationVersionRepository.create`
- `ConfigurationVersionRepository.get_active_by_key`

Every create method must accept a `correlation_id`. If it writes an auditable
record, it must append a journal event in the same transaction.

**Step 4: Verify**

Run:

```bash
cd apps/api
pytest tests/test_symbol_repository.py tests/test_config_version_repository.py -q
ruff check src tests
mypy src
```

Expected: tests, Ruff, and mypy pass.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/repositories/symbols.py apps/api/src/market_trader/repositories/config_versions.py apps/api/tests/test_symbol_repository.py apps/api/tests/test_config_version_repository.py
git commit -m "feat: add symbol and configuration repositories"
```

---

### Task 7: Add Decision and Market Data Repositories

**Files:**

- Create: `apps/api/src/market_trader/repositories/market_data.py`
- Create: `apps/api/src/market_trader/repositories/decisions.py`
- Create: `apps/api/tests/test_market_data_repository.py`
- Create: `apps/api/tests/test_decision_repositories.py`

**Step 1: Write failing tests**

Test behavior:

- Store a market-data snapshot with source, observed time, ingested time,
  session date, quality state, config version reference, immutable payload, and
  correlation ID.
- Fetch snapshots by symbol/source/time range.
- Create a signal linked to a symbol and input snapshot.
- Create a candidate linked to a signal.
- Fetch candidate by ID and verify explanation payload and correlation ID.

**Step 2: Run failing tests**

Run:

```bash
cd apps/api
pytest tests/test_market_data_repository.py tests/test_decision_repositories.py -q
```

Expected: fails because repositories do not exist.

**Step 3: Implement repositories**

Implement:

- `MarketDataRepository.store_snapshot`
- `MarketDataRepository.list_snapshots`
- `DecisionRepository.create_signal`
- `DecisionRepository.create_candidate`
- `DecisionRepository.get_candidate`

All writes must use explicit transactions supplied by the caller's session and
append journal events in the same session.

**Step 4: Verify**

Run:

```bash
cd apps/api
pytest tests/test_market_data_repository.py tests/test_decision_repositories.py -q
ruff check src tests
mypy src
```

Expected: tests, Ruff, and mypy pass.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/repositories/market_data.py apps/api/src/market_trader/repositories/decisions.py apps/api/tests/test_market_data_repository.py apps/api/tests/test_decision_repositories.py
git commit -m "feat: add market data and decision repositories"
```

---

### Task 8: Add Trade Lifecycle and Risk Lock Repositories

**Files:**

- Create: `apps/api/src/market_trader/repositories/orders.py`
- Create: `apps/api/src/market_trader/repositories/risk_locks.py`
- Create: `apps/api/tests/test_trade_lifecycle_repositories.py`
- Create: `apps/api/tests/test_risk_lock_repository.py`

**Step 1: Write failing tests**

Test behavior:

- Create proposed trade, approval, order, fill, and position records without any
  broker endpoint.
- Verify simulated/broker reference fields can remain null.
- Verify order/fill/position records share a correlation ID.
- Create, fetch, and clear a risk lock.
- Verify clearing a risk lock records a clearing audit event.

**Step 2: Run failing tests**

Run:

```bash
cd apps/api
pytest tests/test_trade_lifecycle_repositories.py tests/test_risk_lock_repository.py -q
```

Expected: fails because repositories do not exist.

**Step 3: Implement repositories**

Implement explicit create/fetch methods only. Do not add submit, preview, cancel,
broker, provider, or live-mode behavior.

Required methods:

- `TradeLifecycleRepository.create_proposed_trade`
- `TradeLifecycleRepository.create_approval`
- `TradeLifecycleRepository.create_order_record`
- `TradeLifecycleRepository.create_fill_record`
- `TradeLifecycleRepository.create_position_record`
- `RiskLockRepository.create`
- `RiskLockRepository.clear`
- `RiskLockRepository.get_active`

**Step 4: Verify**

Run:

```bash
cd apps/api
pytest tests/test_trade_lifecycle_repositories.py tests/test_risk_lock_repository.py -q
ruff check src tests
mypy src
```

Expected: tests, Ruff, and mypy pass.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/repositories/orders.py apps/api/src/market_trader/repositories/risk_locks.py apps/api/tests/test_trade_lifecycle_repositories.py apps/api/tests/test_risk_lock_repository.py
git commit -m "feat: add stored trade lifecycle records"
```

---

### Task 9: Add Database Initialization and Backup/Restore Fixture

**Files:**

- Create: `apps/api/src/market_trader/db/migrations.py`
- Create: `apps/api/src/market_trader/db/backup.py`
- Create: `apps/api/tests/test_backup_restore.py`
- Modify: `scripts/verify-foundation.sh`

**Step 1: Write failing backup/restore test**

Create `apps/api/tests/test_backup_restore.py`:

```python
from pathlib import Path

from alembic import command
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from tests.test_migrations import alembic_config
from market_trader.db.backup import backup_sqlite_database, restore_sqlite_database
from market_trader.domain.time import utc_now
from market_trader.repositories.audit import AuditEventCreate, AuditRepository


def test_sqlite_backup_restore_preserves_audit_events(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    restored = tmp_path / "restored.db"
    backup = tmp_path / "backup.db"
    database_url = f"sqlite:///{source}"
    command.upgrade(alembic_config(database_url), "head")

    engine = create_engine(database_url)
    with Session(engine) as session:
        AuditRepository(session).append(
            AuditEventCreate(
                correlation_id="corr_restore",
                event_type="fixture.created",
                actor_type="system",
                occurred_at=utc_now(),
                subject_type="fixture",
                subject_id="fixture_1",
                payload={"schema_version": 1},
                schema_version=1,
            )
        )
        session.commit()

    backup_sqlite_database(source, backup)
    restore_sqlite_database(backup, restored)

    restored_engine = create_engine(f"sqlite:///{restored}")
    with Session(restored_engine) as session:
        events = AuditRepository(session).list_by_correlation_id("corr_restore")

    assert len(events) == 1
```

**Step 2: Run failing test**

Run:

```bash
cd apps/api
pytest tests/test_backup_restore.py -q
```

Expected: fails because backup helpers do not exist.

**Step 3: Implement migration and backup helpers**

Create `apps/api/src/market_trader/db/migrations.py`:

```python
from alembic import command
from alembic.config import Config


def alembic_config(database_url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
```

Create `apps/api/src/market_trader/db/backup.py`:

```python
from pathlib import Path
from shutil import copy2


def backup_sqlite_database(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy2(source, destination)


def restore_sqlite_database(backup: Path, destination: Path) -> None:
    if not backup.exists():
        raise FileNotFoundError(backup)
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy2(backup, destination)
```

**Step 4: Update foundation verification**

Modify `scripts/verify-foundation.sh` to keep existing checks and, if the API
container exposes a database health state later, verify that it is healthy. Do
not expose or print the database URL.

**Step 5: Verify**

Run:

```bash
cd apps/api
pytest tests/test_backup_restore.py -q
ruff check src tests
mypy src
```

Expected: tests, Ruff, and mypy pass.

**Step 6: Commit**

```bash
git add apps/api/src/market_trader/db/migrations.py apps/api/src/market_trader/db/backup.py apps/api/tests/test_backup_restore.py scripts/verify-foundation.sh
git commit -m "feat: add local database backup restore fixture"
```

---

### Task 10: Add Optional Database Health State

**Files:**

- Modify: `apps/api/src/market_trader/api/health.py`
- Modify: `apps/api/tests/test_health.py`

**Step 1: Write failing health test**

Modify `apps/api/tests/test_health.py` to expect a coarse database state:

```python
def test_health_reports_database_state_without_database_url() -> None:
    response = TestClient(app).get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["database"] in {"ok", "unavailable"}
    assert "database_url" not in response.text
    assert "sqlite:///" not in response.text
```

**Step 2: Run failing test**

Run:

```bash
cd apps/api
pytest tests/test_health.py -q
```

Expected: fails because `database` is not in the response.

**Step 3: Implement coarse database health**

Modify `HealthResponse` to include:

```python
database: Literal["ok", "unavailable"]
```

In `health()`, create an engine from `settings.database_url`, run `SELECT 1`,
and return `"ok"` on success or `"unavailable"` on failure. Do not include raw
exception text in the response.

**Step 4: Verify**

Run:

```bash
cd apps/api
pytest tests/test_health.py -q
ruff check src tests
mypy src
```

Expected: health tests, Ruff, and mypy pass.

**Step 5: Commit**

```bash
git add apps/api/src/market_trader/api/health.py apps/api/tests/test_health.py
git commit -m "feat: report coarse database health"
```

---

### Task 11: Update Documentation

**Files:**

- Modify: `README.md`
- Create: `docs/milestone-1-storage.md`

**Step 1: Add local storage documentation**

Create `docs/milestone-1-storage.md` covering:

- Paper-only boundary.
- Local SQLite default.
- How to run migrations on macOS/Linux:

```bash
cd apps/api
alembic upgrade head
```

- How to run repository and migration tests:

```bash
cd apps/api
pytest tests/test_migrations.py tests/test_audit_repository.py -q
```

- How to reset local development data:

```bash
docker compose down
docker volume rm market-trader_market-trader-data
docker compose up --build -d
```

- Backup/restore fixture behavior.
- Explicitly state that Schwab setup, provider keys, scanner behavior,
  approvals, and orders remain unavailable.

**Step 2: Link docs from README**

Add a short Milestone 1 storage section to `README.md` linking to
`docs/milestone-1-storage.md`.

**Step 3: Verify**

Run:

```bash
rg "Schwab|paper-only|alembic upgrade head|market-trader-data" README.md docs/milestone-1-storage.md
```

Expected: docs contain the expected safety and setup text.

**Step 4: Commit**

```bash
git add README.md docs/milestone-1-storage.md
git commit -m "docs: document milestone 1 storage workflow"
```

---

### Task 12: Final Verification

**Files:**

- Review all Milestone 1 files changed by prior tasks.

**Step 1: Run backend verification**

Run:

```bash
cd apps/api
pytest -q
ruff check src tests
mypy src
```

Expected: all backend tests and static checks pass.

**Step 2: Run frontend verification if health contract changed**

Run:

```bash
cd apps/web
npm test -- --run
npm run build
npm run lint
```

Expected: frontend tests, build, and lint pass. If the frontend health type needs
the new `database` field, update `apps/web/src/api.ts`, `apps/web/src/App.tsx`,
and `apps/web/src/App.test.tsx`, then rerun these commands.

**Step 3: Run Docker Compose verification**

Run:

```bash
cp .env.example .env
docker compose up --build -d
./scripts/verify-foundation.sh
docker compose down
```

Expected: foundation verification passes and still reports paper mode.

**Step 4: Check safety exclusions**

Run:

```bash
rg -i "schwab|oauth|broker|submit|live" apps docs README.md
```

Expected: only roadmap/spec/documentation exclusions or existing paper-only live-mode rejection appear. No credential setup, provider integration, broker submission, or live-order path is introduced.

**Step 5: Final commit**

If any verification fixes were required:

```bash
git add .
git commit -m "test: verify milestone 1 storage foundation"
```

**Step 6: Report completion evidence**

Report exact commands run, pass/fail status, any skipped commands, and remaining
risk. Do not claim Milestone 1 is complete unless every acceptance criterion in
the approved spec is satisfied.

