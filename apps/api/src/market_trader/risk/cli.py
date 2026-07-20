from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from market_trader.risk.fixtures import load_risk_fixture
from market_trader.risk.replay import replay_risk_fixture


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="risk")
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("fixture")
    evaluate = subparsers.add_parser("evaluate")
    evaluate.add_argument("fixture")
    args = parser.parse_args(argv)

    if args.command == "validate":
        fixture = load_risk_fixture(args.fixture)
        print(
            json.dumps(
                {
                    "fixture_key": fixture.fixture_key,
                    "valid": True,
                },
                sort_keys=True,
            )
        )
        return 0
    result = replay_risk_fixture(args.fixture)
    print(
        json.dumps(
            {
                "fixture_key": result.fixture.fixture_key,
                "result_digest": result.decision.result_digest,
                "status": result.decision.status.value,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
