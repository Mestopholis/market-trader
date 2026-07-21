from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy.orm import Session

from market_trader.db.engine import create_engine_from_url
from market_trader.recovery.restart import run_restart_recovery_drill


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local restart recovery drill")
    parser.add_argument("database", type=Path)
    parser.add_argument("--correlation-id", default="corr-recovery-drill")
    args = parser.parse_args()

    engine = create_engine_from_url(f"sqlite:///{args.database}")
    try:
        with Session(engine) as session:
            report = run_restart_recovery_drill(
                session,
                correlation_id=args.correlation_id,
            )
        print(report.model_dump_json(indent=2))
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
