# Architecture

This document describes how Attendance Manager is structured, how attendance files are turned
into attendance records, and how data is stored and protected.

## Layers

```
src/attendance_manager/
├── domain/          Pure business logic (no I/O, no Qt); fully unit-tested
│   ├── ids.py           ID normalization and "looks like a student ID" heuristics
│   ├── matching.py      roster × file → present / absent / unmatched
│   ├── statistics.py    cumulative, per-session and dashboard statistics
│   ├── models.py        entities (Course, Student, AttendanceSession, …)
│   └── errors.py        user-facing error types
├── importing/       Spreadsheet reading, table detection, row parsing
│   ├── reader.py        xls/xlsx/csv/html → raw grid (format sniffing)
│   ├── detection.py     ID/name/header detection with a confidence level
│   └── importer.py      grid + column mapping → roster or participant rows, metadata, dates
├── persistence/     SQLite
│   ├── schema.py        versioned migrations, immutability triggers
│   ├── database.py      connection, transactions/savepoints, online backup
│   ├── repositories.py  the only module that contains SQL
│   └── file_store.py    content-addressed store for original uploads
├── services/        Use cases called by the UI (no Qt)
│   ├── course_service.py, attendance_service.py, statistics_service.py,
│   ├── report_service.py, backup_service.py, settings_service.py
│   └── context.py       composition root (wires everything; swappable database for restore)
├── reporting/       excel_report.py: seven-sheet openpyxl report with charts
├── i18n/            catalog lookup, plurals, dates, bidirectional-text helpers (no Qt)
├── locales/         en.json, ar.json
├── ui/              PySide6 main window, pages, dialogs, widgets, theme, icons, language switching
├── app.py           entry point, logging, single-instance lock, --self-test
└── paths.py         per-user data directory and bundled resources
```

Rules that keep the code maintainable:

- Dependencies point inwards only: `ui → services → (domain, importing, persistence, reporting)`.
  `domain` depends on nothing.
- The UI never runs SQL; services never import Qt.
- File parsing and report writing run on a worker thread; the SQLite connection stays on the UI
  thread.
- All user-facing text comes from the translation catalogs (enforced by a test).

## From spreadsheet to attendance record

### 1. Reading

The file type is detected from its content rather than its extension: OLE2 → `xlrd`, ZIP →
`openpyxl` (read-only, formulas as values), HTML tables, and CSV/TSV with BOM and encoding
detection (UTF-8, UTF-16, cp1256, cp1252) and a sniffed delimiter. A mis-named file therefore
still opens. Empty, damaged, password-protected and unreadable files produce specific,
plain-language errors.

### 2. Finding the table (`importing/detection.py`)

Real exports are not clean tables. Microsoft Teams reports contain a "1. Summary" block, a
"2. Participants" section and an organizer row, and a sorted export can move the header row into
the middle of the data or remove it entirely. Detection is therefore content-based:

- every cell is tested for "looks like a student ID" (at least four digits, optionally inside an
  e-mail/UPN such as `202400123@university.edu`); durations, dates and names are rejected;
- the column with the most ID-like cells becomes the ID column; header keywords (`Student Id`,
  `الرقم الجامعي`, `Email`, `UPN`, …) break ties;
- the data starts at the first dense run of IDs, and the non-blank row above it is the header if
  it looks like one;
- the name column is found by header keyword, otherwise by content;
- repeated headers, lone "Total" rows and numbered section titles are skipped.

The result carries a confidence level. Unless it is **high**, the instructor confirms the columns
on a preview where the ID column is tinted blue and the name column green.

### 3. Normalizing IDs (`domain/ids.py`)

