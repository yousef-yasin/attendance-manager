from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout

from attendance_manager.i18n import tr, trn
from attendance_manager.ui import theme
from attendance_manager.ui.dialogs.detail_dialogs import open_path
from attendance_manager.ui.dialogs.messages import show_error
from attendance_manager.ui.icons import pixmap
from attendance_manager.ui.pages.base import Page, page_body, scroll_container
from attendance_manager.ui.widgets.common import Card, button, label
from attendance_manager.ui.widgets.feedback import BusyOverlay, run_in_background

# Report sheet ids, in workbook order. Names/descriptions: "report.sheet.<id>" / "reports.sheet_desc.<id>".
SHEET_IDS = (
    "summary",
    "cumulative",
    "by_session",
    "absence_ranking",
    "highest",
    "at_risk",
    "details",
)


class ReportsPage(Page):
    key = "reports"
    needs_course = True

    def __init__(self, window) -> None:
        super().__init__(window)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body, layout = page_body()
        self.last_dir = str(Path.home() / "Documents")

        card = Card(padding=24)
        card.add_header(tr("reports.full_title"), tr("reports.full_subtitle"))
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        for i, sheet_id in enumerate(SHEET_IDS):
            badge = QLabel(str(i + 1))
            badge.setFixedSize(26, 26)
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setStyleSheet(
                f"background: {theme.ACCENT_SOFT}; color: {theme.ACCENT_PRESSED}; border-radius: 13px;"
                " font-weight: 700;"
            )
            grid.addWidget(badge, i, 0, Qt.AlignmentFlag.AlignTop)
            texts = QVBoxLayout()
            texts.setSpacing(0)
            texts.addWidget(label(tr(f"report.sheet.{sheet_id}"), "CardTitle"))
            texts.addWidget(label(tr(f"reports.sheet_desc.{sheet_id}"), "Secondary", wrap=True))
            grid.addLayout(texts, i, 1)
        grid.setColumnStretch(1, 1)
        card.body.addLayout(grid)
        card.body.addSpacing(8)
        card.body.addWidget(label(tr("reports.language_note"), "Muted", wrap=True))
        row = QHBoxLayout()
        self.course_label = label("", "Secondary")
        row.addWidget(self.course_label, 1)
        self.generate_btn = button(tr("reports.generate"), "primary", "download", self.generate)
        row.addWidget(self.generate_btn)
        card.body.addLayout(row)
        layout.addWidget(card)

        session_card = Card(padding=24)
        session_card.add_header(
            tr("reports.single_title"),
            tr("reports.single_text"),
            button(
                tr("reports.go_to_sessions"), "", "sessions", lambda: window.navigate("sessions")
            ),
        )
        layout.addWidget(session_card)

        tip = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(pixmap("info", theme.MUTED, 16))
        tip.addWidget(ic, 0, Qt.AlignmentFlag.AlignTop)
        tip.addWidget(label(tr("reports.offline_note"), "Muted", wrap=True), 1)
        layout.addLayout(tip)
        layout.addStretch(1)
        outer.addWidget(scroll_container(body))
        self.busy = BusyOverlay(self)

    def header_subtitle(self) -> str:
        course = self.state.course
        return course.display_name if course else self.subtitle

    def refresh(self) -> None:
        course = self.state.course
        if course is None:
            self.course_label.setText(tr("reports.no_course"))
            self.generate_btn.setEnabled(False)
            return
        students, sessions = self.ctx.courses.counts(course.id)
        self.course_label.setText(
            tr(
                "reports.course_line",
                course=course.display_name,
                students=trn("plural.students", students),
                sessions=trn("plural.sessions", sessions),
            )
        )
        self.generate_btn.setEnabled(True)

    def generate(self) -> None:
        course = self.state.course
        if course is None:
            return
        default = str(Path(self.last_dir) / self.ctx.reports.default_filename(course.id))
        path, _ = QFileDialog.getSaveFileName(
            self, tr("reports.save_dialog"), default, tr("files.xlsx_filter")
        )
        if not path:
            return
        target = Path(path)
        if target.suffix.lower() != ".xlsx":
            target = target.with_suffix(".xlsx")
        self.last_dir = str(target.parent)
        try:
            data = self.ctx.reports.report_data(course.id)
        except Exception as exc:
            show_error(self, exc, tr("errors.title.report_not_created"))
            return
        self.busy.show_busy(tr("reports.busy"))
        run_in_background(lambda: self.ctx.reports.write(target, data), self._done, self._failed)

    def _done(self, path: Path) -> None:
        self.busy.hide_busy()
        self.window_.toast(
            "success",
            tr("toast.report_saved"),
            path.name,
            [
                (tr("actions.open_report"), lambda: open_path(path)),
                (tr("actions.show_in_folder"), lambda: open_path(path.parent)),
            ],
        )

    def _failed(self, exc: Exception) -> None:
        self.busy.hide_busy()
        show_error(self, exc, tr("errors.title.report_not_created"))
