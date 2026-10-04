from __future__ import annotations

from typing import TYPE_CHECKING

from attendance_manager.domain.statistics import CourseStatistics, compute_statistics

if TYPE_CHECKING:
    from attendance_manager.services.context import AppContext


class StatisticsService:
    def __init__(self, ctx: AppContext) -> None:
        self.ctx = ctx

    def course_statistics(self, course_id: int) -> CourseStatistics:
        students = self.ctx.student_repo.for_course(course_id)
        sessions = self.ctx.session_repo.for_course(course_id, include_removed=False)
        records = self.ctx.session_repo.records_for_course(course_id)
        thresholds = self.ctx.settings.load().thresholds
        return compute_statistics(students, sessions, records, thresholds)
