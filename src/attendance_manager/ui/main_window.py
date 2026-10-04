from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QCloseEvent, QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from attendance_manager import __version__
from attendance_manager.domain.models import AttendanceSession, Course, CourseStatus
from attendance_manager.domain.statistics import StudentStats
from attendance_manager.i18n import format_date, get_language, paragraph, tr, trn
from attendance_manager.paths import resource_path
from attendance_manager.services.context import AppContext
from attendance_manager.ui import theme
from attendance_manager.ui.dialogs.attendance_dialog import AddAttendanceDialog
from attendance_manager.ui.dialogs.course_dialog import CourseDialog
from attendance_manager.ui.dialogs.detail_dialogs import (
    SessionDetailDialog,
    StudentDetailDialog,
    open_path,
)
from attendance_manager.ui.dialogs.messages import confirm, show_error
from attendance_manager.ui.dialogs.small_dialogs import EditSessionDialog, UpdateRosterDialog
from attendance_manager.ui.icons import icon, pixmap
from attendance_manager.ui.language import apply_language, save_language
from attendance_manager.ui.pages.backup import BackupPage
from attendance_manager.ui.pages.base import Page
from attendance_manager.ui.pages.courses import CoursesPage
from attendance_manager.ui.pages.dashboard import DashboardPage
from attendance_manager.ui.pages.reports import ReportsPage
from attendance_manager.ui.pages.sessions import SessionsPage
from attendance_manager.ui.pages.settings import SettingsPage
from attendance_manager.ui.pages.students import StudentsPage
from attendance_manager.ui.state import AppState
from attendance_manager.ui.widgets.common import button, label
from attendance_manager.ui.widgets.drop_zone import spreadsheet_from_mime
from attendance_manager.ui.widgets.feedback import ToastManager
from attendance_manager.ui.widgets.language_switch import LanguageSwitch

log = logging.getLogger(__name__)

