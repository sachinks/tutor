"""JSON logs on stdout (one object per line), each with the request ID.

Never log message text, prompts, replies or anything a student wrote: log IDs, sizes, timings and outcomes.
Hosted platforms collect stdout, so the service writes no log files.
"""

import json
import logging
import logging.config
from datetime import UTC, datetime
from typing import Any

from .request_context import get_request_id

_STANDARD = set(vars(logging.LogRecord("x", 0, "", 0, "", None, None))) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_request_id(),
        }
        for key, value in vars(record).items():  # structured extras: logger.info("...", extra={"chunks": 4})
            if key not in _STANDARD and key != "request_id":
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {"json": {"()": JsonFormatter}},
            "handlers": {
                "stdout": {"class": "logging.StreamHandler", "formatter": "json", "stream": "ext://sys.stdout"}
            },
            "root": {"handlers": ["stdout"], "level": level},
            "loggers": {
                "uvicorn.access": {"level": "WARNING"},  # our middleware logs one line per request instead
                "httpx": {"level": "WARNING"},
                "sqlalchemy.engine": {"level": "WARNING"},
            },
        }
    )
