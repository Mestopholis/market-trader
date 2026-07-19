from dataclasses import dataclass
from datetime import datetime

from market_trader.options_analysis.fixtures import OptionsFixtureDataset


@dataclass
class VirtualOptionsAnalysisClock:
    current: datetime

    def advance(self, value: datetime) -> datetime:
        if value < self.current:
            raise ValueError("options replay clock cannot move backward")
        self.current = value
        return self.current


def replay_options_analysis(dataset: OptionsFixtureDataset) -> tuple[dict[str, object], ...]:
    return tuple(record for stream in dataset.streams for record in stream)
