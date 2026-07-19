from datetime import datetime

from market_trader.options_analysis.fixtures import OptionsFixtureDataset
from market_trader.options_analysis.replay import (
    VirtualOptionsAnalysisClock,
    replay_options_analysis,
)


def test_virtual_clock_cannot_move_backward() -> None:
    clock = VirtualOptionsAnalysisClock(datetime(2026, 8, 14, 14, 0))
    assert clock.advance(datetime(2026, 8, 14, 15, 0)).hour == 15


def test_replay_preserves_dataset_stream_order() -> None:
    dataset = OptionsFixtureDataset("unit", (({"id": "first"},), ({"id": "second"},)), {})
    assert replay_options_analysis(dataset) == ({"id": "first"}, {"id": "second"})
