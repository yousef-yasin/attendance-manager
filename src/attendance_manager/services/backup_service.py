"""Backup and restore.

A backup is an ordinary ``.zip`` containing:

* ``manifest.json`` — format, app & schema version, creation time, checksums;
* ``attendance.db`` — a consistent SQLite snapshot (online backup API);
* ``files/...`` — every original uploaded Excel file.

Restoring validates the archive completely, takes a safety backup of the
current data, swaps the database in, and rolls back if anything fails.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import json
import logging
import re
import shutil
import sqlite3
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

from attendance_manager import __version__
from attendance_manager.domain.errors import BackupError
from attendance_manager.i18n import tr
from attendance_manager.persistence.database import utc_now
from attendance_manager.persistence.schema import SCHEMA_VERSION

if TYPE_CHECKING:
    from attendance_manager.services.context import AppContext

log = logging.getLogger(__name__)

BACKUP_FORMAT = "attendance-manager-backup"
BACKUP_FORMAT_VERSION = 1
AUTO_REASON = "automatic"


@dataclass(frozen=True)
class BackupInfo:
    path: Path
    created_at: dt.datetime
    reason: str
    app_version: str
    schema_version: int
    courses: int
    sessions: int
    size_bytes: int

    @property
    def is_automatic(self) -> bool:
        return self.reason == AUTO_REASON


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:40] or "backup"


class BackupService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    # ------------------------------------------------------------------ create
    def default_backup_name(self, reason: str = "manual") -> str:
        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        suffix = "" if reason == "manual" else f"_{_slug(reason)}"
        return f"AttendanceManager_Backup_{stamp}{suffix}.zip"

    def create_backup(self, destination: Path | None = None, *, reason: str = "manual") -> Path:
        paths = self.ctx.paths
        if destination is None:
            destination = paths.backups_dir / self.default_backup_name(reason)
            # Never overwrite an existing backup (two backups within one second).
            counter = 2
            base = destination
            while destination.exists():
                destination = base.with_name(f"{base.stem}_{counter}{base.suffix}")
                counter += 1
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)
        work = paths.temp_dir / f"backup-{dt.datetime.now():%Y%m%d%H%M%S%f}"
        work.mkdir(parents=True, exist_ok=True)
        try:
            snapshot = work / "attendance.db"
            self.ctx.db.backup_to(snapshot)
            counts = self._counts(snapshot)
            files = sorted(
                p
                for p in paths.files_dir.rglob("*")
                if p.is_file() and not p.name.endswith(".part")
            )
            manifest = {
                "format": BACKUP_FORMAT,
                "format_version": BACKUP_FORMAT_VERSION,
                "app_version": __version__,
                "schema_version": SCHEMA_VERSION,
                "created_at": utc_now().isoformat(),
                "reason": reason,
                "courses": counts[0],
                "sessions": counts[1],
                "database_sha256": _file_sha(snapshot),
                "files": {p.relative_to(paths.files_dir).as_posix(): _file_sha(p) for p in files},
            }
            temp_zip = destination.with_name(destination.name + ".part")
            with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("manifest.json", json.dumps(manifest, indent=2))
                zf.write(snapshot, "attendance.db")
                for p in files:
                    zf.write(p, "files/" + p.relative_to(paths.files_dir).as_posix())
            with zipfile.ZipFile(temp_zip) as zf:
                if zf.testzip() is not None:
                    raise BackupError(tr("errors.backup.verify_failed"))
            temp_zip.replace(destination)
        except BackupError:
            raise
        except OSError as exc:
            raise BackupError(
                tr("errors.backup.write_failed", path=destination), details=str(exc)
            ) from exc
        finally:
            shutil.rmtree(work, ignore_errors=True)
        with self.ctx.db.transaction():
            self.ctx.audit.log(
                "backup.create", "backup", None, path=str(destination), reason=reason
            )
        log.info("Backup written to %s", destination)
        return destination

    @staticmethod
    def _counts(db_path: Path) -> tuple[int, int]:
        conn = sqlite3.connect(str(db_path))
        try:
            courses = conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
            sessions = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            return int(courses), int(sessions)
        except sqlite3.Error:
            return 0, 0
        finally:
            conn.close()

    # -------------------------------------------------------------------- list
    def read_info(self, path: Path) -> BackupInfo:
        manifest = self._read_manifest(path)
        created = dt.datetime.fromisoformat(manifest["created_at"])
        return BackupInfo(
            path=path,
            created_at=created,
            reason=str(manifest.get("reason", "")),
            app_version=str(manifest.get("app_version", "")),
            schema_version=int(manifest.get("schema_version", 0)),
            courses=int(manifest.get("courses", 0)),
            sessions=int(manifest.get("sessions", 0)),
            size_bytes=path.stat().st_size,
        )

    def list_backups(self) -> list[BackupInfo]:
        result = []
        for path in self.ctx.paths.backups_dir.glob("*.zip"):
            try:
                result.append(self.read_info(path))
            except BackupError:
                log.warning("Ignoring invalid backup %s", path)
        return sorted(result, key=lambda b: b.created_at, reverse=True)

    def last_backup_time(self) -> dt.datetime | None:
        backups = self.list_backups()
        return backups[0].created_at if backups else None

    def auto_backup_if_due(self, now: dt.datetime | None = None) -> Path | None:
        settings = self.ctx.settings.load()
        if not settings.auto_backup or not self.ctx.course_repo.all():
            return None
        now = now or utc_now()
        autos = [b for b in self.list_backups() if b.is_automatic]
        if autos and now - autos[0].created_at < dt.timedelta(hours=20):
            return None
        path = self.create_backup(reason=AUTO_REASON)
        self.prune_automatic(settings.auto_backup_keep)
        return path

    def prune_automatic(self, keep: int) -> int:
        autos = [b for b in self.list_backups() if b.is_automatic]
        removed = 0
        for backup in autos[keep:]:
            try:
                backup.path.unlink()
                removed += 1
            except OSError:
                log.warning("Could not remove old automatic backup %s", backup.path)
        return removed

    # ------------------------------------------------------------------ restore
    def _read_manifest(self, path: Path) -> dict:
        if not path.exists():
            raise BackupError(tr("errors.backup.missing", file=path.name))
        try:
            with zipfile.ZipFile(path) as zf:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
            raise BackupError(tr("errors.backup.not_backup_or_damaged", file=path.name)) from exc
        if manifest.get("format") != BACKUP_FORMAT:
            raise BackupError(tr("errors.backup.not_backup", file=path.name))
        if int(manifest.get("format_version", 0)) > BACKUP_FORMAT_VERSION:
            raise BackupError(tr("errors.backup.newer_version"))
        if int(manifest.get("schema_version", 0)) > SCHEMA_VERSION:
            raise BackupError(tr("errors.backup.newer_version"))
        return manifest

    def validate_backup(self, path: Path) -> BackupInfo:
        """Full validation without touching current data."""
        manifest = self._read_manifest(path)
        with zipfile.ZipFile(path) as zf:
            bad = zf.testzip()
            if bad is not None:
                raise BackupError(tr("errors.backup.corrupt_member", file=bad))
            for name in zf.namelist():
                pure = PurePosixPath(name)
                if pure.is_absolute() or ".." in pure.parts or ":" in name:
                    raise BackupError(tr("errors.backup.unsafe"))
            if "attendance.db" not in zf.namelist():
                raise BackupError(tr("errors.backup.no_database"))
            with zf.open("attendance.db") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            if digest != manifest.get("database_sha256"):
                raise BackupError(tr("errors.backup.checksum"))
        return self.read_info(path)

    def restore_backup(self, path: Path) -> Path:
        """Replace all current data with the backup. Returns the safety backup path."""
        self.validate_backup(path)
        paths = self.ctx.paths
        stage = paths.temp_dir / f"restore-{dt.datetime.now():%Y%m%d%H%M%S%f}"
        stage.mkdir(parents=True)
        try:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(stage)
            staged_db = stage / "attendance.db"
            conn = sqlite3.connect(str(staged_db))
            try:
                ok = conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            finally:
                conn.close()
            if not ok:
                raise BackupError(tr("errors.backup.db_damaged"))

            safety = self.create_backup(reason="before restore")
            self.ctx.close_database()
            saved = stage / "previous"
            saved.mkdir()
            db_files = [
                paths.database,
                paths.database.with_name(paths.database.name + "-wal"),
                paths.database.with_name(paths.database.name + "-shm"),
            ]
            try:
                for f in db_files:
                    if f.exists():
                        shutil.move(str(f), str(saved / f.name))
                shutil.copyfile(staged_db, paths.database)
                staged_files = stage / "files"
                if staged_files.exists():
                    for src in staged_files.rglob("*"):
                        if src.is_file():
                            target = paths.files_dir / src.relative_to(staged_files)
                            if not target.exists():
                                target.parent.mkdir(parents=True, exist_ok=True)
                                shutil.copyfile(src, target)
                self.ctx.reopen_database()
            except Exception as exc:
                log.exception("Restore failed; rolling back")
                with contextlib.suppress(Exception):
                    self.ctx.close_database()
                for f in db_files:
                    f.unlink(missing_ok=True)
                for f in saved.iterdir():
                    shutil.move(str(f), str(paths.database.parent / f.name))
                self.ctx.reopen_database()
                raise BackupError(tr("errors.backup.restore_failed"), details=str(exc)) from exc
            with self.ctx.db.transaction():
                self.ctx.audit.log(
                    "backup.restore", "backup", None, path=str(path), safety_backup=str(safety)
                )
            log.info("Restored backup %s (safety backup %s)", path, safety)
            return safety
        finally:
            shutil.rmtree(stage, ignore_errors=True)
