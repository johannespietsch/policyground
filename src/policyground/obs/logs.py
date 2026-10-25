"""JSON-lines logging (D39). One file per service in LOG_DIR, which Alloy tails into Loki.

Every line carries the current request_id (a contextvar set by the API middleware), so a
dashboard spike leads to the logs and a log line leads to its trace. High-cardinality
IDs (request, property, rate plan) belong here and in traces, never in metric labels (D41).
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(os.environ.get("POLICYGROUND_LOG_DIR", Path.home() / "Library/Logs/policyground"))
request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str):
        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        line = {"ts": datetime.now(timezone.utc).isoformat(), "level": record.levelname.lower(),
                "service": self.service, "logger": record.name, "msg": record.getMessage()}
        if rid := request_id.get():
            line["request_id"] = rid
        line.update(getattr(record, "fields", {}))
        if record.exc_info:
            line["exc"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def setup(service: str) -> logging.Logger:
    """Log to LOG_DIR/<service>.jsonl and to stderr (never stdout: a stdio MCP server
    shares this code in M6, and stdout is its transport)."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = JsonFormatter(service)
    root = logging.getLogger()
    root.handlers.clear()
    for h in (logging.FileHandler(LOG_DIR / f"{service}.jsonl"), logging.StreamHandler(sys.stderr)):
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(logging.INFO)
    for noisy in ("httpx", "httpx2", "httpcore", "httpcore2", "sentence_transformers", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logging.getLogger(service)


def event(log: logging.Logger, msg: str, **fields) -> None:
    log.info(msg, extra={"fields": fields})
