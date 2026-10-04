"""Composition root: wires paths, database, file store and services together."""

from __future__ import annotations

import logging

from attendance_manager.paths import AppPaths
from attendance_manager.persistence.database import Database
from attendance_manager.persistence.file_store import FileStore
from attendance_manager.persistence.repositories import (
    AuditRepository,
    CourseRepository,
    FileRepository,
    RosterImportRepository,
    SessionRepository,
    SettingsRepository,
    StudentRepository,
)

log = logging.getLogger(__name__)


class AppContext:
    def __init__(self, paths: AppPaths) -> None:
        from attendance_manager.services.attendance_service import AttendanceService
        from attendance_manager.services.backup_service import BackupService
        from attendance_manager.services.course_service import CourseService
        from attendance_manager.services.report_service import ReportService
        from attendance_manager.services.settings_service import SettingsService
        from attendance_manager.services.statistics_service import StatisticsService

        self.paths = paths.ensure()
        self.files = FileStore(self.paths.files_dir)
        self.db = Database(self.paths.database)
        self._bind_repositories()
        self.settings = SettingsService(self)
        self.courses = CourseService(self)
        self.attendance = AttendanceService(self)
        self.statistics = StatisticsService(self)
        self.backups = BackupService(self)
        self.reports = ReportService(self)
        log.info("Data directory: %s", self.paths.root)

    def _bind_repositories(self) -> None:
        self.course_repo = CourseRepository(self.db)
        self.student_repo = StudentRepository(self.db)
        self.session_repo = SessionRepository(self.db)
        self.file_repo = FileRepository(self.db)
        self.roster_repo = RosterImportRepository(self.db)
        self.settings_repo = SettingsRepository(self.db)
        self.audit = AuditRepository(self.db)

    def close_database(self) -> None:
        self.db.close()

    def reopen_database(self) -> None:
        self.db = Database(self.paths.database)
        self._bind_repositories()

    def close(self) -> None:
        self.db.close()
