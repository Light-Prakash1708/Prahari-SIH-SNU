"""
PRAHARI · database access
════════════════════════════════════════════════════════════════════════════
One engine, two dialects, identical behaviour.

SQLite runs the local build, the test suite and the offline demo laptop.
PostgreSQL runs the deployment. Nothing above this module knows which is in
use, because the four things that actually differ between them are handled
here:

  · types           the DDL carries {{PLACEHOLDERS}} substituted per dialect
  · auto-increment  INTEGER AUTOINCREMENT vs BIGSERIAL, both with RETURNING id
  · booleans        stored as 0/1 integers in both, so no read ever surprises
  · date arithmetic never done in SQL — see clock.py

Schema changes go in app/schema/NNN_name.sql and are applied once, in order,
recorded in schema_migrations. Nothing mutates the schema at request time.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from .config import Settings, get_settings

log = logging.getLogger("prahari.db")

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"

_SUBSTITUTIONS = {
    "sqlite": {
        "{{PK_SERIAL}}": "INTEGER PRIMARY KEY AUTOINCREMENT",
        "{{BOOL}}": "INTEGER",
        "{{JSON}}": "TEXT",
        "{{TS}}": "TEXT",
        "{{FLOAT}}": "REAL",
    },
    "postgresql": {
        "{{PK_SERIAL}}": "BIGSERIAL PRIMARY KEY",
        "{{BOOL}}": "SMALLINT",
        "{{JSON}}": "TEXT",
        "{{TS}}": "TEXT",
        "{{FLOAT}}": "DOUBLE PRECISION",
    },
}


def _dialect_of(url: str) -> str:
    return "postgresql" if url.startswith(("postgres", "postgresql")) else "sqlite"


def render_ddl(sql: str, dialect: str) -> str:
    for k, v in _SUBSTITUTIONS[dialect].items():
        sql = sql.replace(k, v)
    return sql


def _split_statements(sql: str) -> list[str]:
    """Strip comments, split on semicolons. The DDL has no procedural bodies,
    so a naive split is correct and a parser would be theatre."""
    sql = re.sub(r"--[^\n]*", "", sql)
    return [s.strip() for s in sql.split(";") if s.strip()]


class Database:
    """A thin, explicit wrapper. Every method takes named parameters (:name);
    positional '?' placeholders are refused so the same SQL string works on
    both drivers."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        url = self.settings.database_url
        self.dialect = _dialect_of(url)
        kwargs: dict[str, Any] = {"echo": self.settings.db_echo, "future": True,
                                  "pool_pre_ping": True}
        if self.dialect == "sqlite":
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        else:
            kwargs["pool_size"] = 5
            kwargs["max_overflow"] = 10
        self.engine: Engine = create_engine(url, **kwargs)
        if self.dialect == "sqlite":
            @event.listens_for(self.engine, "connect")
            def _pragmas(dbapi_con, _):
                cur = dbapi_con.cursor()
                cur.execute("PRAGMA foreign_keys=ON")
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA busy_timeout=30000")
                cur.close()
        self._lock = threading.Lock()

    # ── migrations ─────────────────────────────────────────────────────────
    def migrate(self) -> list[str]:
        applied: list[str] = []
        with self.engine.begin() as con:
            con.execute(text(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"))
        with self.engine.begin() as con:
            have = {r[0] for r in con.execute(text("SELECT version FROM schema_migrations"))}
        for path in sorted(SCHEMA_DIR.glob("*.sql")):
            version = path.stem
            if version in have:
                continue
            body = render_ddl(path.read_text(encoding="utf-8"), self.dialect)
            with self.engine.begin() as con:
                for stmt in _split_statements(body):
                    con.execute(text(stmt))
                con.execute(text("INSERT INTO schema_migrations (version, applied_at) "
                                 "VALUES (:v, :a)"),
                            {"v": version, "a": _utc_now()})
            applied.append(version)
            log.info("migration applied", extra={"migration": version})
        return applied

    def migration_state(self) -> list[str]:
        try:
            return [r["version"] for r in self.rows(
                "SELECT version FROM schema_migrations ORDER BY version")]
        except SQLAlchemyError:
            return []

    # ── queries ────────────────────────────────────────────────────────────
    @staticmethod
    def _check(sql: str) -> None:
        if "?" in sql:
            raise ValueError("Use named parameters (:name); '?' is SQLite-only.")

    def rows(self, sql: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        self._check(sql)
        with self.engine.connect() as con:
            res = con.execute(text(sql), params or {})
            return [dict(r) for r in res.mappings()]

    def one(self, sql: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        out = self.rows(sql, params)
        return out[0] if out else None

    def scalar(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        self._check(sql)
        with self.engine.connect() as con:
            return con.execute(text(sql), params or {}).scalar()

    def execute(self, sql: str, params: dict[str, Any] | None = None) -> int:
        self._check(sql)
        with self.engine.begin() as con:
            res = con.execute(text(sql), params or {})
            return res.rowcount if res.rowcount is not None else 0

    def executemany(self, sql: str, seq: Sequence[dict[str, Any]]) -> int:
        if not seq:
            return 0
        self._check(sql)
        with self.engine.begin() as con:
            con.execute(text(sql), list(seq))
            return len(seq)

    def insert_returning_id(self, sql: str, params: dict[str, Any] | None = None) -> Any:
        """INSERT ... RETURNING id — supported by PostgreSQL and SQLite >= 3.35.
        Both are guaranteed by requirements.txt and the Docker base image."""
        self._check(sql)
        if "returning" not in sql.lower():
            sql = sql.rstrip().rstrip(";") + " RETURNING id"
        with self.engine.begin() as con:
            return con.execute(text(sql), params or {}).scalar()

    def health(self) -> dict[str, Any]:
        try:
            self.scalar("SELECT 1")
            return {"ok": True, "dialect": self.dialect}
        except Exception as exc:                       # pragma: no cover - infra
            return {"ok": False, "dialect": self.dialect, "error": str(exc)[:200]}

    def dispose(self) -> None:
        self.engine.dispose()


def _utc_now() -> str:
    from .clock import now_iso
    return now_iso()


# ── JSON column helpers ─────────────────────────────────────────────────────
def dumps(value: Any) -> str | None:
    return None if value is None else json.dumps(value, ensure_ascii=False, default=str)


def loads(value: Any, default: Any = None) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def as_bool(value: Any) -> bool:
    return bool(value) and value not in ("0", 0, "false", "False")


def bit(value: Any) -> int:
    return 1 if value else 0


# ── module-level instance, built once per process ───────────────────────────
_db: Database | None = None
_db_lock = threading.Lock()


def get_db() -> Database:
    global _db
    if _db is None:
        with _db_lock:
            if _db is None:
                _db = Database()
    return _db


def reset_db() -> None:
    """Tests swap DATABASE_URL between modules."""
    global _db
    with _db_lock:
        if _db is not None:
            _db.dispose()
        _db = None