Each ID becomes a *match key*. Whitespace, non-breaking and zero-width characters, Excel's `'`
text marker, numeric cells (`202400123.0`), scientific notation, e-mail/UPN wrappers, letter case
and leading zeros on numeric IDs are normalized, so `202400123`, `202400123.0`, ` 202400123 ` and
`202400123@UNIVERSITY.EDU` are the same student.

### 4. Matching (`domain/matching.py`)

A pure function that never relies on row order:

- roster key found anywhere in the file → **present**;
- roster key not in the file → **absent**;
- file rows that are not on the roster (organizers, guests, other sections) → **not on master
  list**: shown, never counted, never turned into students;
- repeated rows count once.

### 5. Saving (`services/attendance_service.py`)

One immutable record per enrolled student is written in a single transaction, together with every
parsed row of the file (the processed result) and the original file.

### Statistics rules

- Attendance % = present ÷ (present + absent) over **active** sessions only.
- A student added to the roster later is only counted for sessions after they joined.
- Status: **Perfect** = 100 %, **Good** ≥ warning limit (default 85 %), **Warning** ≥ at-risk
  limit (default 75 %), **At risk** below it. Both limits are configurable.
- Course average = total present records ÷ all records.

### Verification against real exports

The pipeline was verified against a real term of data: a 45-student master list and four
Microsoft Teams attendance reports, one of them without a header row. Results (present / absent /
not on list): 26/19/3, 28/17/1, 36/9/1 and 37/8/1, giving 127 present and 53 absent records and a
70.56 % average. These numbers were computed independently from the raw files and are asserted by
`tests/test_workflow.py` whenever the real files are available locally. The files themselves
contain personal data and are never committed.

## Database

| Table | Purpose |
|---|---|
| `organizations`, `instructors` | Ownership. One local instructor is created on first run; university accounts or several instructors only add rows. |
| `courses` | Course, section and term; `status` active/archived. |
| `students` | Per-course roster (`UNIQUE(course_id, student_key)`), all master-file columns in `info_json`, `is_active`. |
| `roster_imports` | Every master list ever uploaded (file, column mapping, counts). |
| `sessions` | One per uploaded attendance file: number, title, date, file, mapping, metadata, counts, `status` active/removed. |
| `attendance_records` | One row per (session, student): present/absent. **Immutable** (trigger). |
| `session_participants` | Every parsed row of the uploaded file, including guests. |
| `stored_files` | Original upload metadata; blobs live in the content-addressed `files/` folder. |
| `audit_log` | Who did what, and when, for every change. |
| `settings`, `app_meta` | Preferences (including the interface language) and the installation id. |

Every syncable table has a stable `uuid`, `updated_at`, `revision` and `synced_at`, so a future
synchronization layer can replicate records without schema changes. Schema changes are ordered
migrations tracked with `PRAGMA user_version`; a database created by a newer version is refused
cleanly by older versions.

## Data location

```
%LOCALAPPDATA%\AttendanceManager\
├── attendance.db          SQLite database (WAL mode)
├── files\ab\<sha256>.xls   original uploads (read-only, verified by hash)
├── backups\               automatic and safety backups (.zip)
├── logs\                  rotating log files
└── temp\                  scratch space
```

`ATTENDANCE_MANAGER_DATA_DIR` overrides the location (portable use, testing). A lock file keeps a
second instance from opening the same database.

## Backup and restore

- **Automatic:** once a day (at start-up and exit), keeping the last 14 days by default.
- **Manual:** a single `.zip` written anywhere (USB drive, network share).
- **Safety backups:** taken before every restore and before a course is permanently deleted.
- **Format:** a standard zip with `manifest.json` (application and schema version, counts, SHA-256
  of every file), a consistent SQLite snapshot made with the online backup API, and all original
  files.
- **Restore** validates the whole archive before touching anything (zip integrity, manifest,
  database checksum, `PRAGMA integrity_check`, path-traversal protection, version compatibility),
  takes a safety backup, swaps the database in and rolls back automatically on failure.

## Localization

- `i18n/__init__.py` is pure Python, so services, importers and the report writer share the
  catalog with the UI. Keys are stable dotted names (`nav.dashboard`, `errors.import.empty`, …).
- `tr(key, **values)` formats placeholders; `trn(key, count)` applies CLDR plural rules (Arabic has
  six forms); `format_date` localizes month and day names while keeping Western digits.
- `ui/language.py` switches Qt's layout direction (real RTL mirroring), sets the default `QLocale`
  for date and number widgets, and loads Qt's own Arabic dialog strings.
- Changing the language rebuilds the main window from the catalog while preserving the current
  page, course and filters; the choice is stored in the `settings` table.
- Left-to-right data (file names, e-mail addresses, paths) is wrapped in direction marks inside
  Arabic sentences so the bidirectional algorithm cannot reorder it.
- Tests enforce identical key sets and placeholders in both catalogs and the absence of hard-coded
  UI strings.
