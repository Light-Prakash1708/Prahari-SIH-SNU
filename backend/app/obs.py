"""
PRAHARI · logging, request IDs, audit
════════════════════════════════════════════════════════════════════════════
Structured logs with a request id that also comes back in the response header,
so a farmer reporting "it said something went wrong at 11:40" can be traced to
one request without guessing.
"""
from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import uuid
from typing import Any

from .clock import now_iso
from .config import get_settings
from .db import dumps, get_db

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("user_id", default=None)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": now_iso(), "level": record.levelname, "logger": record.name,
            "msg": record.getMessage(), "request_id": request_id_var.get(),
        }
        uid = user_id_var.get()
        if uid:
            payload["user_id"] = uid
        for key, value in record.__dict__.items():
            if key in ("args", "msg", "levelname", "levelno", "pathname", "filename",
                       "module", "exc_info", "exc_text", "stack_info", "lineno",
                       "funcName", "created", "msecs", "relativeCreated", "thread",
                       "threadName", "processName", "process", "name", "taskName"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        rid = request_id_var.get()
        base = f"{now_iso()} {record.levelname:<7} [{rid}] {record.name}: {record.getMessage()}"
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)
        return base


def configure_logging() -> None:
    s = get_settings()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if s.log_json else TextFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, s.log_level.upper(), logging.INFO))
    logging.getLogger("uvicorn.access").handlers = [handler]
    logging.getLogger("uvicorn.access").propagate = False


def new_request_id() -> str:
    return uuid.uuid4().hex[:16]


def audit(action: str, *, entity: str = "", entity_id: str = "",
          user_id: str | None = None, role: str | None = None,
          ip: str | None = None, detail: dict[str, Any] | None = None) -> None:
    """Never raises. An audit write that fails must not fail the request it is
    auditing, but it is logged loudly so the gap is visible."""
    try:
        get_db().execute(
            "INSERT INTO audit_logs (at, request_id, user_id, role, action, entity, entity_id, ip, detail)"
            " VALUES (:at, :rid, :uid, :role, :action, :entity, :eid, :ip, :detail)",
            {"at": now_iso(), "rid": request_id_var.get(), "uid": user_id or user_id_var.get(),
             "role": role, "action": action, "entity": entity, "eid": str(entity_id),
             "ip": ip, "detail": dumps(detail)})
    except Exception:                                   # pragma: no cover - infra
        logging.getLogger("prahari.audit").exception("audit write failed", extra={"action": action})


class Timer:
    def __enter__(self):
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *_):
        self.ms = round((time.perf_counter() - self.t0) * 1000)

    @property
    def elapsed_ms(self) -> int:
        return round((time.perf_counter() - self.t0) * 1000)
