# Changelog

All notable changes to this project are documented in this file. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.0.0] — 2026-10-04

First public release.

### Courses and attendance

- Courses with isolated rosters: create from a master list, edit, update the student list,
  archive, and delete (with an automatic backup first).
- Weekly attendance import from `.xls`, `.xlsx`, CSV/TSV and HTML exports, including Microsoft
  Teams attendance reports with or without a header row.
- Automatic column detection with a manual column-mapping screen when detection is uncertain.
- ID-based matching that tolerates whitespace, numeric/text cells, e-mail/UPN identifiers, case
  and leading zeros; organizers and guests are listed but never counted.
- Immutable, recoverable session history with original files and processed results; duplicate
  upload detection.

### Insight and reporting

- Dashboard with key figures, attendance trend and distribution charts, and at-risk lists.
- Students table with search, sorting, filters and per-student history.
- Seven-sheet Excel report and single-session export.

### Arabic and English

- Complete Arabic interface with full right-to-left layout, switchable at runtime from the top bar
  or *Settings* and remembered across restarts.
- Localized dates, Arabic plural rules, error messages and Excel reports (right-to-left sheets in
  Arabic); left-to-right data inside Arabic text is protected from reordering.

### Data safety

- SQLite storage with write-ahead logging, append-only attendance enforced by triggers, and an
  audit log.
- Automatic daily backups and validated manual backup/restore with a safety backup.

### Distribution

- Windows installer (PyInstaller + Inno Setup): per-user installation without administrator
  rights, desktop and Start Menu shortcuts, uninstaller, in-place upgrades; user data is kept on
  uninstall.

### Project

- Documentation: user guide, architecture, release process, contributing guide and security
  policy.
- Continuous integration for tests, linting, formatting and type checking.
- Repository hygiene: `.gitignore` rules and test changes that keep real student data out of
  version control.
