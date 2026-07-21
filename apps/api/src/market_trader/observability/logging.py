import json
import logging as std_logging
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from market_trader.observability.redaction import redact_value

LOGGER_NAME = "market_trader.observability"
_logger = std_logging.getLogger(LOGGER_NAME)


def log_structured_event(event: Mapping[str, Any], *, level: int = std_logging.INFO) -> None:
    payload = {
        "timestamp": datetime.now(UTC).isoformat(),
        **dict(event),
    }
    _logger.log(
        level,
        json.dumps(
            redact_value(payload),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
    )
