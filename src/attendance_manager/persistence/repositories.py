"""Repositories: the only place that knows SQL. Services call these inside transactions."""

from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import asdict
from typing import Any

from attendance_manager.domain.errors import NotFoundError
from attendance_manager.domain.models import (
    AttendanceRecord,
    AttendanceSession,
    AttendanceStatus,
    Course,
    CourseStatus,
    RosterImport,
    SessionParticipant,
    SessionStatus,
    StoredFile,
    Student,
)
from attendance_manager.importing.detection import ColumnMapping
from attendance_manager.persistence.database import (
    Database,
    from_db_time,
    new_uuid,
    to_db_time,
    utc_now,
)


def _now() -> str:
    return to_db_time(utc_now())


def _dt(value: str | None) -> dt.datetime:
    parsed = from_db_time(value)
    assert parsed is not None
    return parsed


def mapping_to_json(mapping: ColumnMapping) -> str:
    return json.dumps(asdict(mapping))


def mapping_from_json(text: str) -> ColumnMapping:
    return ColumnMapping(**json.loads(text))


class CourseRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _row(row: sqlite3.Row) -> Course:
        return Course(
            id=row["id"],
            uuid=row["uuid"],
            name=row["name"],
            section=row["section"],
            semester=row["semester"],
            year=row["year"],
            notes=row["notes"],
            status=CourseStatus(row["status"]),
            created_at=_dt(row["created_at"]),
            updated_at=_dt(row["updated_at"]),
        )

    def default_instructor_id(self) -> int:
        row = self.db.query_one("SELECT id FROM instructors ORDER BY id LIMIT 1")
        assert row is not None
        return int(row["id"])

    def add(self, name: str, section: str, semester: str, year: str, notes: str = "") -> int:
        now = _now()
        cur = self.db.execute(
            "INSERT INTO courses(uuid, instructor_id, name, section, semester, year, notes, status, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)",
            (
                new_uuid(),
                self.default_instructor_id(),
                name,
                section,
                semester,
                year,
                notes,
                now,
                now,
            ),
        )
        return int(cur.lastrowid or 0)

    def update(
        self, course_id: int, name: str, section: str, semester: str, year: str, notes: str
    ) -> None:
        self.db.execute(
            "UPDATE courses SET name=?, section=?, semester=?, year=?, notes=?, updated_at=?, "
            "revision = revision + 1 WHERE id=?",
            (name, section, semester, year, notes, _now(), course_id),
        )

    def set_status(self, course_id: int, status: CourseStatus) -> None:
        self.db.execute(
            "UPDATE courses SET status=?, updated_at=?, revision = revision + 1 WHERE id=?",
            (status.value, _now(), course_id),
        )

    def get(self, course_id: int) -> Course:
        row = self.db.query_one("SELECT * FROM courses WHERE id=?", (course_id,))
        if row is None:
            raise NotFoundError("This course no longer exists.")
        return self._row(row)

    def all(self, include_archived: bool = True) -> list[Course]:
        sql = "SELECT * FROM courses"
        if not include_archived:
            sql += " WHERE status='active'"
        sql += " ORDER BY status='archived', lower(name), section"
        return [self._row(r) for r in self.db.query(sql)]

    def find_duplicate(
        self, name: str, section: str, semester: str, year: str, exclude_id: int | None = None
    ) -> Course | None:
        row = self.db.query_one(
            "SELECT * FROM courses WHERE lower(trim(name))=lower(trim(?)) AND lower(trim(section))=lower(trim(?)) "
            "AND lower(trim(semester))=lower(trim(?)) AND trim(year)=trim(?) AND id IS NOT ?",
            (name, section, semester, year, exclude_id),
        )
        return self._row(row) if row else None

    def delete(self, course_id: int) -> None:
        # Children first (records reference students and sessions).
        self.db.execute(
            "DELETE FROM attendance_records WHERE session_id IN (SELECT id FROM sessions WHERE course_id=?)",
            (course_id,),
        )
        self.db.execute(
            "DELETE FROM session_participants WHERE session_id IN (SELECT id FROM sessions WHERE course_id=?)",
            (course_id,),
        )
        self.db.execute("DELETE FROM sessions WHERE course_id=?", (course_id,))
        self.db.execute(
            "UPDATE students SET first_import_id=NULL, last_import_id=NULL WHERE course_id=?",
            (course_id,),
        )
        self.db.execute("DELETE FROM students WHERE course_id=?", (course_id,))
        self.db.execute("DELETE FROM roster_imports WHERE course_id=?", (course_id,))
        self.db.execute("DELETE FROM courses WHERE id=?", (course_id,))

    def counts(self, course_id: int) -> tuple[int, int]:
        row = self.db.query_one(
            "SELECT (SELECT COUNT(*) FROM students WHERE course_id=:c AND is_active=1) AS students, "
            "(SELECT COUNT(*) FROM sessions WHERE course_id=:c AND status='active') AS sessions",
            {"c": course_id},
        )
        assert row is not None
        return int(row["students"]), int(row["sessions"])


class FileRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _row(row: sqlite3.Row) -> StoredFile:
        return StoredFile(
            id=row["id"],
            sha256=row["sha256"],
            original_filename=row["original_filename"],
            relative_path=row["relative_path"],
            size_bytes=row["size_bytes"],
            stored_at=_dt(row["stored_at"]),
        )

    def add(self, sha256: str, original_filename: str, relative_path: str, size_bytes: int) -> int:
        cur = self.db.execute(
            "INSERT INTO stored_files(uuid, sha256, original_filename, relative_path, size_bytes, stored_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (new_uuid(), sha256, original_filename, relative_path, size_bytes, _now()),
        )
        return int(cur.lastrowid or 0)

    def get(self, file_id: int) -> StoredFile:
        row = self.db.query_one("SELECT * FROM stored_files WHERE id=?", (file_id,))
        if row is None:
            raise NotFoundError("The stored file record is missing.")
        return self._row(row)

    def all(self) -> list[StoredFile]:
        return [self._row(r) for r in self.db.query("SELECT * FROM stored_files ORDER BY id")]


class RosterImportRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def add(
        self,
        course_id: int,
        file_id: int,
        mapping: ColumnMapping,
        student_count: int,
        added: int,
        updated: int,
        deactivated: int,
    ) -> int:
        cur = self.db.execute(
            "INSERT INTO roster_imports(uuid, course_id, file_id, imported_at, column_mapping, student_count, "
            "added_count, updated_count, deactivated_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                new_uuid(),
                course_id,
                file_id,
                _now(),
                mapping_to_json(mapping),
                student_count,
                added,
                updated,
                deactivated,
            ),
        )
        return int(cur.lastrowid or 0)

    def for_course(self, course_id: int) -> list[RosterImport]:
        rows = self.db.query(
            "SELECT r.*, f.original_filename FROM roster_imports r JOIN stored_files f ON f.id = r.file_id "
            "WHERE r.course_id=? ORDER BY r.id",
            (course_id,),
        )
        return [
            RosterImport(
                id=r["id"],
                course_id=r["course_id"],
                file_id=r["file_id"],
                original_filename=r["original_filename"],
                imported_at=_dt(r["imported_at"]),
                student_count=r["student_count"],
                added_count=r["added_count"],
                updated_count=r["updated_count"],
                deactivated_count=r["deactivated_count"],
            )
            for r in rows
        ]

    def file_hashes(self, course_id: int) -> set[str]:
        rows = self.db.query(
            "SELECT f.sha256 FROM roster_imports r JOIN stored_files f ON f.id=r.file_id WHERE r.course_id=?",
            (course_id,),
        )
        return {r["sha256"] for r in rows}


class StudentRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    @staticmethod
    def _row(row: sqlite3.Row) -> Student:
        return Student(
            id=row["id"],
            course_id=row["course_id"],
            student_key=row["student_key"],
            student_number=row["student_number"],
            full_name=row["full_name"],
            info=json.loads(row["info_json"] or "{}"),
            roster_position=row["roster_position"],
            is_active=bool(row["is_active"]),
        )

    def add(
        self,
        course_id: int,
        key: str,
        number: str,
        name: str,
        info: dict[str, str],
        position: int,
        import_id: int,
    ) -> int:
        now = _now()
        cur = self.db.execute(
            "INSERT INTO students(uuid, course_id, student_key, student_number, full_name, info_json, "
            "roster_position, is_active, first_import_id, last_import_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)",
            (
                new_uuid(),
                course_id,
                key,
                number,
                name,
                json.dumps(info, ensure_ascii=False),
                position,
                import_id,
                import_id,
                now,
                now,
            ),
        )
        return int(cur.lastrowid or 0)

    def update_from_roster(
        self,
        student_id: int,
        number: str,
        name: str,
        info: dict[str, str],
        position: int,
        import_id: int,
    ) -> None:
        self.db.execute(
            "UPDATE students SET student_number=?, full_name=?, info_json=?, roster_position=?, is_active=1, "
            "last_import_id=?, updated_at=?, revision = revision + 1 WHERE id=?",
            (
                number,
                name,
                json.dumps(info, ensure_ascii=False),
                position,
                import_id,
                _now(),
                student_id,
            ),
        )

    def set_active(self, student_id: int, active: bool) -> None:
        self.db.execute(
            "UPDATE students SET is_active=?, updated_at=?, revision = revision + 1 WHERE id=?",
            (1 if active else 0, _now(), student_id),
        )

    def for_course(self, course_id: int, active_only: bool = False) -> list[Student]:
        sql = "SELECT * FROM students WHERE course_id=?"
        if active_only:
            sql += " AND is_active=1"
        sql += " ORDER BY is_active DESC, roster_position, id"
        return [self._row(r) for r in self.db.query(sql, (course_id,))]

    def get(self, student_id: int) -> Student:
        row = self.db.query_one("SELECT * FROM students WHERE id=?", (student_id,))
        if row is None:
            raise NotFoundError("This student no longer exists.")
        return self._row(row)


class SessionRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    _SELECT = "SELECT s.*, f.original_filename, f.sha256 FROM sessions s JOIN stored_files f ON f.id = s.file_id"

    @staticmethod
    def _row(row: sqlite3.Row) -> AttendanceSession:
        return AttendanceSession(
            id=row["id"],
            uuid=row["uuid"],
            course_id=row["course_id"],
            session_number=row["session_number"],
            title=row["title"],
            session_date=dt.date.fromisoformat(row["session_date"]),
            original_filename=row["original_filename"],
            file_id=row["file_id"],
            file_sha256=row["sha256"],
            uploaded_at=_dt(row["uploaded_at"]),
            present_count=row["present_count"],
            absent_count=row["absent_count"],
            unmatched_count=row["unmatched_count"],
            status=SessionStatus(row["status"]),
            removed_at=from_db_time(row["removed_at"]),
            removed_reason=row["removed_reason"],
            metadata=json.loads(row["metadata_json"] or "{}"),
        )

    def next_number(self, course_id: int) -> int:
        row = self.db.query_one(
            "SELECT COALESCE(MAX(session_number), 0) + 1 AS n FROM sessions WHERE course_id=?",
            (course_id,),
        )
        assert row is not None
        return int(row["n"])

    def add(
        self,
        course_id: int,
        number: int,
        title: str,
        date: dt.date,
        file_id: int,
        mapping: ColumnMapping,
        metadata: dict[str, str],
        present: int,
        absent: int,
        unmatched: int,
    ) -> int:
        cur = self.db.execute(
            "INSERT INTO sessions(uuid, course_id, session_number, title, session_date, file_id, uploaded_at, "
            "column_mapping, metadata_json, present_count, absent_count, unmatched_count, status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')",
            (
                new_uuid(),
                course_id,
                number,
                title,
                date.isoformat(),
                file_id,
                _now(),
                mapping_to_json(mapping),
                json.dumps(metadata, ensure_ascii=False),
                present,
                absent,
                unmatched,
            ),
        )
        return int(cur.lastrowid or 0)

    def add_records(
        self, session_id: int, records: Iterable[tuple[int, AttendanceStatus, int | None, str]]
    ) -> None:
        self.db.executemany(
            "INSERT INTO attendance_records(session_id, student_id, status, source_row, raw_identifier) "
            "VALUES (?, ?, ?, ?, ?)",
            [(session_id, sid, status.value, row, raw) for sid, status, row, raw in records],
        )

    def add_participants(
        self,
        session_id: int,
        rows: Iterable[tuple[int, str, str | None, str, int | None, dict[str, str]]],
    ) -> None:
        self.db.executemany(
            "INSERT INTO session_participants(session_id, row_number, raw_identifier, student_key, name, "
            "matched_student_id, data_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (session_id, n, raw, key, name, sid, json.dumps(data, ensure_ascii=False))
                for n, raw, key, name, sid, data in rows
            ],
        )

    def get(self, session_id: int) -> AttendanceSession:
        row = self.db.query_one(self._SELECT + " WHERE s.id=?", (session_id,))
        if row is None:
            raise NotFoundError("This attendance session no longer exists.")
        return self._row(row)

    def for_course(self, course_id: int, include_removed: bool = True) -> list[AttendanceSession]:
        sql = self._SELECT + " WHERE s.course_id=?"
        if not include_removed:
            sql += " AND s.status='active'"
        sql += " ORDER BY s.session_date, s.session_number"
        return [self._row(r) for r in self.db.query(sql, (course_id,))]

    def set_removed(self, session_id: int, removed: bool, reason: str = "") -> None:
        if removed:
            self.db.execute(
                "UPDATE sessions SET status='removed', removed_at=?, removed_reason=?, revision=revision+1 WHERE id=?",
                (_now(), reason, session_id),
            )
        else:
            self.db.execute(
                "UPDATE sessions SET status='active', removed_at=NULL, removed_reason='', revision=revision+1 "
                "WHERE id=?",
                (session_id,),
            )

    def update_details(self, session_id: int, title: str, date: dt.date) -> None:
        self.db.execute(
            "UPDATE sessions SET title=?, session_date=?, revision=revision+1 WHERE id=?",
            (title, date.isoformat(), session_id),
        )

    def records_for_course(self, course_id: int) -> list[tuple[int, int, AttendanceStatus]]:
        rows = self.db.query(
            "SELECT r.session_id, r.student_id, r.status FROM attendance_records r "
            "JOIN sessions s ON s.id = r.session_id WHERE s.course_id=? AND s.status='active'",
            (course_id,),
        )
        return [(r["session_id"], r["student_id"], AttendanceStatus(r["status"])) for r in rows]

    def records(self, session_id: int) -> list[AttendanceRecord]:
        rows = self.db.query(
            "SELECT * FROM attendance_records WHERE session_id=? ORDER BY id", (session_id,)
        )
        return [
            AttendanceRecord(
                session_id=r["session_id"],
                student_id=r["student_id"],
                status=AttendanceStatus(r["status"]),
                source_row=r["source_row"],
                raw_identifier=r["raw_identifier"],
            )
            for r in rows
        ]

    def participants(self, session_id: int) -> list[SessionParticipant]:
        rows = self.db.query(
            "SELECT * FROM session_participants WHERE session_id=? ORDER BY row_number",
            (session_id,),
        )
        return [
            SessionParticipant(
                session_id=r["session_id"],
                row_number=r["row_number"],
                raw_identifier=r["raw_identifier"],
                student_key=r["student_key"],
                name=r["name"],
                matched_student_id=r["matched_student_id"],
                data=json.loads(r["data_json"] or "{}"),
            )
            for r in rows
        ]

    def present_sets(self, course_id: int) -> dict[int, frozenset[int]]:
        rows = self.db.query(
            "SELECT r.session_id, r.student_id FROM attendance_records r JOIN sessions s ON s.id=r.session_id "
            "WHERE s.course_id=? AND r.status='present'",
            (course_id,),
        )
        result: dict[int, set[int]] = {}
        for r in rows:
            result.setdefault(r["session_id"], set()).add(r["student_id"])
        return {k: frozenset(v) for k, v in result.items()}


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.db.query_one("SELECT value FROM settings WHERE key=?", (key,))
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def all(self) -> dict[str, str]:
        return {r["key"]: r["value"] for r in self.db.query("SELECT key, value FROM settings")}


class AuditRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def log(self, action: str, entity_type: str, entity_id: int | None, **details: Any) -> None:
        self.db.execute(
            "INSERT INTO audit_log(occurred_at, action, entity_type, entity_id, details_json) VALUES (?, ?, ?, ?, ?)",
            (
                _now(),
                action,
                entity_type,
                entity_id,
                json.dumps(details, ensure_ascii=False, default=str),
            ),
        )

    def recent(self, limit: int = 200) -> Sequence[sqlite3.Row]:
        return self.db.query("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
