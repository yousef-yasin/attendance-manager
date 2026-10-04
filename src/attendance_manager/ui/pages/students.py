from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLineEdit,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.models import StudentStanding
from attendance_manager.domain.statistics import CourseStatistics, StudentStats
from attendance_manager.i18n import tr, trn
from attendance_manager.ui import theme
from attendance_manager.ui.icons import icon
from attendance_manager.ui.pages.base import Page
from attendance_manager.ui.widgets.common import EmptyState, button, label, standing_label
from attendance_manager.ui.widgets.tables import (
    PAYLOAD_ROLE,
    ChipDelegate,
    Column,
    ObjectTableModel,
    PercentDelegate,
    SearchFilterProxy,
    apply_column_widths,
    configure_table,
    install_delegates,
    mapping_column,
)

# Stable filter ids -> predicate. Labels come from "students.filter.<id>".
FILTERS: dict[str, object] = {
    "all": lambda s: s.student.is_active,
    "perfect": lambda s: s.standing is StudentStanding.PERFECT,
    "good": lambda s: s.standing is StudentStanding.GOOD,
    "warning": lambda s: s.standing is StudentStanding.WARNING,
    "at_risk": lambda s: s.standing is StudentStanding.AT_RISK,
    "with_absences": lambda s: s.absent > 0,
    "no_absences": lambda s: s.sessions > 0 and s.absent == 0,
    "inactive": lambda s: not s.student.is_active,
}


def student_columns(info_columns: list[str]) -> list[Column]:
    cols = [
        Column(tr("students.col.id"), lambda s: s.student.student_number, width=120),
        Column(tr("students.col.name"), lambda s: s.student.full_name, width=280),
    ]
    cols += [
        Column(tr("students.col.present"), lambda s: s.present, align="right", width=80),
        Column(tr("students.col.absent"), lambda s: s.absent, align="right", width=80),
        Column(tr("students.col.percent"), lambda s: s.percentage, kind="percent", width=190),
        Column(
            tr("students.col.status"),
            lambda s: s.standing if s.student.is_active else "not_enrolled",
            display=lambda s: (
                standing_label(s.standing) if s.student.is_active else tr("status.not_enrolled")
            ),
            kind="chip",
            width=150,
        ),
    ]
    cols += [mapping_column(name, lambda s: s.student.info) for name in info_columns]
    return cols


class StudentsPage(Page):
    key = "students"
    needs_course = True

    def __init__(self, window) -> None:
        super().__init__(window)
        self.stats: CourseStatistics | None = None
        self._columns_key: tuple[str, ...] | None = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.no_course = EmptyState(
            "students",
            tr("students.no_course_title"),
            tr("students.no_course_text"),
            [button(tr("actions.create_course"), "primary", "plus", window.create_course)],
        )
        self.stack.addWidget(self.no_course)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 8, 28, 24)
        layout.setSpacing(12)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("students.search_placeholder"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(
            QAction(icon("search", theme.MUTED), "", self.search),
            QLineEdit.ActionPosition.LeadingPosition,
        )
        self.search.setMinimumWidth(340)
        self.filter = QComboBox()
        for filter_id in FILTERS:
            self.filter.addItem(tr(f"students.filter.{filter_id}"), filter_id)
        self.filter.setToolTip(tr("students.filter_tooltip"))
        self.filter.setMinimumWidth(190)
        self.count = label("", "Secondary")
        bar.addWidget(self.search, 2)
        bar.addWidget(self.filter)
        bar.addSpacing(8)
        bar.addWidget(self.count)
        bar.addStretch(1)
        self.open_btn = button(tr("actions.open_details"), "", "eye", self.open_selected)
        bar.addWidget(self.open_btn)
        layout.addLayout(bar)

        self.model = ObjectTableModel([])
        self.proxy = SearchFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        configure_table(self.table, 42)
        self.table.setSortingEnabled(True)
        self._percent = PercentDelegate(
            lambda: (
                self.ctx.settings.load().at_risk_below,
                self.ctx.settings.load().warning_below,
            ),
            self.table,
        )
        self._chip = ChipDelegate(self.table)
        self.table.doubleClicked.connect(lambda _: self.open_selected())
        self.table.selectionModel().selectionChanged.connect(
            lambda *_: self.open_btn.setEnabled(self._selected() is not None)
        )
        QShortcut(
            QKeySequence(Qt.Key.Key_Return),
            self.table,
            self.open_selected,
            context=Qt.ShortcutContext.WidgetShortcut,
        )
        layout.addWidget(self.table, 1)
        self.stack.addWidget(content)
        self.content = content

        self.search.textChanged.connect(self._apply_filter)
        self.filter.currentIndexChanged.connect(self._apply_filter)
        self._apply_filter()

    def header_subtitle(self) -> str:
        course = self.state.course
        return course.display_name if course else self.subtitle

    def set_filter(self, filter_id: str) -> None:
        self.search.clear()
        index = self.filter.findData(filter_id)
        self.filter.setCurrentIndex(max(0, index))

    def focus_search(self) -> None:
        self.search.setFocus()
        self.search.selectAll()

    def refresh(self) -> None:
        course = self.state.course
        if course is None:
            self.stack.setCurrentWidget(self.no_course)
            return
        self.stack.setCurrentWidget(self.content)
        self.stats = self.ctx.statistics.course_statistics(course.id)
        info = self.ctx.courses.info_columns(course.id)
        columns = student_columns(info)
        key = tuple(c.title for c in columns)
        self.model.set_rows(self.stats.students, columns)
        if key != self._columns_key:
            install_delegates(self.table, columns, self._percent, self._chip)
            apply_column_widths(self.table, columns)
            self.table.horizontalHeader().setStretchLastSection(True)
            self.table.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
            self._columns_key = key
        self._apply_filter()

    def _apply_filter(self) -> None:
        predicate = FILTERS.get(self.filter.currentData() or "all")
        self.proxy.set_predicate(predicate)  # type: ignore[arg-type]
        self.proxy.set_search(self.search.text())
        total = sum(1 for s in (self.stats.students if self.stats else []) if s.student.is_active)
        shown = self.proxy.rowCount()
        self.count.setText(tr("students.showing", shown=shown, total=trn("plural.students", total)))
        self.open_btn.setEnabled(self._selected() is not None)

    def _selected(self) -> StudentStats | None:
        rows = self.table.selectionModel().selectedRows()
        return self.proxy.data(rows[0], PAYLOAD_ROLE) if rows else None

    def open_selected(self) -> None:
        s = self._selected()
        if s is None and self.proxy.rowCount() == 1:
            s = self.proxy.data(self.proxy.index(0, 0), PAYLOAD_ROLE)
        if s is not None:
            self.window_.open_student(s)
