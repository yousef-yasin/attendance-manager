from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
)

from attendance_manager import __version__
from attendance_manager.i18n import get_language, tr
from attendance_manager.persistence.schema import SCHEMA_VERSION
from attendance_manager.services.settings_service import AppSettings
from attendance_manager.ui.dialogs.detail_dialogs import open_path
from attendance_manager.ui.dialogs.messages import show_error
from attendance_manager.ui.pages.base import Page, page_body, scroll_container
from attendance_manager.ui.widgets.common import Card, InfoGrid, button, label
from attendance_manager.ui.widgets.language_switch import LanguageSwitch


class SettingsPage(Page):
    key = "settings"

    def __init__(self, window) -> None:
        super().__init__(window)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        body, layout = page_body()

        language = Card(padding=22)
        switch = LanguageSwitch(get_language())
        switch.language_selected.connect(window.change_language, Qt.ConnectionType.QueuedConnection)
        language.add_header(tr("settings.language_title"), tr("settings.language_subtitle"), switch)
        layout.addWidget(language)

        profile = Card(padding=22)
        profile.add_header(tr("settings.instructor_title"), tr("settings.instructor_subtitle"))
        form = QFormLayout()
        self.instructor = QLineEdit()
        self.instructor.setPlaceholderText(tr("settings.instructor_placeholder"))
        self.instructor.setMaxLength(120)
        form.addRow(label(tr("settings.instructor_name"), "FieldLabel"), self.instructor)
        profile.body.addLayout(form)
        layout.addWidget(profile)

        rules = Card(padding=22)
        rules.add_header(tr("settings.limits_title"), tr("settings.limits_subtitle"))
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.at_risk = QDoubleSpinBox()
        self.warning = QDoubleSpinBox()
        for spin in (self.at_risk, self.warning):
            spin.setRange(0, 100)
            spin.setDecimals(0)
            spin.setSuffix(" %")
            spin.setMaximumWidth(140)
        form.addRow(label(tr("settings.at_risk_below"), "FieldLabel"), self.at_risk)
        form.addRow(label(tr("settings.warning_below"), "FieldLabel"), self.warning)
        rules.body.addLayout(form)
        self.rules_hint = label("", "Secondary", wrap=True)
        rules.body.addWidget(self.rules_hint)
        layout.addWidget(rules)

        backups = Card(padding=22)
        backups.add_header(tr("settings.backups_title"), tr("settings.backups_subtitle"))
        self.auto_backup = QCheckBox(tr("settings.auto_backup"))
        backups.body.addWidget(self.auto_backup)
        form = QFormLayout()
        self.keep = QSpinBox()
        self.keep.setRange(1, 365)
        self.keep.setSuffix(tr("settings.keep_suffix"))
        self.keep.setMaximumWidth(170)
        form.addRow(label(tr("settings.keep_latest"), "FieldLabel"), self.keep)
        backups.body.addLayout(form)
        layout.addWidget(backups)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.revert_btn = button(tr("settings.discard"), on_click=self.refresh_now)
        self.save_btn = button(tr("settings.save"), "primary", "check", self.save)
        save_row.addWidget(self.revert_btn)
        save_row.addWidget(self.save_btn)
        layout.addLayout(save_row)

        storage = Card(padding=22)
        storage.add_header(tr("settings.storage_title"), tr("settings.storage_subtitle"))
        self.storage_info = QVBoxLayout()
        storage.body.addLayout(self.storage_info)
        row = QHBoxLayout()
        row.addWidget(
            button(
                tr("settings.open_data_folder"),
                "",
                "folder",
                lambda: open_path(self.ctx.paths.root),
            )
        )
        row.addWidget(
            button(
                tr("settings.open_logs_folder"),
                "",
                "file",
                lambda: open_path(self.ctx.paths.logs_dir),
            )
        )
        row.addStretch(1)
        storage.body.addLayout(row)
        layout.addWidget(storage)
        layout.addStretch(1)
        outer.addWidget(scroll_container(body))

        self.instructor.textChanged.connect(self._changed)
        for s in (self.at_risk, self.warning):
            s.valueChanged.connect(self._changed)
        self.keep.valueChanged.connect(self._changed)
        self.auto_backup.toggled.connect(self._changed)

    def _form_settings(self) -> AppSettings:
        current = self.ctx.settings.load()
        return AppSettings(
            instructor_name=self.instructor.text(),
            at_risk_below=self.at_risk.value(),
            warning_below=self.warning.value(),
            auto_backup=self.auto_backup.isChecked(),
            auto_backup_keep=self.keep.value(),
            last_course_id=current.last_course_id,
        )

    def _changed(self) -> None:
        s = self._form_settings()
        dirty = s != self.ctx.settings.load()
        self.save_btn.setEnabled(dirty)
        self.revert_btn.setEnabled(dirty)
        if s.at_risk_below > s.warning_below:
            self.rules_hint.setText(tr("settings.limits_invalid"))
            self.save_btn.setEnabled(False)
        else:
            self.rules_hint.setText(
                tr(
                    "settings.limits_hint",
                    warning=f"{s.warning_below:g}",
                    at_risk=f"{s.at_risk_below:g}",
                )
            )

    def refresh(self) -> None:
        s = self.ctx.settings.load()
        widgets = (self.instructor, self.at_risk, self.warning, self.auto_backup, self.keep)
        for w in widgets:
            w.blockSignals(True)
        self.instructor.setText(s.instructor_name)
        self.at_risk.setValue(s.at_risk_below)
        self.warning.setValue(s.warning_below)
        self.auto_backup.setChecked(s.auto_backup)
        self.keep.setValue(s.auto_backup_keep)
        for w in widgets:
            w.blockSignals(False)
        self._changed()
        while self.storage_info.count():
            item = self.storage_info.takeAt(0)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.deleteLater()
        install = self.ctx.db.query_one("SELECT value FROM app_meta WHERE key='installation_id'")
        self.storage_info.addWidget(
            InfoGrid(
                [
                    (tr("settings.info.data_folder"), str(self.ctx.paths.root)),
                    (tr("settings.info.database"), str(self.ctx.paths.database)),
                    (
                        tr("settings.info.version"),
                        tr(
                            "settings.info.version_value",
                            version=__version__,
                            schema=SCHEMA_VERSION,
                        ),
                    ),
                    (tr("settings.info.installation_id"), install["value"] if install else "—"),
                ],
                columns=2,
            )
        )

    def save(self) -> None:
        try:
            self.ctx.settings.save(self._form_settings())
        except Exception as exc:
            show_error(self, exc, tr("errors.title.settings_not_saved"))
            return
        self.window_.toast("success", tr("toast.settings_saved"))
        self.state.notify_changed()
        self.refresh_now()
