from pathlib import Path


def test_options_analysis_migration_defines_append_only_tables() -> None:
    migration = Path("migrations/versions/20260719_0005_options_analysis.py").read_text()
    for table in (
        "options_analysis_runs",
        "option_contract_evaluations",
        "option_spread_candidates",
        "option_spread_warnings",
    ):
        assert table in migration
    assert "{table}_no_{operation}" in migration
    assert "_create_append_only_triggers(table)" in migration
