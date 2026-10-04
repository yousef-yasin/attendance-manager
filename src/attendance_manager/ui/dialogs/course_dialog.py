"""Create / edit a course. Creating is a 2-step wizard: details, then master student list."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QStackedWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.errors import AttendanceError, ValidationError
from attendance_manager.domain.models import Course
from attendance_manager.i18n import is_rtl, tr, tr_list, trn
from attendance_manager.importing.importer import (
    LoadedFile,
    RosterPreview,
    load_file,
)
from attendance_manager.services.context import AppContext
from attendance_manager.services.course_service import CourseDetails
from attendance_manager.ui.dialogs.file_loading import resolve_mapping
from attendance_manager.ui.dialogs.messages import confirm, show_error
from attendance_manager.ui.icons import directional
from attendance_manager.ui.widgets.common import Banner, button, clear_layout, label
from attendance_manager.ui.widgets.drop_zone import DropZone
from attendance_manager.ui.widgets.feedback import BusyOverlay, run_in_background
from attendance_manager.ui.widgets.tables import (
    Column,
    ObjectTableModel,
    apply_column_widths,
    configure_table,
    mapping_column,
)


def roster_columns(info_columns: list[str]) -> list[Column]:
    cols = [
        Column(tr("roster.col.row"), lambda s: s.row_number, align="right", width=70),
        Column(tr("students.col.id"), lambda s: s.student_number, width=130),
        Column(tr("students.col.name"), lambda s: s.full_name, width=280),
    ]
    cols += [mapping_column(name, lambda s: s.info) for name in info_columns]
    return cols


def academic_years() -> list[str]:
    year = dt.date.today().year
    return [f"{year - 1}/{year}", f"{year}/{year + 1}", str(year), str(year + 1)]


class RosterPreviewWidget(QWidget):
    """Summary, warnings and a table of the students found in a master file."""

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        head = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = label("", "SectionTitle")
        self.subtitle = label("", "Secondary", wrap=True)
        texts.addWidget(self.title)
        texts.addWidget(self.subtitle)
        head.addLayout(texts, 1)
        self.adjust_button = button(tr("files.adjust_columns"), "", "columns")
        self.change_button = button(tr("files.choose_another"), "", "folder")
        head.addWidget(self.adjust_button, 0, Qt.AlignmentFlag.AlignTop)
        head.addWidget(self.change_button, 0, Qt.AlignmentFlag.AlignTop)
        layout.addLayout(head)
        self.notices = QVBoxLayout()
        self.notices.setSpacing(6)
        layout.addLayout(self.notices)
        self.model = ObjectTableModel([])
        self.table = QTableView()
        self.table.setModel(self.model)
        configure_table(self.table, 34)
        layout.addWidget(self.table, 1)

    def show_roster(self, roster: RosterPreview) -> None:
        self.title.setText(
            tr("roster.found", students=trn("plural.students", len(roster.students)))
        )
        cols = [c for c in roster.table.column_names]
        self.subtitle.setText(
            tr(
                "roster.source",
                file=roster.table.file_name,
                sheet=roster.table.sheet_name,
                id_column=roster.table.id_column_name,
                name_column=roster.table.name_column_name or tr("roster.none"),
                columns=tr("common.list_separator").join(cols),
            )
        )
        clear_layout(self.notices)
        for warning in roster.warnings[:4]:
            self.notices.addWidget(Banner("warning", warning))
        if len(roster.warnings) > 4:
            self.notices.addWidget(
                Banner("warning", tr("roster.more_notes", count=len(roster.warnings) - 4))
            )
        columns = roster_columns(roster.info_columns)
        self.model.set_rows(roster.students, columns)
        apply_column_widths(self.table, columns)


class CourseDialog(QDialog):
    def __init__(
        self,
        ctx: AppContext,
        parent: QWidget | None = None,
        course: Course | None = None,
        initial_file: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.course = course
        self.created: Course | None = None
        self.loaded: LoadedFile | None = None
        self.roster: RosterPreview | None = None
        editing = course is not None
        self.setWindowTitle(
            tr("course_dialog.window_edit") if editing else tr("course_dialog.window_create")
        )
        self.resize(760, 520) if editing else self.resize(980, 700)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(14)
        root.addWidget(
            label(
                tr("course_dialog.title_edit") if editing else tr("course_dialog.title_create"),
                "PageTitle",
            )
        )
        if not editing:
            steps = QHBoxLayout()
            self.step_labels = [
                label(tr("course_dialog.step1"), "StepLabel"),
                label(tr("course_dialog.step2"), "StepLabel"),
            ]
            for i, s in enumerate(self.step_labels):
                steps.addWidget(s)
                if i == 0:
                    steps.addWidget(label("  ‹  " if is_rtl() else "  ›  ", "Muted"))
            steps.addStretch(1)
            root.addLayout(steps)

        self.pages = QStackedWidget()
        root.addWidget(self.pages, 1)

        # ---- page 1: details
        details = QWidget()
        form = QFormLayout(details)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("course_dialog.name_placeholder"))
        self.name.setMaxLength(150)
        self.section = QLineEdit()
        self.section.setPlaceholderText(tr("course_dialog.section_placeholder"))
        self.section.setMaxLength(50)
        self.semester = QComboBox()
        self.semester.setEditable(True)
        self.semester.addItems(["", *tr_list("course_dialog.semesters")])
        self.year = QComboBox()
        self.year.setEditable(True)
        self.year.addItems(["", *academic_years()])
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText(tr("course_dialog.notes_placeholder"))
        self.notes.setFixedHeight(90)
        form.addRow(label(tr("course_dialog.name"), "FieldLabel"), self.name)
        form.addRow(label(tr("course_dialog.section"), "FieldLabel"), self.section)
        form.addRow(label(tr("course_dialog.semester"), "FieldLabel"), self.semester)
        form.addRow(label(tr("course_dialog.year"), "FieldLabel"), self.year)
        form.addRow(label(tr("course_dialog.notes"), "FieldLabel"), self.notes)
        self.error = label("", wrap=True)
        self.error.setStyleSheet("color: #B42323; font-weight: 600;")
        form.addRow("", self.error)
        self.pages.addWidget(details)

        # ---- page 2: master list
        upload = QWidget()
        up = QVBoxLayout(upload)
        up.setContentsMargins(0, 0, 0, 0)
        self.upload_stack = QStackedWidget()
        self.drop = DropZone(
            tr("course_dialog.drop_title"),
            tr("course_dialog.drop_hint"),
            tr("course_dialog.drop_dialog"),
        )
        self.drop.file_selected.connect(self._load)
        self.preview = RosterPreviewWidget()
        self.preview.change_button.clicked.connect(self.drop.browse)
        self.preview.adjust_button.clicked.connect(self._adjust)
        self.upload_stack.addWidget(self.drop)
        self.upload_stack.addWidget(self.preview)
        up.addWidget(self.upload_stack)
        self.pages.addWidget(upload)
        self.busy = BusyOverlay(upload)

        # ---- buttons
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.cancel = button(tr("actions.cancel"), on_click=self.reject)
        self.back = button(tr("actions.back"), "", directional("chevron-left"), lambda: self._go(0))
        self.next = button(
            tr("actions.next"), "primary", directional("chevron-right"), lambda: self._go(1)
        )
        self.finish = button(
            tr("actions.save_changes") if editing else tr("actions.create_course"),
            "primary",
            "check",
            self._finish,
        )
        for b in (self.cancel, self.back, self.next, self.finish):
            buttons.addWidget(b)
        root.addLayout(buttons)

        if course is not None:
            self.name.setText(course.name)
            self.section.setText(course.section)
            self.semester.setCurrentText(course.semester)
            self.year.setCurrentText(course.year)
            self.notes.setPlainText(course.notes)
        self.name.textChanged.connect(lambda: self.error.setText(""))
        self._go(0)
        self.name.setFocus()
        self._pending_file: Path | None = initial_file if not editing else None

    # ------------------------------------------------------------ navigation
    def details(self) -> CourseDetails:
        return CourseDetails(
            name=self.name.text(),
            section=self.section.text(),
            semester=self.semester.currentText(),
            year=self.year.currentText(),
            notes=self.notes.toPlainText(),
        ).cleaned()

    def _go(self, page: int) -> None:
        editing = self.course is not None
        if page == 1:
            try:
                self.details().validate()
            except ValidationError as exc:
                self.error.setText(exc.message)
                self.name.setFocus()
                return
        self.pages.setCurrentIndex(page)
        self.back.setVisible(not editing and page == 1)
        self.next.setVisible(not editing and page == 0)
        self.finish.setVisible(editing or page == 1)
        self.finish.setEnabled(editing or self.roster is not None)
        (self.finish if editing else self.next if page == 0 else self.finish).setDefault(True)
        if not editing:
            for i, s in enumerate(self.step_labels):
                s.setProperty("active", "true" if i == page else "false")
                s.style().unpolish(s)
                s.style().polish(s)
        if page == 1 and self._pending_file is not None:
            path, self._pending_file = self._pending_file, None
            self._load(path)

    # ---------------------------------------------------------------- upload
    def _load(self, path: Path) -> None:
        self.busy.show_busy(tr("files.reading", file=path.name))
        run_in_background(lambda: load_file(path), self._loaded, self._load_failed)

    def _load_failed(self, exc: Exception) -> None:
        self.busy.hide_busy()
        show_error(self, exc, tr("errors.title.file_unusable"))

    def _loaded(self, loaded: LoadedFile) -> None:
        self.busy.hide_busy()
        mapping = resolve_mapping(self, loaded, "roster")
        if mapping is None:
            return
        self._build(loaded, mapping)

    def _build(self, loaded: LoadedFile, mapping) -> None:
        try:
            roster = self.ctx.courses.roster_preview(loaded, mapping)
        except AttendanceError as exc:
            show_error(self, exc, tr("errors.title.no_students"))
            return
        self.loaded, self.roster = loaded, roster
        self.preview.show_roster(roster)
        self.upload_stack.setCurrentIndex(1)
        self.finish.setEnabled(True)

    def _adjust(self) -> None:
        if self.loaded is None or self.roster is None:
            return
        mapping = resolve_mapping(
            self,
            self.loaded,
            "roster",
            force=True,
            current=self.roster.table.mapping,
        )
        if mapping is not None:
            self._build(self.loaded, mapping)

    # ---------------------------------------------------------------- finish
    def _finish(self) -> None:
        try:
            if self.course is not None:
                self.created = self.ctx.courses.update_course(self.course.id, self.details())
                self.accept()
                return
            if self.roster is None or self.loaded is None:
                return
            try:
                self.created = self.ctx.courses.create_course(
                    self.details(), self.roster, self.loaded.workbook.path
                )
            except ValidationError as exc:
                if exc.details != "duplicate-course":
                    raise
                if not confirm(
                    self,
                    tr("course_dialog.duplicate_title"),
                    tr("course_dialog.duplicate_message", message=exc.message),
                    tr("course_dialog.duplicate_button"),
                ):
                    return
                self.created = self.ctx.courses.create_course(
                    self.details(), self.roster, self.loaded.workbook.path, allow_duplicate=True
                )
            self.accept()
        except ValidationError as exc:
            if self.pages.currentIndex() == 0 or self.course is not None:
                self.error.setText(exc.message)
            else:
                show_error(self, exc, tr("errors.title.check_details"))
        except Exception as exc:
            show_error(self, exc)
