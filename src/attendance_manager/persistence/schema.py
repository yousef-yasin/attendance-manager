"""Database schema, as an ordered list of migrations.

Design notes (future-proofing without touching the attendance engine):

* every syncable entity has a stable ``uuid`` besides its local integer id, plus
  ``revision``/``synced_at`` columns so a future cloud-sync layer can do
  last-writer-wins or merge without schema changes;
* courses belong to an ``instructor``; instructors optionally belong to an
  ``organization`` (university account). A single local instructor is created
  on first run, so multi-instructor support only adds rows, not columns;
* ``app_meta`` holds the installation id and is where licensing / update
  channel metadata will live;
* attendance records are immutable (enforced by triggers): removing a session
  only flags it, and every upload is a new session.
"""

from __future__ import annotations

MIGRATIONS: list[str] = [
    # ---- v1 -----------------------------------------------------------------
    """
    CREATE TABLE app_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    CREATE TABLE organizations (
        id          INTEGER PRIMARY KEY,
        uuid        TEXT NOT NULL UNIQUE,
        name        TEXT NOT NULL,
        external_id TEXT,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );

    CREATE TABLE instructors (
        id                  INTEGER PRIMARY KEY,
        uuid                TEXT NOT NULL UNIQUE,
        organization_id     INTEGER REFERENCES organizations(id) ON DELETE SET NULL,
        display_name        TEXT NOT NULL DEFAULT '',
        email               TEXT NOT NULL DEFAULT '',
        external_account_id TEXT,
        is_local            INTEGER NOT NULL DEFAULT 1,
        created_at          TEXT NOT NULL,
        updated_at          TEXT NOT NULL
    );

    CREATE TABLE courses (
        id            INTEGER PRIMARY KEY,
        uuid          TEXT NOT NULL UNIQUE,
        instructor_id INTEGER NOT NULL REFERENCES instructors(id),
        name          TEXT NOT NULL,
        section       TEXT NOT NULL DEFAULT '',
        semester      TEXT NOT NULL DEFAULT '',
        year          TEXT NOT NULL DEFAULT '',
        notes         TEXT NOT NULL DEFAULT '',
        status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived')),
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        revision      INTEGER NOT NULL DEFAULT 1,
        synced_at     TEXT
    );
    CREATE INDEX ix_courses_instructor ON courses(instructor_id);

    CREATE TABLE stored_files (
        id                INTEGER PRIMARY KEY,
        uuid              TEXT NOT NULL UNIQUE,
        sha256            TEXT NOT NULL,
        original_filename TEXT NOT NULL,
        relative_path     TEXT NOT NULL,
        size_bytes        INTEGER NOT NULL,
        stored_at         TEXT NOT NULL
    );
    CREATE INDEX ix_stored_files_sha ON stored_files(sha256);

    CREATE TABLE roster_imports (
        id                INTEGER PRIMARY KEY,
        uuid              TEXT NOT NULL UNIQUE,
        course_id         INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        file_id           INTEGER NOT NULL REFERENCES stored_files(id),
        imported_at       TEXT NOT NULL,
        column_mapping    TEXT NOT NULL,
        student_count     INTEGER NOT NULL,
        added_count       INTEGER NOT NULL,
        updated_count     INTEGER NOT NULL,
        deactivated_count INTEGER NOT NULL
    );
    CREATE INDEX ix_roster_imports_course ON roster_imports(course_id);

    CREATE TABLE students (
        id              INTEGER PRIMARY KEY,
        uuid            TEXT NOT NULL UNIQUE,
        course_id       INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        student_key     TEXT NOT NULL,
        student_number  TEXT NOT NULL,
        full_name       TEXT NOT NULL,
        info_json       TEXT NOT NULL DEFAULT '{}',
        roster_position INTEGER NOT NULL,
        is_active       INTEGER NOT NULL DEFAULT 1,
        first_import_id INTEGER REFERENCES roster_imports(id),
        last_import_id  INTEGER REFERENCES roster_imports(id),
        created_at      TEXT NOT NULL,
        updated_at      TEXT NOT NULL,
        revision        INTEGER NOT NULL DEFAULT 1,
        synced_at       TEXT,
        UNIQUE (course_id, student_key)
    );
    CREATE INDEX ix_students_course ON students(course_id);

    CREATE TABLE sessions (
        id              INTEGER PRIMARY KEY,
        uuid            TEXT NOT NULL UNIQUE,
        course_id       INTEGER NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
        session_number  INTEGER NOT NULL,
        title           TEXT NOT NULL DEFAULT '',
        session_date    TEXT NOT NULL,
        file_id         INTEGER NOT NULL REFERENCES stored_files(id),
        uploaded_at     TEXT NOT NULL,
        column_mapping  TEXT NOT NULL,
        metadata_json   TEXT NOT NULL DEFAULT '{}',
        present_count   INTEGER NOT NULL,
        absent_count    INTEGER NOT NULL,
        unmatched_count INTEGER NOT NULL,
        status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'removed')),
        removed_at      TEXT,
        removed_reason  TEXT NOT NULL DEFAULT '',
        revision        INTEGER NOT NULL DEFAULT 1,
        synced_at       TEXT,
        UNIQUE (course_id, session_number)
    );
    CREATE INDEX ix_sessions_course ON sessions(course_id);

    CREATE TABLE attendance_records (
        id             INTEGER PRIMARY KEY,
        session_id     INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        student_id     INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        status         TEXT NOT NULL CHECK (status IN ('present', 'absent')),
        source_row     INTEGER,
        raw_identifier TEXT NOT NULL DEFAULT '',
        UNIQUE (session_id, student_id)
    );
    CREATE INDEX ix_records_student ON attendance_records(student_id);

    CREATE TABLE session_participants (
        id                 INTEGER PRIMARY KEY,
        session_id         INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        row_number         INTEGER NOT NULL,
        raw_identifier     TEXT NOT NULL,
        student_key        TEXT,
        name               TEXT NOT NULL DEFAULT '',
        matched_student_id INTEGER REFERENCES students(id) ON DELETE SET NULL,
        data_json          TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX ix_participants_session ON session_participants(session_id);

    CREATE TABLE audit_log (
        id            INTEGER PRIMARY KEY,
        occurred_at   TEXT NOT NULL,
        instructor_id INTEGER,
        action        TEXT NOT NULL,
        entity_type   TEXT NOT NULL,
        entity_id     INTEGER,
        details_json  TEXT NOT NULL DEFAULT '{}'
    );

    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );

    -- Historical attendance is append-only.
    CREATE TRIGGER trg_records_immutable
    BEFORE UPDATE ON attendance_records
    BEGIN
        SELECT RAISE(ABORT, 'Attendance records are immutable');
    END;

    CREATE TRIGGER trg_participants_immutable
    BEFORE UPDATE OF session_id, row_number, raw_identifier, student_key, name, data_json
    ON session_participants
    BEGIN
        SELECT RAISE(ABORT, 'Session participants are immutable');
    END;

    CREATE TRIGGER trg_session_results_immutable
    BEFORE UPDATE OF course_id, session_number, file_id, present_count, absent_count,
                     unmatched_count, column_mapping, uploaded_at
    ON sessions
    BEGIN
        SELECT RAISE(ABORT, 'Session results are immutable');
    END;
    """,
]

SCHEMA_VERSION = len(MIGRATIONS)
