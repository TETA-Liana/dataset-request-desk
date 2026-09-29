"""Structured logging: every log line is one JSON object, easy to search in any log tool."""
import json
import logging
import sys
from datetime import datetime, timezone

from app.config import LOG_LEVEL


class JsonFormatter(logging.Formatter):
    def format(self, record):
        line = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # anything passed with logger.info("...", extra={"fields": {...}})
        line.update(getattr(record, "fields", {}))
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info)
        return json.dumps(line)


def setup_logging():
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(LOG_LEVEL)
    # uvicorn prints its own access line; ours replaces it, so turn theirs off
    logging.getLogger("uvicorn.access").disabled = True
