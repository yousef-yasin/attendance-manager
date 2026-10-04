from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QTableView, QVBoxLayout

from attendance_manager.i18n import format_date, tr, trn
from attendance_manager.services.backup_service import BackupInfo
from attendance_manager.ui.dialogs.detail_dialogs import open_path
from attendance_manager.ui.dialogs.messages import confirm, show_error
from attendance_manager.ui.pages.base import Page, page_body, scroll_container
from attendance_manager.ui.widgets.common import Card, ResponsiveGrid, button, label
from attendance_manager.ui.widgets.feedback import BusyOverlay
from attendance_manager.ui.widgets.tables import (
    PAYLOAD_ROLE,
    Column,
    ObjectTableModel,
    apply_column_widths,
    configure_table,
)


def _size(n: int) -> str:
    if n < 1024 * 1024:
        return tr("backup.size_kb", size=f"{n / 1024:.0f}")
    return tr("backup.size_mb", size=f"{n / 1024 / 1024:.1f}")


def backup_kind(b: BackupInfo) -> str:
    """Stored reasons are stable English codes/phrases; show them translated."""
    reason = b.reason.lower()
    if reason == "automatic":
        return tr("backup.kind.automatic")
    if reason.startswith("before deleting"):
        return tr("backup.kind.before_delete")
    if reason.startswith("before restore"):
        return tr("backup.kind.before_restore")
    return tr("backup.kind.manual")


def backup_columns() -> list[Column]:
    return [
        Column(
            tr("backup.col.created"),
            lambda b: b.created_at.isoformat(),
            display=lambda b: format_date(b.created_at.astimezone(), "long_datetime"),
            width=230,
        ),
        Column(tr("backup.col.type"), backup_kind, width=210),
        Column(tr("backup.col.courses"), lambda b: b.courses, align="right", width=90),
        Column(tr("backup.col.sessions"), lambda b: b.sessions, align="right", width=90),
        Column(
            tr("backup.col.size"),
            lambda b: b.size_bytes,
            display=lambda b: _size(b.size_bytes),
            align="right",
            width=90,
        ),
        Column(tr("backup.col.file"), lambda b: b.path.name),
    ]


class BackupPage(Page):
    key = "backup"

    def __init__(self, window) -> None:
        super().__init__(window)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body, layout = page_body()
        self.last_dir = str(Path.home() / "Documents")

        cards = ResponsiveGrid(min_item_width=380, max_columns=2)
        create = Card(padding=22)
        create.add_header(tr("backup.create_title"), tr("backup.create_text"))
        self.last_label = label("", "Secondary")
        create.body.addWidget(self.last_label)
        create.body.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(button(tr("backup.backup_now"), "primary", "download", self.backup_now))
        row.addStretch(1)
        create.body.addLayout(row)
        restore = Card(padding=22)
        restore.add_header(tr("backup.restore_title"), tr("backup.restore_text"))
        restore.body.addStretch(1)
        row = QHBoxLayout()
        row.addWidget(button(tr("backup.restore_from_file"), "", "history", self.restore_from_file))
        row.addStretch(1)
        restore.body.addLayout(row)
        cards.set_items([create, restore])
        layout.addWidget(cards)

        history = Card(padding=22)
        history.add_header(tr("backup.history_title"), tr("backup.history_text"))
        self.columns = backup_columns()
        self.model = ObjectTableModel(self.columns)
        self.table = QTableView()
        self.table.setModel(self.model)
        configure_table(self.table, 40)
        self.table.setMinimumHeight(300)
        self.table.doubleClicked.connect(lambda _: self.restore_selected())
        history.body.addWidget(self.table)
        self.empty_history = label(tr("backup.no_backups"), "Secondary")
        history.body.addWidget(self.empty_history)
        row = QHBoxLayout()
        self.restore_btn = button(
            tr("backup.restore_selected"), "", "history", self.restore_selected
        )
        row.addWidget(self.restore_btn)
        row.addWidget(
            button(
                tr("backup.open_folder"),
                "",
                "folder",
                lambda: open_path(self.ctx.paths.backups_dir),
            )
        )
        row.addStretch(1)
        history.body.addLayout(row)
        layout.addWidget(history)
        layout.addStretch(1)
        outer.addWidget(scroll_container(body))
        self.busy = BusyOverlay(self)
        self._widths = False

    def refresh(self) -> None:
        backups = self.ctx.backups.list_backups()
        self.model.set_rows(backups)
        if not self._widths:
            apply_column_widths(self.table, self.columns, stretch_title=tr("backup.col.file"))
            self._widths = True
        self.table.setVisible(bool(backups))
        self.empty_history.setVisible(not backups)
        self.restore_btn.setEnabled(bool(backups))
        last = backups[0].created_at.astimezone() if backups else None
        self.last_label.setText(
            tr("backup.last_backup", when=format_date(last, "long_datetime"))
            if last
            else tr("backup.never")
        )

    def backup_now(self) -> None:
        default = Path(self.last_dir) / self.ctx.backups.default_backup_name()
        path, _ = QFileDialog.getSaveFileName(
            self, tr("backup.save_dialog"), str(default), tr("files.zip_filter")
        )
        if not path:
            return
        target = Path(path) if path.lower().endswith(".zip") else Path(path + ".zip")
        self.last_dir = str(target.parent)
        self.busy.show_busy(tr("backup.busy_create"))
        try:
            out = self.ctx.backups.create_backup(target)
            # Keep a copy in the app's backup history too.
            if out.parent != self.ctx.paths.backups_dir:
                shutil.copyfile(out, self.ctx.paths.backups_dir / out.name)
        except Exception as exc:
            self.busy.hide_busy()
            show_error(self, exc, tr("errors.title.backup_not_created"))
            return
        self.busy.hide_busy()
        self.window_.toast(
            "success",
            tr("toast.backup_created"),
            out.name,
            [(tr("actions.show_in_folder"), lambda: open_path(out.parent))],
        )
        self.refresh_now()

    def restore_from_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("backup.open_dialog"), self.last_dir, tr("files.zip_filter")
        )
        if path:
            self._restore(Path(path))

    def restore_selected(self) -> None:
        rows = self.table.selectionModel().selectedRows()
        if rows:
            self._restore(self.model.data(rows[0], PAYLOAD_ROLE).path)

    def _restore(self, path: Path) -> None:
        try:
            info = self.ctx.backups.validate_backup(path)
        except Exception as exc:
            show_error(self, exc, tr("errors.title.backup_cannot_restore"))
            return
        if not confirm(
            self,
            tr("confirm.restore.title"),
            tr(
                "confirm.restore.message",
                when=format_date(info.created_at.astimezone(), "long_datetime"),
                courses=trn("plural.courses", info.courses),
                sessions=trn("plural.sessions", info.sessions),
            ),
            tr("confirm.restore.button"),
            danger=True,
            details=tr("confirm.restore.details"),
        ):
            return
        self.busy.show_busy(tr("backup.busy_restore"))
        try:
            safety = self.ctx.backups.restore_backup(path)
        except Exception as exc:
            self.busy.hide_busy()
            show_error(self, exc, tr("errors.title.backup_not_restored"))
            return
        self.busy.hide_busy()
        self.window_.after_restore()
        self.window_.toast(
            "success",
            tr("toast.backup_restored"),
            tr("toast.backup_restored_detail", file=safety.name),
            timeout_ms=8000,
        )
        self.refresh_now()
