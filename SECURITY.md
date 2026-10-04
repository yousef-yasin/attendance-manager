# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | ✅ |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report vulnerabilities privately through GitHub: open the repository's **Security** tab and choose
**Report a vulnerability**. Include the affected version, steps to reproduce and the potential
impact. Never include real student data in a report; use fictional data to demonstrate the
problem.

The maintainer will acknowledge the report and coordinate a fix, which is released as a new patch
version and noted in the changelog.

## Data-handling model

Attendance Manager processes personal data (student names, IDs, e-mail addresses and attendance)
and is designed to keep it on the instructor's computer:

- **No network access.** The application makes no network connections: no telemetry, update
  checks or cloud services.
- **Local storage.** All data is stored per Windows user in `%LOCALAPPDATA%\AttendanceManager`
  (SQLite database, original uploaded files, backups and logs), protected by the operating
  system's user-account permissions. The data is **not encrypted** by the application; use
  Windows device encryption (BitLocker) on computers that hold student records.
- **Integrity.** Original uploads are stored content-addressed and verified by SHA-256.
  Attendance records are append-only, enforced by database triggers, and changes are written to
  an audit log.
- **Backups** are ordinary `.zip` files containing the full database and original files. Treat
  them as confidential and store them only in approved locations.
- **Restore safety.** Backups are validated before use (archive integrity, checksums, SQLite
  integrity check, path-traversal protection, version compatibility), and a safety backup is
  taken first.
- **Uninstalling keeps the data.** To remove it completely, delete
  `%LOCALAPPDATA%\AttendanceManager` after uninstalling.

## Repository hygiene

The repository must never contain real student data, databases, reports, backups, secrets or
signing certificates. `.gitignore` blocks these file types; tests and documentation use synthetic,
fictional data only.
