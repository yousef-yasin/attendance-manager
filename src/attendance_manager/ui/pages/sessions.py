from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QMenu,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.models import AttendanceSession, SessionStatus
from attendance_manager.i18n import format_date, tr, trn
from attendance_manager.ui import theme
from attendance_manager.ui.icons import icon
from attendance_manager.ui.pages.base import Page
from attendance_manager.ui.widgets.common import EmptyState, button, label
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
)


def session_columns() -> list[Column]:
    """Built on demand so headers follow the current language."""
    return [
        Column("#", lambda s: s.session_number, align="right", width=48),
        Column(tr("sessions.col.session"), lambda s: s.label, width=170),
        Column(
            tr("sessions.col.date"),
            lambda s: s.session_date.isoformat(),
            display=lambda s: format_date(s.session_date, "weekday_date"),
            width=150,
        ),
        Column(tr("sessions.col.file"), lambda s: s.original_filename, width=120),
        Column(
            tr("sessions.col.uploaded"),
            lambda s: s.uploaded_at.isoformat(),
            display=lambda s: format_date(s.uploaded_at.astimezone(), "datetime"),
            width=150,
        ),
        Column(tr("sessions.col.present"), lambda s: s.present_count, align="right", width=70),
        Column(tr("sessions.col.absent"), lambda s: s.absent_count, align="right", width=70),
        Column(tr("sessions.col.attendance"), lambda s: s.percentage, kind="percent", width=150),
        Column(
            tr("sessions.col.status"),
            lambda s: "removed" if s.status is SessionStatus.REMOVED else "active",
            display=lambda s: tr(
                "status.removed" if s.status is SessionStatus.REMOVED else "status.active"
            ),
            kind="chip",
            width=110,
        ),
    ]


class SessionsPage(Page):
    key = "sessions"
    needs_course = True

    def __init__(self, window) -> None:
        super().__init__(window)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack)
        self.no_course = EmptyState(
            "courses",
            tr("sessions.no_course_title"),
            tr("sessions.no_course_text"),
            [button(tr("actions.create_course"), "primary", "plus", window.create_course)],
        )
        self.empty = EmptyState(
            "sessions",
            tr("sessions.empty_title"),
            tr("sessions.empty_text"),
            [
                button(
                    tr("actions.add_attendance"),
                    "primary",
                    "upload",
                    lambda: window.add_attendance(),
                )
            ],
        )
        self.stack.addWidget(self.no_course)
        self.stack.addWidget(self.empty)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 8, 28, 24)
        layout.setSpacing(12)
        bar = QHBoxLayout()
        self.show_removed = QCheckBox(tr("sessions.show_removed"))
        self.show_removed.toggled.connect(lambda _: self.refresh_now())
        bar.addWidget(self.show_removed)
        bar.addSpacing(12)
        self.count = label("", "Secondary")
        bar.addWidget(self.count)
        bar.addStretch(1)
        self.view_btn = button(tr("actions.view_details"), "", "eye", self.view_selected)
        self.open_btn = button(tr("actions.open_original"), "", "external", self.open_original)
        self.more_btn = button(tr("common.more"), "", "more")
        self.more_btn.clicked.connect(
            lambda: self._menu(self.more_btn.mapToGlobal(QPoint(0, self.more_btn.height())))
        )
        for b in (self.view_btn, self.open_btn, self.more_btn):
            bar.addWidget(b)
        bar.addSpacing(8)
        bar.addWidget(
            button(
                tr("actions.add_attendance"), "primary", "upload", lambda: window.add_attendance()
            )
        )
        layout.addLayout(bar)
        self.columns = session_columns()
        self.model = ObjectTableModel(self.columns)
        self.proxy = SearchFilterProxy(self)
        self.proxy.setSourceModel(self.model)
        self.table = QTableView()
        self.table.setModel(self.proxy)
        configure_table(self.table, 44)
        self.table.setSortingEnabled(True)
        thresholds = lambda: (  # noqa: E731
            self.ctx.settings.load().at_risk_below,
            self.ctx.settings.load().warning_below,
        )
        install_delegates(
            self.table,
            self.columns,
            PercentDelegate(thresholds, self.table),
            ChipDelegate(self.table),
        )
        self.table.doubleClicked.connect(lambda _: self.view_selected())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(
            lambda pos: self._menu(self.table.viewport().mapToGlobal(pos))
        )
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._update_buttons())
        QShortcut(
            QKeySequence(Qt.Key.Key_Return),
            self.table,
            self.view_selected,
            context=Qt.ShortcutContext.WidgetShortcut,
        )
        layout.addWidget(self.table, 1)
        layout.addWidget(label(tr("sessions.footer_note"), "Muted", wrap=True))
        self.stack.addWidget(content)
        self.content = content
        self._widths_set = False

    def header_subtitle(self) -> str:
        course = self.state.course
        return course.display_name if course else self.subtitle

    def refresh(self) -> None:
        course = self.state.course
        if course is None:
            self.stack.setCurrentWidget(self.no_course)
            return
        sessions = self.ctx.attendance.sessions(course.id, include_removed=True)
        if not sessions:
            self.stack.setCurrentWidget(self.empty)
            return
        self.stack.setCurrentWidget(self.content)
        removed = sum(1 for s in sessions if s.status is SessionStatus.REMOVED)
        visible = [
            s for s in sessions if self.show_removed.isChecked() or s.status is SessionStatus.ACTIVE
        ]
        self.model.set_rows(visible)
        if not self._widths_set:
            # Compact fixed widths; the session title takes the remaining space.
            apply_column_widths(self.table, self.columns, stretch_title=tr("sessions.col.session"))
            self.table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
            self._widths_set = True
        text = trn("plural.active_sessions", len(sessions) - removed)
        if removed:
            text = tr("sessions.count_with_removed", active=text, removed=removed)
        self.count.setText(text)
        self._update_buttons()

    def selected(self) -> AttendanceSession | None:
        rows = self.table.selectionModel().selectedRows()
        if not rows:
            return None
        return self.proxy.data(rows[0], PAYLOAD_ROLE)

    def _update_buttons(self) -> None:
        has = self.selected() is not None
        for b in (self.view_btn, self.open_btn, self.more_btn):
            b.setEnabled(has)

    def view_selected(self) -> None:
        s = self.selected()
        if s is not None:
            self.window_.open_session(s.id)

    def open_original(self) -> None:
        s = self.selected()
        if s is not None:
            self.window_.open_original(s.id)

    def _menu(self, pos: QPoint) -> None:
        s = self.selected()
        if s is None:
            return
        menu = QMenu(self)
        menu.addAction(icon("eye", theme.INK_2), tr("actions.view_details"), self.view_selected)
        menu.addAction(
            icon("external", theme.INK_2), tr("actions.open_original"), self.open_original
        )
        menu.addAction(
            icon("download", theme.INK_2),
            tr("sessions.menu.export"),
            lambda: self.window_.export_session(s),
        )
        menu.addAction(
            icon("edit", theme.INK_2),
            tr("sessions.menu.rename"),
            lambda: self.window_.edit_session(s),
        )
        menu.addSeparator()
        if s.status is SessionStatus.REMOVED:
            menu.addAction(
                icon("undo", theme.INK_2),
                tr("sessions.menu.restore"),
                lambda: self.window_.restore_session(s),
            )
        else:
            menu.addAction(
                icon("archive", theme.CRITICAL),
                tr("sessions.menu.remove"),
                lambda: self.window_.remove_session(s),
            )
        menu.exec(pos)
