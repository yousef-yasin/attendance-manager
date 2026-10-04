from __future__ import annotations

import datetime as dt
import logging
import sqlite3
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any

from attendance_manager.i18n import tr
from attendance_manager.persistence.schema import MIGRATIONS, SCHEMA_VERSION

log = logging.getLogger(__name__)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def to_db_time(value: dt.datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=dt.timezone.utc)
    return value.astimezone(dt.timezone.utc).isoformat()


def from_db_time(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed


def new_uuid() -> str:
    return str(uuid.uuid4())


class SchemaTooNewError(RuntimeError):
    pass


class Database:
    """Thin wrapper around a SQLite connection with explicit transactions."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path), isolation_level=None, timeout=15)
        self._conn.row_factory = sqlite3.Row
        self._depth = 0
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = FULL")
        self.migrate()

    # ----------------------------------------------------------------- basics
    @property
    def connection(self) -> sqlite3.Connection:
        return self._conn

    def close(self) -> None:
        with suppress(sqlite3.Error):
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        self._conn.close()

    def execute(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def executemany(self, sql: str, rows: Sequence[Sequence[Any]]) -> sqlite3.Cursor:
        return self._conn.executemany(sql, rows)

    def query(self, sql: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[sqlite3.Row]:
        return self._conn.execute(sql, params).fetchall()

    def query_one(
        self, sql: str, params: Sequence[Any] | dict[str, Any] = ()
    ) -> sqlite3.Row | None:
        row: sqlite3.Row | None = self._conn.execute(sql, params).fetchone()
        return row

    @contextmanager
    def transaction(self) -> Iterator[Database]:
        """Atomic unit of work. Nested calls use savepoints."""
        if self._depth == 0:
            self._conn.execute("BEGIN IMMEDIATE")
        else:
            self._conn.execute(f"SAVEPOINT sp{self._depth}")
        self._depth += 1
        try:
            yield self
        except BaseException:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("ROLLBACK")
            else:
                self._conn.execute(f"ROLLBACK TO sp{self._depth}")
                self._conn.execute(f"RELEASE sp{self._depth}")
            raise
        else:
            self._depth -= 1
            if self._depth == 0:
                self._conn.execute("COMMIT")
            else:
                self._conn.execute(f"RELEASE sp{self._depth}")

    # ------------------------------------------------------------- migrations
    @property
    def schema_version(self) -> int:
        return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> None:
        current = self.schema_version
        if current > SCHEMA_VERSION:
            raise SchemaTooNewError(tr("errors.schema_too_new_detail", schema=current))
        for version in range(current, SCHEMA_VERSION):
            log.info("Applying database migration %d", version + 1)
            script = MIGRATIONS[version]
            self._conn.executescript(
                f"BEGIN;\n{script}\nPRAGMA user_version = {version + 1};\nCOMMIT;"
            )
        self._bootstrap()

    def _bootstrap(self) -> None:
        now = to_db_time(utc_now())
        with self.transaction():
            if self.query_one("SELECT 1 FROM app_meta WHERE key = 'installation_id'") is None:
                self.execute(
                    "INSERT INTO app_meta(key, value) VALUES ('installation_id', ?)", (new_uuid(),)
                )
                self.execute("INSERT INTO app_meta(key, value) VALUES ('created_at', ?)", (now,))
            if self.query_one("SELECT 1 FROM instructors") is None:
                self.execute(
                    "INSERT INTO instructors(uuid, display_name, is_local, created_at, updated_at) "
                    "VALUES (?, '', 1, ?, ?)",
                    (new_uuid(), now, now),
                )

    # ---------------------------------------------------------------- safety
    def integrity_ok(self) -> bool:
        row = self._conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row and row[0] == "ok")

    def backup_to(self, target: Path) -> None:
        """Consistent online copy of the database (safe while the app is running)."""
        target.parent.mkdir(parents=True, exist_ok=True)
        dest = sqlite3.connect(str(target))
        try:
            self._conn.backup(dest)
            dest.execute("PRAGMA journal_mode = DELETE")
        finally:
            dest.close()
