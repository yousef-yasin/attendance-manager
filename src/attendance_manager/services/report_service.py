from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import TYPE_CHECKING

from attendance_manager.domain.errors import AttendanceError
from attendance_manager.i18n import strip_bidi, tr
from attendance_manager.reporting.excel_report import (
    ReportData,
    write_course_report,
    write_session_report,
)

if TYPE_CHECKING:
    from attendance_manager.services.context import AppContext


def safe_filename(text: str) -> str:
    text = strip_bidi(text)
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", text).strip(" .-") or "report"


class ReportService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def default_filename(self, course_id: int) -> str:
        course = self.ctx.course_repo.get(course_id)
        parts = [
            course.name,
            course.section and tr("report.filename_section", section=course.section),
            course.semester,
            course.year,
        ]
        base = " ".join(p for p in parts if p)
        name = tr("report.filename", course=base, date=f"{dt.date.today():%Y-%m-%d}")
        return safe_filename(name) + ".xlsx"

    def report_data(self, course_id: int) -> ReportData:
        settings = self.ctx.settings.load()
        return ReportData(
            course=self.ctx.course_repo.get(course_id),
            statistics=self.ctx.statistics.course_statistics(course_id),
            info_columns=self.ctx.courses.info_columns(course_id),
            thresholds=settings.thresholds,
            instructor=settings.instructor_name,
            generated_at=dt.datetime.now(),
        )

    @staticmethod
    def write(path: Path, data: ReportData) -> Path:
        """Pure file writing — safe to call from a worker thread."""
        try:
            return write_course_report(path, data)
        except PermissionError as exc:
            raise AttendanceError(tr("errors.report_locked", file=path.name)) from exc

    def generate(self, course_id: int, path: Path) -> Path:
        result = self.write(path, self.report_data(course_id))
        with self.ctx.db.transaction():
            self.ctx.audit.log("report.generate", "course", course_id, path=str(path))
        return result

    def export_session(self, session_id: int, path: Path) -> Path:
        detail = self.ctx.attendance.session_detail(session_id)
        course = self.ctx.course_repo.get(detail.session.course_id)
        try:
            return write_session_report(
                path,
                course,
                detail.session.label,
                detail.session.session_date,
                detail.session.original_filename,
                detail.present,
                detail.absent,
                detail.unmatched,
            )
        except PermissionError as exc:
            raise AttendanceError(tr("errors.report_locked", file=path.name)) from exc
