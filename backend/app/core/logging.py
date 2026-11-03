from __future__ import annotations

import json
import logging
import sys

from app.core.config import get_settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def configure_logging() -> None:
    s = get_settings()
    root = logging.getLogger()
    if getattr(root, "_age_configured", False):
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if s.is_production else logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if s.debug else logging.INFO)
    for noisy in ("httpx", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._age_configured = True  # type: ignore[attr-defined]
