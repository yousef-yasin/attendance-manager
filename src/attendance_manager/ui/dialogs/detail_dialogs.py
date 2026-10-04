"""Read-only detail views for a student and for a historical session."""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableView,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from attendance_manager.domain.models import AttendanceStatus, SessionStatus
from attendance_manager.domain.statistics import SessionStats, StudentStats
from attendance_manager.i18n import format_date, format_percent, paragraph, tr
from attendance_manager.services.context import AppContext
from attendance_manager.ui import theme
from attendance_manager.ui.dialogs.attendance_dialog import participant_table, student_table
from attendance_manager.ui.dialogs.messages import show_error
from attendance_manager.ui.widgets.common import (
    Banner,
    Card,
    InfoGrid,
    StatCard,
    StatusChip,
    button,
    label,
)
from attendance_manager.ui.widgets.tables import (
    ChipDelegate,
    Column,
    ObjectTableModel,
    apply_column_widths,
    configure_table,
)


def _initials(name: str) -> str:
    parts = [p for p in name.replace("'", "").split() if p[:1].isalpha()]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def open_path(path: Path) -> None:
    if hasattr(os, "startfile"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:  # pragma: no cover - non-Windows development
        import subprocess

        subprocess.Popen(["xdg-open", str(path)])


class StudentDetailDialog(QDialog):
    def __init__(
        self,
        ctx: AppContext,
        stats: StudentStats,
        sessions: list[SessionStats],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        student = stats.student
        self.setWindowTitle(tr("student_dialog.window", name=student.full_name))
        self.resize(900, 760)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        root = QVBoxLayout(body)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(16)
        scroll.setWidget(body)
        outer.addWidget(scroll)

        head = QHBoxLayout()
        head.setSpacing(14)
        avatar = QLabel(_initials(student.full_name))
        avatar.setFixedSize(56, 56)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar.setStyleSheet(
            f"background: {theme.ACCENT_SOFT}; color: {theme.ACCENT_PRESSED}; border-radius: 28px;"
            " font-size: 18px; font-weight: 700;"
        )
        head.addWidget(avatar)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(label(paragraph(student.full_name), "PageTitle", selectable=True))
        texts.addWidget(
            label(
                tr("student_dialog.id_line", id=student.student_number),
                "PageSubtitle",
                selectable=True,
            )
        )
        head.addLayout(texts, 1)
        chip = StatusChip(stats.standing)
        head.addWidget(chip, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(head)
        if not student.is_active:
            root.addWidget(
                Banner(
                    "info",
                    tr("student_dialog.inactive"),
                )
            )

        cards = QHBoxLayout()
        cards.setSpacing(12)
        for title, icon_name, color, value in (
            (tr("student_dialog.card.sessions"), "sessions", theme.ACCENT, str(stats.sessions)),
            (tr("student_dialog.card.present"), "user-check", theme.GOOD, str(stats.present)),
            (tr("student_dialog.card.absent"), "user-x", theme.CRITICAL, str(stats.absent)),
            (
                tr("student_dialog.card.rate"),
                "percent",
                theme.ACCENT,
                format_percent(stats.percentage),
            ),
        ):
            card = StatCard(title, icon_name, color, small=True)
            card.set_value(value)
            cards.addWidget(card)
        root.addLayout(cards)

        info = Card()
        info.add_header(tr("student_dialog.info_title"), tr("student_dialog.info_subtitle"))
        pairs = [
            (tr("students.col.id"), student.student_number),
            (tr("students.col.name"), student.full_name),
        ]
        pairs += list(student.info.items())
        info.body.addWidget(InfoGrid(pairs, columns=3))
        root.addWidget(info)

        history = Card()
        history.add_header(
            tr("student_dialog.history_title"), tr("student_dialog.history_subtitle")
        )
        rows = []
        for s in sessions:
            status = stats.history.get(s.session.id)
            key = (
                "present"
                if status is AttendanceStatus.PRESENT
                else "absent"
                if status is not None
                else "not_enrolled"
            )
            rows.append((s, key))
        columns = [
            Column("#", lambda r: r[0].session.session_number, align="right", width=50),
            Column(tr("sessions.col.session"), lambda r: r[0].session.label, width=220),
            Column(
                tr("sessions.col.date"),
                lambda r: r[0].session.session_date.isoformat(),
                display=lambda r: format_date(r[0].session.session_date, "weekday_date"),
                width=170,
            ),
            Column(tr("sessions.col.file"), lambda r: r[0].session.original_filename, width=150),
            Column(
                tr("student_dialog.col.attendance"),
                lambda r: r[1],
                display=lambda r: tr(f"status.{r[1]}"),
                kind="chip",
                width=150,
            ),
        ]
        view = QTableView()
        model = ObjectTableModel(columns, rows, view)
        view.setModel(model)
        configure_table(view, 36)
        view.setItemDelegateForColumn(4, ChipDelegate(view))
        apply_column_widths(view, columns)
        view.setMinimumHeight(min(520, 60 + 36 * max(1, len(rows))))
        if not rows:
            history.body.addWidget(label(tr("student_dialog.no_history"), "Secondary"))
        else:
            history.body.addWidget(view)
        root.addWidget(history)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        close = button(tr("actions.close"), "primary", on_click=self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        close.setFocus()


class SessionDetailDialog(QDialog):
    """Opens a historical session. Read-only: nothing here changes stored data."""

    def __init__(self, ctx: AppContext, session_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        detail = ctx.attendance.session_detail(session_id)
        s = detail.session
        self.session = s
        self.setWindowTitle(tr("session_dialog.window", session=s.label))
        self.resize(1000, 760)
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 22, 26, 18)
        root.setSpacing(12)
        head = QHBoxLayout()
        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(
            label(paragraph(f"#{s.session_number}  {s.label}"), "PageTitle", selectable=True)
        )
        texts.addWidget(
            label(
                tr(
                    "session_dialog.subtitle",
                    date=format_date(s.session_date, "long"),
                    file=s.original_filename,
                    uploaded=format_date(s.uploaded_at.astimezone(), "datetime"),
                ),
                "PageSubtitle",
                wrap=True,
            )
        )
        head.addLayout(texts, 1)
        chip = StatusChip(
            text=tr("status.removed") if s.status is SessionStatus.REMOVED else tr("status.active"),
            dot=theme.MUTED if s.status is SessionStatus.REMOVED else theme.GOOD,
            soft=theme.NEUTRAL_SOFT if s.status is SessionStatus.REMOVED else theme.GOOD_SOFT,
        )
        head.addWidget(chip, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(head)
        if s.status is SessionStatus.REMOVED:
            reason = (
                tr("session_dialog.reason", reason=s.removed_reason) if s.removed_reason else ""
            )
            root.addWidget(
                Banner(
                    "warning",
                    tr("session_dialog.removed_banner") + reason,
                )
            )
        root.addWidget(Banner("info", tr("session_dialog.readonly_banner")))

        cards = QHBoxLayout()
        cards.setSpacing(12)
        for title, icon_name, color, value in (
            (tr("attendance.card.present"), "user-check", theme.GOOD, str(s.present_count)),
            (tr("attendance.card.absent"), "user-x", theme.CRITICAL, str(s.absent_count)),
            (tr("attendance.card.rate"), "percent", theme.ACCENT, format_percent(s.percentage)),
            (tr("attendance.card.unmatched"), "info", theme.MUTED, str(s.unmatched_count)),
        ):
            card = StatCard(title, icon_name, color, small=True)
            card.set_value(value)
            cards.addWidget(card)
        root.addLayout(cards)

        tabs = QTabWidget()
        tabs.addTab(
            student_table(detail.present), tr("attendance.tab.present", count=len(detail.present))
        )
        tabs.addTab(
            student_table(detail.absent), tr("attendance.tab.absent", count=len(detail.absent))
        )
        tabs.addTab(
            participant_table(detail.unmatched),
            tr("attendance.tab.unmatched", count=len(detail.unmatched)),
        )
        value_cols: list[str] = []
        for p in detail.participants:
            for k in p.data:
                if k not in value_cols:
                    value_cols.append(k)
        tabs.addTab(
            participant_table(detail.participants, value_cols),
            tr("session_dialog.tab.original_rows", count=len(detail.participants)),
        )
        meta = {
            (tr("session_dialog.sheet") if k == "Sheet" else k): v
            for k, v in s.metadata.items()
            if v
        }
        if meta:
            info = QWidget()
            lay = QVBoxLayout(info)
            lay.setContentsMargins(4, 12, 4, 4)
            lay.addWidget(InfoGrid(list(meta.items()), columns=2))
            lay.addStretch(1)
            tabs.addTab(info, tr("session_dialog.tab.file_info"))
        root.addWidget(tabs, 1)

        buttons = QHBoxLayout()
        buttons.addWidget(
            button(
                tr("actions.open_original"),
                "",
                "external",
                self._open_original,
                tr("session_dialog.open_original_tooltip"),
            )
        )
        buttons.addWidget(button(tr("session_dialog.export"), "", "download", self._export))
        buttons.addStretch(1)
        close = button(tr("actions.close"), "primary", on_click=self.accept)
        buttons.addWidget(close)
        root.addLayout(buttons)
        close.setFocus()

    def _open_original(self) -> None:
        try:
            if not self.ctx.attendance.verify_original(self.session.id):
                raise FileNotFoundError(tr("errors.original_missing"))
            open_path(self.ctx.attendance.original_file_copy(self.session.id))
        except Exception as exc:
            show_error(self, exc, tr("errors.title.original_not_opened"))

    def _export(self) -> None:
        default = (
            Path.home()
            / "Documents"
            / f"{self.session.label} - {self.session.session_date:%Y-%m-%d}.xlsx"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dialogs.export_session"), str(default), tr("files.xlsx_filter")
        )
        if not path:
            return
        try:
            out = self.ctx.reports.export_session(self.session.id, Path(path))
            open_path(out)
        except Exception as exc:
            show_error(self, exc, tr("errors.title.session_not_exported"))
