from pathlib import Path

from market_trader.risk.cli import main


def test_cli_validate_and_evaluate_emit_json(capsys) -> None:  # type: ignore[no-untyped-def]
    path = Path("fixtures/risk/share-sizing-boundaries/approved-share.json")

    assert main(["validate", str(path)]) == 0
    assert '"valid": true' in capsys.readouterr().out

    assert main(["evaluate", str(path)]) == 0
    output = capsys.readouterr().out
    assert '"status": "approved"' in output
    assert '"result_digest":' in output
