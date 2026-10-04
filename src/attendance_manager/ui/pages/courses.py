from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
)

from attendance_manager.domain.models import Course, CourseStatus
from attendance_manager.i18n import format_percent, paragraph, tr
from attendance_manager.ui import theme
from attendance_manager.ui.icons import icon
from attendance_manager.ui.pages.base import Page, page_body, scroll_container
from attendance_manager.ui.widgets.common import (
    Card,
    EmptyState,
    ResponsiveGrid,
    StatusChip,
    button,
    label,
)


class CourseCard(Card):
    def __init__(
        self,
        page: CoursesPage,
        course: Course,
        students: int,
        sessions: int,
        average: float | None,
        current: bool,
    ) -> None:
        super().__init__(padding=18)
        self.setProperty("selected", "true" if current else "false")
        self.setMinimumHeight(190)
        top = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        name = label(paragraph(course.name), "CardTitle", wrap=True)
        name.setStyleSheet("font-size: 16px;")
        texts.addWidget(name)
        sub = course.term_description
        texts.addWidget(label(paragraph(sub or tr("courses.no_term")), "CardSubtitle"))
        top.addLayout(texts, 1)
        if course.status is CourseStatus.ARCHIVED:
            top.addWidget(
                StatusChip(text=tr("status.archived"), dot=theme.MUTED, soft=theme.NEUTRAL_SOFT),
                0,
                Qt.AlignmentFlag.AlignTop,
            )
        elif current:
            top.addWidget(
                StatusChip(text=tr("status.selected"), dot=theme.ACCENT, soft=theme.ACCENT_SOFT),
                0,
                Qt.AlignmentFlag.AlignTop,
            )
        more = QPushButton()
        more.setProperty("kind", "subtle")
        more.setIcon(icon("more", theme.INK_2))
        more.setIconSize(QSize(18, 18))
        more.setToolTip(tr("common.more_actions"))
        more.setCursor(Qt.CursorShape.PointingHandCursor)
        menu = QMenu(more)
        menu.addAction(
            icon("edit", theme.INK_2),
            tr("courses.menu.edit"),
            lambda: page.window_.edit_course(course),
        )
        menu.addAction(
            icon("students", theme.INK_2),
            tr("courses.menu.update_roster"),
            lambda: page.window_.update_roster(course),
        )
        menu.addSeparator()
        if course.status is CourseStatus.ARCHIVED:
            menu.addAction(
                icon("undo", theme.INK_2),
                tr("courses.menu.unarchive"),
                lambda: page.set_archived(course, False),
            )
        else:
            menu.addAction(
                icon("archive", theme.INK_2),
                tr("courses.menu.archive"),
                lambda: page.set_archived(course, True),
            )
        menu.addAction(
            icon("trash", theme.CRITICAL),
            tr("courses.menu.delete"),
            lambda: page.window_.delete_course(course),
        )
        more.setMenu(menu)
        top.addWidget(more, 0, Qt.AlignmentFlag.AlignTop)
        self.body.addLayout(top)

        stats = QHBoxLayout()
        stats.setSpacing(24)
        for title, value in (
            (tr("courses.stat.students"), str(students)),
            (tr("courses.stat.sessions"), str(sessions)),
            (tr("courses.stat.average"), format_percent(average)),
        ):
            box = QVBoxLayout()
            box.setSpacing(0)
            box.addWidget(label(value, "StatValueSmall"))
            box.addWidget(label(title, "StatHint"))
            stats.addLayout(box)
        stats.addStretch(1)
        self.body.addLayout(stats)
        self.body.addStretch(1)
        actions = QHBoxLayout()
        open_btn = button(
            tr("courses.open_dashboard"),
            "primary" if not current else "",
            "dashboard",
            lambda: page.open_course(course),
        )
        attendance = button(
            tr("actions.add_attendance"), "", "upload", lambda: page.add_attendance(course)
        )
        attendance.setEnabled(course.status is CourseStatus.ACTIVE)
        actions.addWidget(open_btn)
        actions.addWidget(attendance)
        actions.addStretch(1)
        self.body.addLayout(actions)


class CoursesPage(Page):
    key = "courses"

    def __init__(self, window) -> None:
        super().__init__(window)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.empty = EmptyState(
            "courses",
            tr("courses.empty_title"),
            tr("courses.empty_text"),
            [button(tr("actions.create_course"), "primary", "plus", window.create_course)],
        )
        self.stack.addWidget(self.empty)
        body, layout = page_body()
        bar = QHBoxLayout()
        self.show_archived = QCheckBox(tr("courses.show_archived"))
        self.show_archived.toggled.connect(lambda _: self.refresh_now())
        bar.addWidget(self.show_archived)
        bar.addStretch(1)
        bar.addWidget(button(tr("actions.create_course"), "primary", "plus", window.create_course))
        layout.addLayout(bar)
        self.grid = ResponsiveGrid(min_item_width=340, max_columns=3)
        layout.addWidget(self.grid)
        self.none_visible = label(tr("courses.all_archived"), "Secondary")
        layout.addWidget(self.none_visible)
        layout.addStretch(1)
        self.content = scroll_container(body)
        self.stack.addWidget(self.content)

    def refresh(self) -> None:
        courses = self.ctx.courses.list_courses(include_archived=True)
        if not courses:
            self.stack.setCurrentWidget(self.empty)
            return
        self.stack.setCurrentWidget(self.content)
        visible = [
            c for c in courses if self.show_archived.isChecked() or c.status is CourseStatus.ACTIVE
        ]
        cards = []
        for course in visible:
            students, sessions = self.ctx.courses.counts(course.id)
            average = None
            if sessions:
                average = self.ctx.statistics.course_statistics(
                    course.id
                ).dashboard.average_percentage
            cards.append(
                CourseCard(
                    self, course, students, sessions, average, course.id == self.state.course_id
                )
            )
        self.grid.set_items(cards)
        self.none_visible.setVisible(not visible)

    def open_course(self, course: Course) -> None:
        self.state.select_course(course.id)
        self.window_.navigate("dashboard")

    def add_attendance(self, course: Course) -> None:
        self.state.select_course(course.id)
        self.window_.add_attendance()

    def set_archived(self, course: Course, archived: bool) -> None:
        self.window_.set_course_archived(course, archived)
