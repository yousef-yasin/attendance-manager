from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QStackedWidget, QVBoxLayout

from attendance_manager.domain.statistics import CourseStatistics, StudentStats
from attendance_manager.i18n import format_date, format_percent, tr, trn
from attendance_manager.ui import theme
from attendance_manager.ui.pages.base import ListRow, Page, page_body, scroll_container
from attendance_manager.ui.widgets.charts import DistributionChart, TrendChart
from attendance_manager.ui.widgets.common import (
    Card,
    EmptyState,
    ResponsiveGrid,
    StatCard,
    StatusChip,
    button,
    clear_layout,
    label,
)


def _names(students: list[StudentStats], limit: int = 3) -> str:
    # Student names are data: shown exactly as in the master list (never translated).
    names = [s.student.full_name.title() for s in students[:limit]]
    more = len(students) - limit
    text = tr("common.list_separator").join(names)
    return tr("common.and_more", names=text, count=more) if more > 0 else text


class DashboardPage(Page):
    key = "dashboard"

    def __init__(self, window) -> None:
        super().__init__(window)
        self.stats: CourseStatistics | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)

        self.welcome = EmptyState(
            "cap",
            tr("dashboard.welcome_title"),
            tr("dashboard.welcome_text"),
            [button(tr("dashboard.create_first_course"), "primary", "plus", window.create_course)],
        )
        self.no_sessions = EmptyState(
            "sessions",
            tr("dashboard.no_sessions_title"),
            "",
            [
                button(
                    tr("actions.add_attendance"),
                    "primary",
                    "upload",
                    lambda: window.add_attendance(),
                )
            ],
        )
        self.stack.addWidget(self.welcome)
        self.stack.addWidget(self.no_sessions)

        body, layout = page_body()
        self.kpis = ResponsiveGrid(min_item_width=200, max_columns=5)
        self.c_students = StatCard(tr("dashboard.kpi.students"), "students")
        self.c_sessions = StatCard(tr("dashboard.kpi.sessions"), "sessions")
        self.c_average = StatCard(tr("dashboard.kpi.average"), "percent")
        self.c_present = StatCard(tr("dashboard.kpi.present"), "user-check", theme.GOOD)
        self.c_absent = StatCard(tr("dashboard.kpi.absent"), "user-x", theme.CRITICAL)
        self.c_perfect = StatCard(tr("dashboard.kpi.perfect"), "award", theme.GOOD)
        self.c_with_abs = StatCard(
            tr("dashboard.kpi.with_absences"), "alert-circle", theme.WARNING_TEXT
        )
        self.c_highest = StatCard(tr("dashboard.kpi.highest"), "trend", theme.ACCENT)
        self.c_most_abs = StatCard(tr("dashboard.kpi.most_absences"), "user-x", theme.CRITICAL)
        self.c_risk = StatCard(tr("dashboard.kpi.at_risk"), "alert", theme.CRITICAL)
        cards = [
            self.c_students,
            self.c_sessions,
            self.c_average,
            self.c_present,
            self.c_absent,
            self.c_perfect,
            self.c_with_abs,
            self.c_highest,
            self.c_most_abs,
            self.c_risk,
        ]
        self.kpis.set_items(cards)
        self.c_students.clicked.connect(lambda: window.show_students("all"))
        self.c_sessions.clicked.connect(lambda: window.navigate("sessions"))
        self.c_perfect.clicked.connect(lambda: window.show_students("perfect"))
        self.c_with_abs.clicked.connect(lambda: window.show_students("with_absences"))
        self.c_risk.clicked.connect(lambda: window.show_students("at_risk"))
        for c in (self.c_students, self.c_sessions, self.c_perfect, self.c_with_abs, self.c_risk):
            c.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.kpis)

        charts = ResponsiveGrid(min_item_width=440, max_columns=2)
        self.trend_card = Card()
        self.trend_card.add_header(tr("dashboard.trend_title"), tr("dashboard.trend_subtitle"))
        self.trend = TrendChart()
        self.trend_card.body.addWidget(self.trend)
        self.dist_card = Card()
        self.dist_card.add_header(
            tr("dashboard.distribution_title"), tr("dashboard.distribution_subtitle")
        )
        self.distribution = DistributionChart()
        self.dist_card.body.addWidget(self.distribution)
        charts.set_items([self.trend_card, self.dist_card])
        layout.addWidget(charts)

        lists = ResponsiveGrid(min_item_width=340, max_columns=3)
        self.risk_card = Card()
        self.absent_card = Card()
        self.recent_card = Card()
        self.risk_list = QVBoxLayout()
        self.absent_list = QVBoxLayout()
        self.recent_list = QVBoxLayout()
        for card, lst, key in (
            (self.risk_card, self.risk_list, "risk"),
            (self.absent_card, self.absent_list, "most_absent"),
            (self.recent_card, self.recent_list, "recent"),
        ):
            card.add_header(tr(f"dashboard.list.{key}_title"), tr(f"dashboard.list.{key}_subtitle"))
            lst.setSpacing(2)
            card.body.addLayout(lst)
            card.body.addStretch(1)
        lists.set_items([self.risk_card, self.absent_card, self.recent_card])
        layout.addWidget(lists)
        layout.addStretch(1)
        self.content = scroll_container(body)
        self.stack.addWidget(self.content)

    def header_subtitle(self) -> str:
        course = self.state.course
        return course.display_name if course else self.subtitle

    def refresh(self) -> None:
        course = self.state.course
        if course is None:
            self.stack.setCurrentWidget(self.welcome)
            return
        stats = self.ctx.statistics.course_statistics(course.id)
        self.stats = stats
        d = stats.dashboard
        if d.total_sessions == 0:
            self.no_sessions.set_text(
                tr(
                    "dashboard.no_sessions_text",
                    students=trn("plural.students", d.total_students),
                    course=course.name,
                )
            )
            self.stack.setCurrentWidget(self.no_sessions)
            return
        self.stack.setCurrentWidget(self.content)
        thresholds = self.ctx.settings.load().thresholds

        self.c_students.set_value(str(d.total_students), tr("dashboard.hint.students"))
        self.c_sessions.set_value(str(d.total_sessions), tr("dashboard.hint.sessions"))
        self.c_average.set_value(format_percent(d.average_percentage), tr("dashboard.hint.average"))
        self.c_present.set_value(str(d.total_present), tr("dashboard.hint.present"))
        self.c_absent.set_value(str(d.total_absent), tr("dashboard.hint.absent"))
        self.c_perfect.set_value(
            str(len(d.perfect_students)),
            tr("dashboard.hint.perfect"),
            _names(d.perfect_students, 12),
        )
        self.c_with_abs.set_value(
            str(len(d.students_with_absences)), tr("dashboard.hint.with_absences")
        )
        self.c_highest.set_value(
            format_percent(d.highest_percentage),
            tr(
                "dashboard.hint.highest",
                students=trn("plural.students", len(d.highest_attendance_students)),
            ),
            _names(d.highest_attendance_students, 12),
        )
        if not d.highest_absence_count:
            most_hint = tr("dashboard.hint.no_absences")
        elif len(d.highest_absence_students) == 1:
            most_hint = d.highest_absence_students[0].student.full_name.title()
        else:
            most_hint = tr(
                "dashboard.hint.most_absences",
                students=trn("plural.students", len(d.highest_absence_students)),
            )
        self.c_most_abs.set_value(
            str(d.highest_absence_count), most_hint, _names(d.highest_absence_students, 12)
        )
        self.c_risk.set_value(
            str(len(d.at_risk_students)),
            tr("dashboard.hint.at_risk", limit=f"{thresholds.at_risk_below:g}"),
            _names(d.at_risk_students, 12),
        )

        self.trend.set_data(d.trend, thresholds.at_risk_below)
        self.distribution.set_data(d.distribution)

        clear_layout(self.risk_list)
        risky = (d.at_risk_students + d.warning_students)[:7]
        if not risky:
            self.risk_list.addWidget(label(tr("dashboard.list.nobody_at_risk"), "Secondary"))
        for s in risky:
            self.risk_list.addWidget(
                self._student_row(
                    s,
                    tr(
                        "dashboard.list.risk_row",
                        percent=format_percent(s.percentage),
                        absences=trn("plural.absences", s.absent),
                    ),
                )
            )
        clear_layout(self.absent_list)
        most = sorted(
            (s for s in stats.students if s.absent), key=lambda s: (-s.absent, s.percentage or 0)
        )[:7]
        if not most:
            self.absent_list.addWidget(label(tr("dashboard.list.no_absences"), "Secondary"))
        for s in most:
            self.absent_list.addWidget(
                self._student_row(
                    s,
                    tr(
                        "dashboard.list.absent_row",
                        absences=trn("plural.absences", s.absent),
                        sessions=s.sessions,
                    ),
                )
            )
        clear_layout(self.recent_list)
        for sess in list(reversed(d.trend))[:7]:
            chip = StatusChip(
                text=format_percent(sess.percentage, 0), dot=theme.ACCENT, soft=theme.ACCENT_SOFT
            )
            self.recent_list.addWidget(
                ListRow(
                    f"#{sess.session.session_number}  {sess.session.label}",
                    tr(
                        "dashboard.list.recent_row",
                        date=format_date(sess.session.session_date, "weekday_date"),
                        present=sess.present,
                        absent=sess.absent,
                    ),
                    chip,
                    lambda sid=sess.session.id: self.window_.open_session(sid),
                )
            )

    def _student_row(self, s: StudentStats, subtitle: str) -> ListRow:
        return ListRow(
            s.student.full_name.title(),
            f"{s.student.student_number} · {subtitle}",
            StatusChip(s.standing),
            lambda st=s: self.window_.open_student(st),
        )