# (page key, navigation label key, icon)
NAV = [
    ("dashboard", "nav.dashboard", "dashboard"),
    ("courses", "nav.courses", "courses"),
    ("sessions", "nav.sessions", "sessions"),
    ("students", "nav.students", "students"),
    ("reports", "nav.reports", "reports"),
    ("settings", "nav.settings", "settings"),
    ("backup", "nav.backup", "backup"),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.state = AppState(ctx)
        self.state.initialise()
        icon_file = resource_path("ui/assets/app_icon.png")
        if icon_file.exists():
            self.setWindowIcon(QIcon(str(icon_file)))
        self.resize(1360, 860)
        self.setMinimumSize(980, 640)
        self.setAcceptDrops(True)
        self.state.course_changed.connect(self._on_data_changed)
        self.state.data_changed.connect(self._on_data_changed)
        self._install_shortcuts()
        self._build_ui()
        self.navigate(
            "dashboard"
            if self.state.course_id
            else ("courses" if self._has_courses() else "dashboard")
        )

    # ------------------------------------------------------------------ layout
    def _build_ui(self) -> None:
        """(Re)build every widget from the translation catalog.

        Called at start-up and whenever the language changes, so every visible
        string comes from the current language with no per-widget bookkeeping.
        """
        self.setWindowTitle(tr("app.name"))
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_sidebar())
        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        main_layout.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack, 1)
        root.addWidget(main, 1)
        previous = self.takeCentralWidget()
        if previous is not None:
            # Detach the old widget tree right away, but keep a Python reference until
            # Qt's deferred deletion runs: destroying it synchronously while one of its
            # buttons is still emitting a signal would crash.
            previous.hide()
            previous.setParent(None)
            previous.deleteLater()
            self._retired_widgets = [previous]
        self.setCentralWidget(central)
        self.toasts = ToastManager(main)

        self.pages: dict[str, Page] = {}
        for page_cls in (
            DashboardPage,
            CoursesPage,
            SessionsPage,
            StudentsPage,
            ReportsPage,
            SettingsPage,
            BackupPage,
        ):
            page = page_cls(self)
            self.pages[page.key] = page
            self.stack.addWidget(page)
        self._refresh_course_selector()

    def _build_sidebar(self) -> QWidget:
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(248)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(4)
        brand = QHBoxLayout()
        logo = QLabel()
        logo.setFixedSize(38, 38)
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setPixmap(pixmap("sessions", "#FFFFFF", 20))
        logo.setStyleSheet(f"background: {theme.ACCENT}; border-radius: 10px;")
        brand.addWidget(logo)
        texts = QVBoxLayout()
        texts.setSpacing(0)
        for key in ("app.name_line1", "app.name_line2"):
            line = QLabel(tr(key))
            line.setObjectName("AppTitle")
            texts.addWidget(line)
        brand.addLayout(texts, 1)
        layout.addLayout(brand)
        layout.addSpacing(22)
        self.nav_group = QButtonGroup(side)
        self.nav_group.setExclusive(True)
        self.nav_buttons: dict[str, QPushButton] = {}
        for index, (key, text_key, icon_name) in enumerate(NAV):
            text = tr(text_key)
            b = QPushButton("  " + text.replace("&", "&&"))
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setIcon(icon(icon_name, theme.SIDEBAR_TEXT, "#FFFFFF"))
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setToolTip(tr("nav.tooltip", page=text, shortcut=f"Ctrl+{index + 1}"))
            # "toggled" also fires when assistive technology activates the button.
            b.toggled.connect(lambda checked, k=key: self._nav_toggled(k, checked))
            self.nav_group.addButton(b)
            self.nav_buttons[key] = b
            layout.addWidget(b)
            if key == "reports":
                layout.addSpacing(14)
        layout.addStretch(1)
        footer = QHBoxLayout()
        shield = QLabel()
        shield.setPixmap(pixmap("shield", "#7FD18B", 16))
        footer.addWidget(shield, 0, Qt.AlignmentFlag.AlignTop)
        note = QLabel(tr("app.offline_note", version=__version__))
        note.setObjectName("SidebarFooter")
        note.setWordWrap(True)
        footer.addWidget(note, 1)
        layout.addLayout(footer)
        return side

    def _build_topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(28, 22, 28, 14)
        row.setSpacing(12)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.page_title = label("", "PageTitle")
        self.page_subtitle = label("", "PageSubtitle")
        for lbl in (self.page_title, self.page_subtitle):
            # Let long titles clip instead of forcing the bar wider than the window.
            lbl.setMinimumWidth(1)
            lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            texts.addWidget(lbl)
        row.addLayout(texts, 1)
        self.language_switch = LanguageSwitch(get_language())
        # Queued: the rebuild replaces the switch itself, so it must run after the
        # click has finished being delivered.
        self.language_switch.language_selected.connect(
            self.change_language, Qt.ConnectionType.QueuedConnection
        )
        row.addWidget(self.language_switch)
        row.addSpacing(6)
        self.course_caption = label(tr("topbar.course"), "FieldLabel")
        row.addWidget(self.course_caption)
        self.course_selector = QComboBox()
        self.course_selector.setObjectName("CourseSelector")
        self.course_selector.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.course_selector.setMinimumContentsLength(20)
        self.course_selector.setMaximumWidth(400)
        self.course_selector.setToolTip(tr("topbar.switch_course"))
        self.course_selector.activated.connect(self._course_selected)
        row.addWidget(self.course_selector)
        self.primary_action = button(
            tr("actions.add_attendance"), "primary", "upload", self._primary_clicked
        )
        self.primary_action.setToolTip(tr("topbar.add_attendance_tooltip"))
        row.addWidget(self.primary_action)
        return bar

    def _install_shortcuts(self) -> None:
        for index, (key, _, _) in enumerate(NAV):
            QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self, lambda k=key: self.navigate(k))
        QShortcut(QKeySequence("Ctrl+N"), self, self.create_course)
        QShortcut(QKeySequence("Ctrl+U"), self, lambda: self.add_attendance())
        QShortcut(QKeySequence("Ctrl+F"), self, self._focus_search)
        QShortcut(QKeySequence("Ctrl+E"), self, self._shortcut_report)
        QShortcut(QKeySequence("F5"), self, self._on_data_changed)

    # ---------------------------------------------------------------- language
    def change_language(self, language: str) -> None:
        if language == get_language():
            return
        current = self.current_page_key()
        save_language(self.ctx, language)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            apply_language(app, language)
        self._build_ui()
        self.navigate(current)
        self.toast("success", tr("toast.language_changed"))

    def current_page_key(self) -> str:
        page = self.stack.currentWidget()
        return page.key if isinstance(page, Page) else "dashboard"

    # -------------------------------------------------------------- navigation
    def _nav_toggled(self, key: str, checked: bool = True) -> None:
        if not checked:
            return
        if self.current_page_key() != key or self.stack.currentWidget() is not self.pages.get(key):
            self.navigate(key)

    def navigate(self, key: str) -> None:
        page = self.pages[key]
        self.stack.setCurrentWidget(page)
        self.nav_buttons[key].setChecked(True)
        if page._dirty:
            # Don't depend on show-event timing (e.g. right after a language rebuild).
            page.refresh_now()
        self._update_header()

    def _update_header(self) -> None:
        page = self.stack.currentWidget()
        if isinstance(page, Page):
            self.page_title.setText(page.title)
            self.page_subtitle.setText(paragraph(page.header_subtitle()))

    def _has_courses(self) -> bool:
        return bool(self.ctx.courses.list_courses(include_archived=True))

    def _refresh_course_selector(self) -> None:
        courses = self.ctx.courses.list_courses(include_archived=False)
        current = self.state.course
        if current is not None and current.status is CourseStatus.ARCHIVED:
            courses.append(current)
        self.course_selector.blockSignals(True)
        self.course_selector.clear()
        for c in courses:
            text = c.display_name
            if c.status is CourseStatus.ARCHIVED:
                text = tr("topbar.archived_suffix", name=text)
            self.course_selector.addItem(paragraph(text), c.id)
        idx = self.course_selector.findData(self.state.course_id)
        self.course_selector.setCurrentIndex(idx)
        self.course_selector.blockSignals(False)
        has = bool(courses)
        self.course_selector.setVisible(has)
        self.course_caption.setVisible(has)
        if has:
            self.primary_action.setText(tr("actions.add_attendance"))
            self.primary_action.setIcon(icon("upload", "#FFFFFF"))
            enabled = current is not None and current.status is CourseStatus.ACTIVE
            self.primary_action.setEnabled(enabled)
        else:
            self.primary_action.setText(tr("actions.create_course"))
            self.primary_action.setIcon(icon("plus", "#FFFFFF"))
            self.primary_action.setEnabled(True)

    def _course_selected(self, index: int) -> None:
        self.state.select_course(self.course_selector.itemData(index))

    def _primary_clicked(self) -> None:
        if self.course_selector.count() == 0:
            self.create_course()
        else:
            self.add_attendance()

    def _on_data_changed(self) -> None:
        if not hasattr(self, "pages"):
            return
        self._refresh_course_selector()
        for page in self.pages.values():
            page.mark_dirty()
        self._update_header()

    def _shortcut_report(self) -> None:
        self.navigate("reports")
        self.pages["reports"].generate()  # type: ignore[attr-defined]

    def _focus_search(self) -> None:
        self.navigate("students")
        self.pages["students"].focus_search()  # type: ignore[attr-defined]

    def show_students(self, filter_id: str) -> None:
        self.navigate("students")
        self.pages["students"].set_filter(filter_id)  # type: ignore[attr-defined]

    def toast(
        self,
        kind: str,
        title: str,
        message: str = "",
        actions: list[tuple[str, Callable[[], None]]] | None = None,
        timeout_ms: int = 5000,
    ) -> None:
        self.toasts.show(kind, title, message, actions, timeout_ms)

    # ------------------------------------------------------------------ actions
    def create_course(self, initial_file: Path | None = None) -> None:
        dialog = CourseDialog(self.ctx, self, initial_file=initial_file)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.created is not None:
            course = dialog.created
            students, _ = self.ctx.courses.counts(course.id)
            self.state.select_course(course.id)
            self.state.notify_changed()
            self.navigate("dashboard")
            self.toast(
                "success",
                tr("toast.course_created"),
                tr(
                    "toast.course_created_detail",
                    course=course.display_name,
                    students=trn("plural.students", students),
                ),
                [(tr("actions.add_attendance"), lambda: self.add_attendance())],
            )

    def edit_course(self, course: Course) -> None:
        dialog = CourseDialog(self.ctx, self, course=course)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.state.notify_changed()
            self.toast("success", tr("toast.course_updated"))

    def update_roster(self, course: Course) -> None:
        dialog = UpdateRosterDialog(self.ctx, course.id, self)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.diff is not None:
            d = dialog.diff
            self.state.notify_changed()
            self.toast(
                "success",
                tr("toast.roster_updated"),
                tr(
                    "toast.roster_updated_detail",
                    added=trn("plural.students", len(d.added)),
                    updated=trn("plural.students", len(d.updated)),
                ),
            )

    def set_course_archived(self, course: Course, archived: bool) -> None:
        if archived and not confirm(
            self,
            tr("confirm.archive.title"),
            tr("confirm.archive.message", course=course.display_name),
            tr("confirm.archive.button"),
        ):
            return
        try:
            self.ctx.courses.set_archived(course.id, archived)
        except Exception as exc:
            show_error(self, exc)
            return
        if archived and self.state.course_id == course.id:
            remaining = self.ctx.courses.list_courses(include_archived=False)
            self.state.select_course(remaining[0].id if remaining else None)
        self.state.notify_changed()
        self.toast(
            "success",
            tr("toast.course_archived") if archived else tr("toast.course_restored"),
            course.display_name,
        )

    def delete_course(self, course: Course) -> None:
        students, sessions = self.ctx.courses.counts(course.id)
        phrase = tr("confirm.delete.phrase")
        if not confirm(
            self,
            tr("confirm.delete.title"),
            tr(
                "confirm.delete.message",
                course=course.display_name,
                students=trn("plural.students", students),
                sessions=trn("plural.sessions", sessions),
            ),
            tr("confirm.delete.button"),
            danger=True,
            type_to_confirm=phrase,
            details=tr("confirm.delete.details"),
        ):
            return
        try:
            backup = self.ctx.courses.delete_course(course.id)
        except Exception as exc:
            show_error(self, exc, tr("errors.title.course_not_deleted"))
            return
        if self.state.course_id == course.id:
            remaining = self.ctx.courses.list_courses(include_archived=False)
            self.state.select_course(remaining[0].id if remaining else None)
        self.state.notify_changed()
        self.toast(
            "success",
            tr("toast.course_deleted"),
            tr("toast.course_deleted_detail", file=backup.name),
        )

    def add_attendance(self, initial_file: Path | None = None) -> None:
        course = self.state.course
        if course is None:
            if self._has_courses():
                self.navigate("courses")
                self.toast("info", tr("toast.select_course"), tr("toast.select_course_detail"))
            else:
                self.create_course()
            return
        if course.status is CourseStatus.ARCHIVED:
            self.toast(
                "warning", tr("toast.course_is_archived"), tr("toast.course_is_archived_detail")
            )
            return
        dialog = AddAttendanceDialog(self.ctx, course.id, self, initial_file)
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.saved is not None:
            s = dialog.saved
            self.state.notify_changed()
            self.toast(
                "success",
                tr("toast.session_saved", session=s.label),
                tr("toast.session_saved_detail", present=s.present_count, absent=s.absent_count),
                [(tr("actions.view_session"), lambda: self.open_session(s.id))],
            )

    def open_student(self, stats: StudentStats) -> None:
        course_stats = self.ctx.statistics.course_statistics(stats.student.course_id)
        fresh = course_stats.for_student(stats.student.id) or stats
        StudentDetailDialog(self.ctx, fresh, course_stats.sessions, self).exec()

    def open_session(self, session_id: int) -> None:
        try:
            SessionDetailDialog(self.ctx, session_id, self).exec()
        except Exception as exc:
            show_error(self, exc)

    def open_original(self, session_id: int) -> None:
        try:
            if not self.ctx.attendance.verify_original(session_id):
                raise FileNotFoundError(tr("errors.original_missing"))
            open_path(self.ctx.attendance.original_file_copy(session_id))
        except Exception as exc:
            show_error(self, exc, tr("errors.title.original_not_opened"))

    def export_session(self, session: AttendanceSession) -> None:
        default = (
            Path.home() / "Documents" / f"{session.label} - {session.session_date:%Y-%m-%d}.xlsx"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialogs.export_session"), str(default), tr("files.xlsx_filter")
        )
        if not path:
            return
        try:
            out = self.ctx.reports.export_session(session.id, Path(path))
        except Exception as exc:
            show_error(self, exc, tr("errors.title.session_not_exported"))
            return
        self.toast(
            "success",
            tr("toast.session_exported"),
            out.name,
            [(tr("actions.open"), lambda: open_path(out))],
        )

    def edit_session(self, session: AttendanceSession) -> None:
        if EditSessionDialog(self.ctx, session, self).exec() == QDialog.DialogCode.Accepted:
            self.state.notify_changed()
            self.toast("success", tr("toast.session_updated"))

    def remove_session(self, session: AttendanceSession) -> None:
        reason, ok = QInputDialog.getText(
            self,
            tr("remove_session.title"),
            tr(
                "remove_session.prompt",
                session=session.label,
                date=format_date(session.session_date),
            ),
        )
        if not ok:
            return
        try:
            self.ctx.attendance.remove_session(session.id, reason)
        except Exception as exc:
            show_error(self, exc)
            return
        self.state.notify_changed()
        self.toast(
            "success",
            tr("toast.session_removed"),
            session.label,
            [(tr("actions.undo"), lambda: self.restore_session(session))],
        )

    def restore_session(self, session: AttendanceSession) -> None:
        try:
            self.ctx.attendance.restore_session(session.id)
        except Exception as exc:
            show_error(self, exc)
            return
        self.state.notify_changed()
        self.toast("success", tr("toast.session_restored"), session.label)

    def after_restore(self) -> None:
        self.state.initialise()
        self.state.notify_changed()
        self.state.course_changed.emit()

    # ------------------------------------------------------------- drag & drop
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if spreadsheet_from_mime(event):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        path = spreadsheet_from_mime(event)
        if path is None:
            return
        event.acceptProposedAction()
        QTimer.singleShot(
            0,
            lambda: (
                self.create_course(path) if self.state.course is None else self.add_attendance(path)
            ),
        )

    # ------------------------------------------------------------------ closing
    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            self.ctx.backups.auto_backup_if_due()
        except Exception:
            log.exception("Automatic backup on exit failed")
        super().closeEvent(event)
