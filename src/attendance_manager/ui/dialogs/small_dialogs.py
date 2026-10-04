"""Update-roster and edit-session dialogs."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.models import AttendanceSession
from attendance_manager.i18n import paragraph, tr, trn
from attendance_manager.importing.importer import LoadedFile, RosterPreview, load_file
from attendance_manager.services.context import AppContext
from attendance_manager.services.course_service import RosterDiff
from attendance_manager.ui.dialogs.course_dialog import RosterPreviewWidget
from attendance_manager.ui.dialogs.file_loading import resolve_mapping
from attendance_manager.ui.dialogs.messages import show_error
from attendance_manager.ui.widgets.common import Banner, button, clear_layout, label
from attendance_manager.ui.widgets.drop_zone import DropZone
from attendance_manager.ui.widgets.feedback import BusyOverlay, run_in_background


class UpdateRosterDialog(QDialog):
    """Upload a newer master list. Adds/updates students; never deletes history."""

    def __init__(self, ctx: AppContext, course_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.course_id = course_id
        self.loaded: LoadedFile | None = None
        self.roster: RosterPreview | None = None
        self.diff: RosterDiff | None = None
        course = ctx.courses.get(course_id)
        self.setWindowTitle(tr("roster_dialog.window"))
        self.resize(980, 700)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(12)
        root.addWidget(label(tr("roster_dialog.title"), "PageTitle"))
        root.addWidget(
            label(
                paragraph(tr("roster_dialog.subtitle", course=course.display_name)),
                "PageSubtitle",
                wrap=True,
            )
        )
        self.stack = QStackedWidget()
        self.drop = DropZone(
            tr("roster_dialog.drop_title"),
            tr("roster_dialog.drop_hint"),
            tr("roster_dialog.drop_dialog"),
        )
        self.drop.file_selected.connect(self._load)
        review = QWidget()
        rv = QVBoxLayout(review)
        rv.setContentsMargins(0, 0, 0, 0)
        self.summary = QVBoxLayout()
        rv.addLayout(self.summary)
        self.preview = RosterPreviewWidget()
        self.preview.change_button.clicked.connect(self.drop.browse)
        self.preview.adjust_button.clicked.connect(self._adjust)
        rv.addWidget(self.preview, 1)
        self.deactivate = QCheckBox()
        rv.addWidget(self.deactivate)
        self.stack.addWidget(self.drop)
        self.stack.addWidget(review)
        root.addWidget(self.stack, 1)
        self.busy = BusyOverlay(self)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(button(tr("actions.cancel"), on_click=self.reject))
        self.apply = button(tr("roster_dialog.apply"), "primary", "check", self._apply)
        self.apply.setEnabled(False)
        buttons.addWidget(self.apply)
        root.addLayout(buttons)

    def _load(self, path: Path) -> None:
        self.busy.show_busy(tr("files.reading", file=path.name))
        run_in_background(lambda: load_file(path), self._loaded, self._failed)

    def _failed(self, exc: Exception) -> None:
        self.busy.hide_busy()
        show_error(self, exc, tr("errors.title.file_unusable"))

    def _loaded(self, loaded: LoadedFile) -> None:
        self.busy.hide_busy()
        mapping = resolve_mapping(self, loaded, "roster")
        if mapping is not None:
            self._build(loaded, mapping)

    def _adjust(self) -> None:
        if self.loaded and self.roster:
            mapping = resolve_mapping(
                self,
                self.loaded,
                "roster",
                force=True,
                current=self.roster.table.mapping,
            )
            if mapping is not None:
                self._build(self.loaded, mapping)

    def _build(self, loaded: LoadedFile, mapping) -> None:
        try:
            roster = self.ctx.courses.roster_preview(loaded, mapping)
            diff = self.ctx.courses.roster_diff(self.course_id, roster)
        except Exception as exc:
            show_error(self, exc, tr("errors.title.file_unusable"))
            return
        self.loaded, self.roster, self.diff = loaded, roster, diff
        self.preview.show_roster(roster)
        clear_layout(self.summary)
        self.summary.addWidget(
            Banner(
                "info",
                tr(
                    "roster_dialog.summary",
                    added=trn("plural.new_students", len(diff.added)),
                    updated=trn("plural.updated_students", len(diff.updated)),
                    unchanged=diff.unchanged,
                    missing=len(diff.missing),
                ),
            )
        )
        if diff.missing:
            names = tr("common.list_separator").join(
                f"{s.full_name} ({s.student_number})" for s in diff.missing[:6]
            )
            if len(diff.missing) > 6:
                names = tr("common.and_more", names=names, count=len(diff.missing) - 6)
            self.summary.addWidget(Banner("warning", tr("roster_dialog.missing", names=names)))
        self.deactivate.setText(
            tr("roster_dialog.deactivate", students=trn("plural.students", len(diff.missing)))
        )
        self.deactivate.setVisible(bool(diff.missing))
        self.deactivate.setChecked(bool(diff.missing))
        self.stack.setCurrentIndex(1)
        self.apply.setEnabled(True)

    def _apply(self) -> None:
        if not (self.roster and self.loaded):
            return
        try:
            self.diff = self.ctx.courses.update_roster(
                self.course_id,
                self.roster,
                self.loaded.workbook.path,
                deactivate_missing=self.deactivate.isChecked(),
            )
        except Exception as exc:
            show_error(self, exc, tr("errors.title.roster_not_updated"))
            return
        self.accept()


class EditSessionDialog(QDialog):
    def __init__(
        self, ctx: AppContext, session: AttendanceSession, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.session = session
        self.setWindowTitle(tr("edit_session.window"))
        self.setMinimumWidth(460)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(12)
        root.addWidget(label(tr("edit_session.title"), "SectionTitle"))
        root.addWidget(label(tr("edit_session.note"), "Secondary"))
        form = QFormLayout()
        self.title = QLineEdit(session.title)
        self.title.setMaxLength(120)
        self.date = QDateEdit(
            QDate(session.session_date.year, session.session_date.month, session.session_date.day)
        )
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat(tr("date.qt_format"))
        form.addRow(label(tr("edit_session.field_title"), "FieldLabel"), self.title)
        form.addRow(label(tr("edit_session.field_date"), "FieldLabel"), self.date)
        root.addLayout(form)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(button(tr("actions.cancel"), on_click=self.reject))
        save = button(tr("actions.save"), "primary", "check", self._save)
        save.setDefault(True)
        buttons.addWidget(save)
        root.addLayout(buttons)

    def _save(self) -> None:
        qd = self.date.date()
        try:
            self.ctx.attendance.update_session_details(
                self.session.id, self.title.text(), dt.date(qd.year(), qd.month(), qd.day())
            )
        except Exception as exc:
            show_error(self, exc, tr("errors.title.session_not_changed"))
            return
        self.accept()
