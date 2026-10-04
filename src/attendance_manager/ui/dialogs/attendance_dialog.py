"""Add a weekly attendance file: drop -> review -> save."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDateEdit,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
    QStackedWidget,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.errors import AttendanceError
from attendance_manager.domain.matching import ParticipantRow
from attendance_manager.domain.models import AttendanceSession, Student
from attendance_manager.i18n import format_percent, paragraph, tr, trn
from attendance_manager.importing.importer import LoadedFile, load_file
from attendance_manager.services.attendance_service import SessionPreview
from attendance_manager.services.context import AppContext
from attendance_manager.ui import theme
from attendance_manager.ui.dialogs.file_loading import resolve_mapping
from attendance_manager.ui.dialogs.messages import show_error
from attendance_manager.ui.widgets.common import Banner, StatCard, button, clear_layout, label
from attendance_manager.ui.widgets.drop_zone import DropZone
from attendance_manager.ui.widgets.feedback import BusyOverlay, run_in_background
from attendance_manager.ui.widgets.tables import (
    Column,
    ObjectTableModel,
    apply_column_widths,
    configure_table,
    mapping_column,
)


def student_columns() -> list[Column]:
    return [
        Column(tr("students.col.id"), lambda s: s.student_number, width=140),
        Column(tr("students.col.name"), lambda s: s.full_name, width=320),
    ]


def student_table(rows: list[Student], extra: list[Column] | None = None) -> QTableView:
    view = QTableView()
    columns = student_columns() + (extra or [])
    model = ObjectTableModel(columns, rows, view)
    view.setModel(model)
    configure_table(view, 34)
    apply_column_widths(view, columns)
    return view


def participant_table(rows: list, value_columns: list[str] | None = None) -> QTableView:
    view = QTableView()
    columns = [
        Column(tr("attendance.col.row"), lambda p: p.row_number, align="right", width=100),
        Column(
            tr("attendance.col.identifier"),
            lambda p: p.raw_identifier or tr("attendance.empty_id"),
            width=220,
        ),
        Column(tr("attendance.col.name"), lambda p: p.name, width=260),
    ]
    for name in value_columns or []:
        columns.append(mapping_column(name, lambda p: p.data))
    model = ObjectTableModel(columns, rows, view)
    view.setModel(model)
    configure_table(view, 34)
    apply_column_widths(view, columns)
    return view


class AddAttendanceDialog(QDialog):
    def __init__(
        self,
        ctx: AppContext,
        course_id: int,
        parent: QWidget | None = None,
        initial_file: Path | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.course_id = course_id
        self.course = ctx.courses.get(course_id)
        self.loaded: LoadedFile | None = None
        self.preview: SessionPreview | None = None
        self.saved: AttendanceSession | None = None
        self.setWindowTitle(tr("actions.add_attendance"))
        self.resize(1040, 760)

        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(12)
        root.addWidget(label(tr("actions.add_attendance"), "PageTitle"))
        root.addWidget(label(paragraph(self.course.display_name), "PageSubtitle"))

        self.stack = QStackedWidget()
        root.addWidget(self.stack, 1)
        self.drop = DropZone(
            tr("attendance.drop_title"),
            tr("attendance.drop_hint"),
            tr("attendance.drop_dialog"),
        )
        self.drop.file_selected.connect(self._load)
        self.stack.addWidget(self.drop)

        # ---- review page
        review = QWidget()
        rv = QVBoxLayout(review)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(12)
        head = QHBoxLayout()
        self.file_label = label("", "SectionTitle")
        self.file_hint = label("", "Secondary")
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(self.file_label)
        texts.addWidget(self.file_hint)
        head.addLayout(texts, 1)
        head.addWidget(
            button(tr("files.adjust_columns"), "", "columns", self._adjust),
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        head.addWidget(
            button(tr("files.choose_another"), "", "folder", self.drop.browse),
            0,
            Qt.AlignmentFlag.AlignTop,
        )
        rv.addLayout(head)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.addWidget(label(tr("attendance.session_title"), "FieldLabel"), 0, 0)
        form.addWidget(label(tr("attendance.lecture_date"), "FieldLabel"), 0, 1)
        self.title = QLineEdit()
        self.title.setMaxLength(120)
        self.title.textEdited.connect(lambda: self.title.setProperty("auto", False))
        self.date = QDateEdit()
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat(tr("date.qt_format"))
        self.date.setMinimumWidth(240)
        self.date_hint = label("", "StatHint")
        form.addWidget(self.title, 1, 0)
        form.addWidget(self.date, 1, 1)
        form.addWidget(self.date_hint, 2, 1)
        form.setColumnStretch(0, 3)
        form.setColumnStretch(1, 2)
        rv.addLayout(form)

        cards = QHBoxLayout()
        cards.setSpacing(12)
        self.card_present = StatCard(
            tr("attendance.card.present"), "user-check", theme.GOOD, small=True
        )
        self.card_absent = StatCard(
            tr("attendance.card.absent"), "user-x", theme.CRITICAL, small=True
        )
        self.card_pct = StatCard(tr("attendance.card.rate"), "percent", theme.ACCENT, small=True)
        self.card_unmatched = StatCard(
            tr("attendance.card.unmatched"), "info", theme.MUTED, small=True
        )
        for c in (self.card_present, self.card_absent, self.card_pct, self.card_unmatched):
            cards.addWidget(c)
        rv.addLayout(cards)

        self.notices = QVBoxLayout()
        self.notices.setSpacing(6)
        rv.addLayout(self.notices)
        self.tabs = QTabWidget()
        rv.addWidget(self.tabs, 1)
        self.override = QCheckBox(tr("attendance.override"))
        self.override.toggled.connect(self._update_save)
        rv.addWidget(self.override)
        self.stack.addWidget(review)
        self.busy = BusyOverlay(self)

        buttons = QHBoxLayout()
        self.steps_hint = label(tr("attendance.nothing_saved"), "Muted")
        buttons.addWidget(self.steps_hint)
        buttons.addStretch(1)
        buttons.addWidget(button(tr("actions.cancel"), on_click=self.reject))
        self.save = button(tr("attendance.save"), "primary", "check", self._save)
        self.save.setEnabled(False)
        buttons.addWidget(self.save)
        root.addLayout(buttons)

        if initial_file is not None:
            from PySide6.QtCore import QTimer

            QTimer.singleShot(0, lambda: self._load(initial_file))

    # ---------------------------------------------------------------- loading
    def _load(self, path: Path) -> None:
        self.busy.show_busy(tr("files.reading", file=path.name))
        run_in_background(lambda: load_file(path), self._loaded, self._failed)

    def _failed(self, exc: Exception) -> None:
        self.busy.hide_busy()
        show_error(self, exc, tr("errors.title.file_unusable"))

    def _loaded(self, loaded: LoadedFile) -> None:
        self.busy.hide_busy()
        mapping = resolve_mapping(self, loaded, "attendance")
        if mapping is None:
            return
        self._build(loaded, mapping)

    def _adjust(self) -> None:
        if self.loaded is None or self.preview is None:
            return
        mapping = resolve_mapping(
            self,
            self.loaded,
            "attendance",
            force=True,
            current=self.preview.mapping,
        )
        if mapping is not None:
            self._build(self.loaded, mapping)

    def _build(self, loaded: LoadedFile, mapping) -> None:
        try:
            preview = self.ctx.attendance.build_preview(self.course_id, loaded, mapping)
        except Exception as exc:
            show_error(self, exc, tr("errors.title.file_unusable"))
            return
        self.loaded, self.preview = loaded, preview
        m = preview.match
        table = preview.table
        self.file_label.setText(paragraph(table.file_name))
        self.file_hint.setText(
            tr(
                "attendance.file_hint",
                sheet=table.sheet_name,
                rows=trn("plural.rows", len(table.rows)),
                column=table.id_column_name,
            )
        )
        if not self.title.text().strip() or self.title.property("auto"):
            self.title.setText(preview.suggested_title)
            self.title.setProperty("auto", True)
        date = preview.detected_date or dt.date.today()
        self.date.setDate(QDate(date.year, date.month, date.day))
        self.date_hint.setText(
            tr("attendance.date_detected")
            if preview.detected_date
            else tr("attendance.date_not_found")
        )
        of_total = tr("attendance.of_students", students=trn("plural.students", len(m.statuses)))
        self.card_present.set_value(str(m.present_count), of_total)
        self.card_absent.set_value(str(m.absent_count), of_total)
        self.card_pct.set_value(format_percent(m.percentage), tr("attendance.rate_hint"))
        self.card_unmatched.set_value(str(len(m.unmatched)), tr("attendance.unmatched_hint"))

        clear_layout(self.notices)
        for notice in preview.notices:
            self.notices.addWidget(Banner(notice.severity.value, notice.message))

        self.tabs.clear()
        present_rows = {k: m.evidence[k].row_number for k in m.present_keys}
        extra = [
            Column(
                tr("attendance.col.row"),
                lambda s: present_rows.get(s.student_key, ""),
                align="right",
                width=100,
            )
        ]
        self.tabs.addTab(
            student_table(preview.present_students, extra),
            tr("attendance.tab.present", count=m.present_count),
        )
        self.tabs.addTab(
            student_table(preview.absent_students),
            tr("attendance.tab.absent", count=m.absent_count),
        )
        value_cols = [
            n for n in table.column_names if n not in (table.id_column_name, table.name_column_name)
        ][:4]
        self.tabs.addTab(
            participant_table(m.unmatched), tr("attendance.tab.unmatched", count=len(m.unmatched))
        )
        rows = [
            ParticipantRow(r.row_number, r.raw_identifier, r.key, r.name, r.values)
            for r in table.rows
        ]
        self.tabs.addTab(
            participant_table(rows, value_cols), tr("attendance.tab.all_rows", count=len(rows))
        )

        self.override.setChecked(False)
        self.override.setVisible(preview.duplicate_of is not None)
        self.stack.setCurrentIndex(1)
        self._update_save()
        self.save.setFocus()

    def _update_save(self) -> None:
        p = self.preview
        ok = p is not None and (p.duplicate_of is None or self.override.isChecked())
        self.save.setEnabled(ok)
        self.save.setText(
            tr("attendance.save_anyway")
            if p is not None and p.duplicate_of is not None
            else tr("attendance.save")
        )
        self.save.setProperty(
            "kind", "danger" if p is not None and p.duplicate_of is not None else "primary"
        )
        self.save.style().unpolish(self.save)
        self.save.style().polish(self.save)

    # ------------------------------------------------------------------ save
    def _save(self) -> None:
        if self.preview is None:
            return
        qd = self.date.date()
        try:
            self.saved = self.ctx.attendance.save_session(
                self.preview,
                title=self.title.text(),
                session_date=dt.date(qd.year(), qd.month(), qd.day()),
                allow_duplicate=self.override.isChecked(),
            )
        except AttendanceError as exc:
            show_error(self, exc, tr("errors.title.attendance_not_saved"))
            return
        except Exception as exc:
            show_error(self, exc, tr("errors.title.attendance_not_saved"))
            return
        self.accept()
