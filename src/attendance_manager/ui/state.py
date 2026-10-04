from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from attendance_manager.domain.errors import NotFoundError
from attendance_manager.domain.models import Course
from attendance_manager.services.context import AppContext


class AppState(QObject):
    """Shared UI state: the selected course and a 'data changed' broadcast."""

    course_changed = Signal()
    data_changed = Signal()

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.course_id: int | None = None

    @property
    def course(self) -> Course | None:
        if self.course_id is None:
            return None
        try:
            return self.ctx.courses.get(self.course_id)
        except NotFoundError:
            return None

    def initialise(self) -> None:
        courses = self.ctx.courses.list_courses(include_archived=False)
        remembered = self.ctx.settings.load().last_course_id
        ids = [c.id for c in courses]
        if remembered in ids:
            self.course_id = remembered
        else:
            self.course_id = ids[0] if ids else None

    def select_course(self, course_id: int | None) -> None:
        if course_id == self.course_id:
            return
        self.course_id = course_id
        self.ctx.settings.remember_course(course_id)
        self.course_changed.emit()

    def notify_changed(self) -> None:
        if self.course_id is not None and self.course is None:
            self.course_id = None
            courses = self.ctx.courses.list_courses(include_archived=False)
            self.course_id = courses[0].id if courses else None
            self.ctx.settings.remember_course(self.course_id)
            self.course_changed.emit()
        self.data_changed.emit()
