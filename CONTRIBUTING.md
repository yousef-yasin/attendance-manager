# Contributing

Thank you for helping improve Attendance Manager. This document explains how to set up a
development environment and the conventions the code base follows.

> This is a proprietary project (see the README). Please open an issue to discuss a change before
> starting significant work.

## Never commit student data

Real attendance files, rosters, SQLite databases, generated reports, backups and screenshots of
real courses contain personal information. They must never be committed, attached to issues or
pasted into pull requests.

- Put real files only in `tests/fixtures/real/` (ignored by git). Tests that need them are skipped
  automatically when they are absent.
- Use the synthetic fixtures in `tests/fixtures/synthetic/` (regenerate them with
  `python tests/fixtures/make_synthetic.py`) or invent clearly fictional values in tests, such as
  `202400123` or `j.doe@university.edu`.
- `scripts/screenshots.py` uses the synthetic fixtures by default; only publish screenshots made
  from them.

## Development setup

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m attendance_manager
```

Python 3.10+ on Windows 10/11 is the supported environment. Dependencies are pinned in
`requirements.txt` (runtime) and `requirements-dev.txt` (tooling).

## Quality gates

Every change must pass the same checks as CI:

```powershell
.venv\Scripts\python -m pytest
.venv\Scripts\ruff check .
.venv\Scripts\ruff format --check .
.venv\Scripts\mypy
```

Use `ruff format .` to format and `ruff check --fix .` for automatic lint fixes.

## Code conventions

- **Layering.** `ui → services → (domain, importing, persistence, reporting)`. `domain` has no I/O
  and no Qt; services never import Qt; the UI never runs SQL. SQL lives only in
  `persistence/repositories.py`. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
- **Typing.** All non-UI code is fully typed (`disallow_untyped_defs`); mypy must stay clean.
- **Attendance history is immutable.** Never update or delete attendance records; corrections go
  through removing and re-adding sessions.
- **Schema changes** are new migrations appended to `persistence/schema.py`, each with a test.
  Existing migrations are never edited.
- **Long-running work** (file parsing, report writing) runs on a worker thread; the database
  connection stays on the UI thread.

## Localization

- Every user-facing string lives in **both** `src/attendance_manager/locales/en.json` and
  `ar.json` under the same dotted key. Use `tr("key", name=value)` or, for counts,
  `trn("key", count)` with the plural forms the language needs (Arabic uses `zero`, `one`, `two`,
  `few`, `many`, `other`).
- Do not hard-code UI text: `tests/test_i18n.py` scans the UI, services and importers and fails on
  literal strings, missing keys or mismatched placeholders.
- Check new screens in Arabic: the layout must mirror correctly in right-to-left mode, and data
  such as names, IDs and file names must stay untranslated.

## Pull requests

1. Create a feature branch from `main`.
2. Keep changes focused, with tests for new behaviour and a `CHANGELOG.md` entry under
   *Unreleased* for user-visible changes.
3. Make sure all quality gates pass locally.
4. Fill in the pull request template, including how the change was tested.
